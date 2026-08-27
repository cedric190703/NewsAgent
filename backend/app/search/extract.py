"""Best-effort article body extraction for providers that return only snippets.

Two things matter here beyond "turn HTML into text":

1. *Scoping*. A raw tag-strip drags in nav bars, cookie banners and footers,
   which poison relevance scoring and give the summarizer junk to quote. When
   the page marks its content with `<article>` / `<main>`, we use only that.
2. *Not re-fetching*. The same URL can surface from several providers and
   several sub-topics in one run, so extraction results are cached per URL.
"""

from __future__ import annotations

import asyncio
import re
from html import unescape

from app.core.cache import TTLCache
from app.core.config import settings
from app.core.http import fetch
from app.core.logging import get_logger
from app.search.base import SearchHit

log = get_logger(__name__)

_SCRIPT_RE = re.compile(
    r"<(script|style|noscript|svg|template|iframe|form)[^>]*>.*?</\1>", re.I | re.S
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_CHROME_RE = re.compile(r"<(nav|header|footer|aside)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_BLOCK_RE = re.compile(r"</(p|div|section|article|li|h[1-6]|br)\s*/?>", re.I)
_OG_IMAGE_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.I | re.S)
_MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.I | re.S)

# (text, image_url) keyed by URL.
_article_cache: TTLCache[tuple[str, str | None]] = TTLCache(
    settings.article_cache_ttl_seconds, max_entries=1024
)


def _main_content(html: str) -> str:
    """Prefer the page's own content landmark; fall back to the whole document."""

    for pattern in (_ARTICLE_RE, _MAIN_RE):
        matches = pattern.findall(html)
        if matches:
            best = max(matches, key=len)
            # A tiny <article> is usually a teaser card, not the story.
            if len(best) > 500:
                return best
    return html


def html_to_text(html: str, *, scope_to_content: bool = False) -> str:
    cleaned = _COMMENT_RE.sub(" ", html)
    cleaned = _SCRIPT_RE.sub(" ", cleaned)
    if scope_to_content:
        cleaned = _main_content(cleaned)
    cleaned = _CHROME_RE.sub(" ", cleaned)
    cleaned = _BLOCK_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.split("\n"))
    return _NEWLINES_RE.sub("\n\n", cleaned).strip()


def find_og_image(html: str) -> str | None:
    match = _OG_IMAGE_RE.search(html)
    return match.group(1) if match else None


async def _download_article(url: str) -> tuple[str, str | None]:
    """Return (text, image_url). Empty text means extraction failed."""

    try:
        response = await fetch(url)
        response.raise_for_status()
    except Exception as exc:
        log.debug("extract failed", extra={"url": url, "error": type(exc).__name__})
        return "", None

    if "html" not in response.headers.get("content-type", "text/html").lower():
        return "", None
    if len(response.content) > settings.max_download_bytes:
        return "", None

    try:
        html = response.text
    except (UnicodeDecodeError, LookupError):
        return "", None

    text = html_to_text(html, scope_to_content=True)[: settings.max_article_chars]
    return text, find_og_image(html)


async def fetch_article(url: str) -> tuple[str, str | None]:
    """Cached, single-flight article download."""

    return await _article_cache.get_or_load(url, lambda: _download_article(url))


async def enrich_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """Fill in missing `content` for hits by fetching the article page."""

    if not settings.enable_article_extraction:
        return hits

    targets = [hit for hit in hits if len(hit.content) < settings.min_content_chars]
    if not targets:
        return hits

    results = await asyncio.gather(
        *(fetch_article(hit.url) for hit in targets),
        return_exceptions=True,
    )

    enriched = 0
    for hit, result in zip(targets, results, strict=True):
        if isinstance(result, BaseException):
            continue
        text, image = result
        if len(text) > len(hit.content):
            hit.content = text[: settings.max_article_chars]
            enriched += 1
        if image and not hit.image_url:
            hit.image_url = image

    log.debug("enriched hits", extra={"attempted": len(targets), "enriched": enriched})
    return hits
