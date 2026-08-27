"""Outbound HTTP: one pooled client, an SSRF guard, and a global fetch budget.

Every outbound request in the app goes through `fetch_text`. Article URLs come
from third-party feeds and search APIs, so they are attacker-influenceable: the
guard blocks loopback/private/link-local targets (including via redirect) so a
malicious feed cannot use the backend to reach internal services.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()
_fetch_gate: asyncio.Semaphore | None = None
_resolve_cache: dict[str, bool] = {}

ALLOWED_SCHEMES = frozenset({"http", "https"})


class BlockedURLError(Exception):
    """The target resolves to a non-public address, or the scheme is unsupported."""


def _is_public(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


async def _host_is_public(host: str) -> bool:
    """Resolve `host` and require every answer to be a public address.

    Requiring *all* answers to be public closes the DNS-rebinding-ish hole where
    a name resolves to one public and one private address.
    """

    if host in _resolve_cache:
        return _resolve_cache[host]

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, proto=socket.IPPROTO_TCP
        )
    except (socket.gaierror, UnicodeError, OSError):
        _resolve_cache[host] = False
        return False

    addresses = {info[4][0] for info in infos}
    allowed = bool(addresses) and all(_is_public(addr) for addr in addresses)
    _resolve_cache[host] = allowed
    return allowed


async def assert_fetchable(url: str) -> None:
    """Raise `BlockedURLError` unless `url` is a public http(s) target."""

    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise BlockedURLError(f"unsupported scheme: {parts.scheme or 'none'}")
    if not parts.hostname:
        raise BlockedURLError("missing host")
    if settings.allow_private_fetch_targets:
        return
    if not await _host_is_public(parts.hostname):
        raise BlockedURLError(f"blocked non-public host: {parts.hostname}")


def _gate() -> asyncio.Semaphore:
    global _fetch_gate
    if _fetch_gate is None:
        _fetch_gate = asyncio.Semaphore(max(1, settings.max_concurrent_fetches))
    return _fetch_gate


async def get_client() -> httpx.AsyncClient:
    """Process-wide pooled client. Reused across runs so TLS/TCP setup is paid once."""

    global _client
    if _client is not None and not _client.is_closed:
        return _client
    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.source_fetch_timeout_seconds),
                headers={"User-Agent": settings.http_user_agent},
                limits=httpx.Limits(
                    max_connections=settings.max_concurrent_fetches * 2,
                    max_keepalive_connections=settings.max_concurrent_fetches,
                ),
                follow_redirects=False,
            )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


@asynccontextmanager
async def http_client():
    """For call sites that want a client without owning its lifecycle."""

    yield await get_client()


async def fetch(
    url: str,
    *,
    method: str = "GET",
    max_redirects: int = 4,
    **kwargs,
) -> httpx.Response:
    """Fetch `url`, validating the target before every hop.

    Redirects are followed manually: `follow_redirects=True` would let a public
    URL bounce the request to `http://169.254.169.254/` behind the guard's back.
    """

    client = await get_client()
    current = url

    async with _gate():
        for _ in range(max_redirects + 1):
            await assert_fetchable(current)
            response = await client.request(method, current, **kwargs)
            if not response.is_redirect:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            current = str(response.next_request.url) if response.next_request else location

    raise BlockedURLError(f"too many redirects: {url}")


async def fetch_text(url: str, *, max_bytes: int | None = None) -> str | None:
    """Return decoded body text, or None on any failure. Never raises."""

    limit = max_bytes if max_bytes is not None else settings.max_download_bytes
    try:
        response = await fetch(url)
        response.raise_for_status()
    except BlockedURLError as exc:
        log.debug("fetch blocked", extra={"url": url, "reason": str(exc)})
        return None
    except (httpx.HTTPError, UnicodeDecodeError, OSError) as exc:
        log.debug("fetch failed", extra={"url": url, "error": type(exc).__name__})
        return None

    if len(response.content) > limit:
        log.debug("response too large", extra={"url": url, "bytes": len(response.content)})
        return None

    try:
        return response.text
    except (UnicodeDecodeError, LookupError):
        return None
