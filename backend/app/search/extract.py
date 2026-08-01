"""Best-effort article body extraction for providers that return only snippets."""

from __future__ import annotations

import asyncio
import re
from html import unescape

import httpx

from app.core.config import settings

_SCRIPT_RE = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_BLOCK_RE = re.compile(r"</(p|div|section|article|li|h[1-6])>", re.I)
_OG_IMAGE_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)


def html_to_text(html: str) -> str:
    cleaned = _SCRIPT_RE.sub(" ", html)
    cleaned = _BLOCK_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.split("\n"))
    return _NEWLINES_RE.sub("\n\n", cleaned).strip()


def find_og_image(html: str) -> str | None:
    match = _OG_IMAGE_RE.search(html)
    return match.group(1) if match else None


async def fetch_article(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, str | None]:
    """Return (text, image_url). Empty text means extraction failed."""

    try:
        response = await client.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": settings.http_user_agent},
        )
        response.raise_for_status()
    except (httpx.HTTPError, UnicodeDecodeError):
        return "", None

    if "html" not in response.headers.get("content-type", "text/html"):
        return "", None

    html = response.text
    return html_to_text(html)[: settings.max_article_chars], find_og_image(html)


async def enrich_hits(hits: list, limit_chars: int | None = None) -> list:
    """Fill in missing `content` for hits by fetching the article page."""

    if not settings.enable_article_extraction:
        return hits

    targets = [hit for hit in hits if len(hit.content) < settings.min_content_chars]
    if not targets:
        return hits

    timeout = httpx.Timeout(settings.source_fetch_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(
            *(fetch_article(client, hit.url) for hit in targets),
            return_exceptions=True,
        )

    for hit, result in zip(targets, results):
        if isinstance(result, BaseException):
            continue
        text, image = result
        if len(text) > len(hit.content):
            hit.content = text[: limit_chars or settings.max_article_chars]
        if image and not hit.image_url:
            hit.image_url = image

    return hits
