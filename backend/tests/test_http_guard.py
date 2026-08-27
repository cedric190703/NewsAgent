"""The SSRF guard: feed and search URLs are attacker-influenceable input."""

import pytest

from app.core import http as core_http
from app.core.config import settings


@pytest.fixture(autouse=True)
def _clear_resolve_cache():
    core_http._resolve_cache.clear()
    yield
    core_http._resolve_cache.clear()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com",
        "javascript:alert(1)",
    ],
)
async def test_non_http_schemes_are_rejected(url):
    with pytest.raises(core_http.BlockedURLError):
        await core_http.assert_fetchable(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/admin",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://[::1]:9000/",
        "http://0.0.0.0/",
    ],
)
async def test_private_and_loopback_targets_are_blocked(url):
    with pytest.raises(core_http.BlockedURLError):
        await core_http.assert_fetchable(url)


async def test_missing_host_is_rejected():
    with pytest.raises(core_http.BlockedURLError):
        await core_http.assert_fetchable("http:///nohost")


async def test_unresolvable_host_is_rejected():
    with pytest.raises(core_http.BlockedURLError):
        await core_http.assert_fetchable("https://this-host-does-not-exist.invalid/x")


async def test_public_addresses_are_allowed(monkeypatch):
    async def fake_getaddrinfo(host, *args, **kwargs):
        return [(None, None, None, None, ("93.184.216.34", 0))]

    monkeypatch.setattr(
        core_http.asyncio.get_running_loop().__class__,
        "getaddrinfo",
        lambda self, *a, **k: fake_getaddrinfo(*a, **k),
        raising=False,
    )
    await core_http.assert_fetchable("https://example.com/article")


async def test_mixed_public_and_private_answers_are_blocked(monkeypatch):
    """A name resolving to both a public and a private address must not pass."""

    async def fake_getaddrinfo(self, host, *args, **kwargs):
        return [
            (None, None, None, None, ("93.184.216.34", 0)),
            (None, None, None, None, ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr(
        core_http.asyncio.get_running_loop().__class__,
        "getaddrinfo",
        fake_getaddrinfo,
        raising=False,
    )
    with pytest.raises(core_http.BlockedURLError):
        await core_http.assert_fetchable("https://rebind.example/x")


async def test_guard_can_be_disabled_for_trusted_networks(monkeypatch):
    monkeypatch.setattr(settings, "allow_private_fetch_targets", True)
    await core_http.assert_fetchable("http://127.0.0.1:8000/admin")


async def test_fetch_text_returns_none_instead_of_raising():
    assert await core_http.fetch_text("http://127.0.0.1:1/blocked") is None
    assert await core_http.fetch_text("not-a-url") is None


def test_public_address_classification():
    assert core_http._is_public("93.184.216.34") is True
    assert core_http._is_public("127.0.0.1") is False
    assert core_http._is_public("10.1.2.3") is False
    assert core_http._is_public("172.16.0.1") is False
    assert core_http._is_public("169.254.169.254") is False
    assert core_http._is_public("224.0.0.1") is False
    assert core_http._is_public("nonsense") is False
