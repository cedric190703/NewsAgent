"""Best-effort article body extraction for providers that return only snippets.

Improves on naive tag-stripping by:
- Removing cookie consent walls, sign-in overlays, and nav/footer boilerplate
- Attempting to isolate the main article content area
- Detecting and rejecting junk-heavy extracted text
"""

from __future__ import annotations

import asyncio
import re
from html import unescape

import httpx

from app.core.config import settings

_SCRIPT_RE = re.compile(r"<(script|style|noscript|svg|template)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_BLOCK_RE = re.compile(r"</(p|div|section|article|li|h[1-6])>", re.I)
_OG_IMAGE_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)

# --- junk / boilerplate detection ---

# Patterns that indicate cookie walls, consent banners, sign-in overlays
_JUNK_PATTERNS = [
    re.compile(r"before you continue.*?sign in", re.I | re.S),
    re.compile(r"we use cookies and data.*?reject all", re.I | re.S),
    re.compile(r"deliver and maintain google services", re.I),
    re.compile(r"track outages and protect against spam", re.I),
    re.compile(r"measure audience engagement and site statistics", re.I),
    re.compile(r"non-personalized (?:content|ads) is influenced by", re.I),
    re.compile(r"if you choose to .{0,20}(?:accept all|reject all)", re.I | re.S),
    re.compile(r"sign in to (?:google|your account|continue)", re.I),
    re.compile(r"by using (?:this|our) (?:site|website).*?you (?:agree|consent)", re.I | re.S),
    re.compile(r"this site uses cookies.*?continue", re.I | re.S),
    re.compile(r"consent to (?:the use of|our use of) cookies", re.I),
    re.compile(r"manage (?:your )?(?:privacy )?(?:choices|preferences|settings)", re.I),
    re.compile(r"do not sell (or share )?my (?:personal )?information", re.I),
    re.compile(r"privacy (?:policy|notice|center)", re.I),
    re.compile(r"terms of (?:service|use|condition)", re.I),
    re.compile(r"accept (?:all )?cookies", re.I),
    re.compile(r"cookie (?:settings|preferences|consent|banner|notice)", re.I),
    re.compile(r"subscribe (?:to|for|now|today)", re.I),
    re.compile(r"sign up for (?:our |the )?newsletter", re.I),
    re.compile(r"follow us on", re.I),
    re.compile(r"download our app", re.I),
    re.compile(r"related (?:articles|stories|posts|topics)", re.I),
    re.compile(r"read more:", re.I),
    re.compile(r"advertisement", re.I),
    re.compile(r"sponsored content", re.I),
    re.compile(r"promoted (?:by|content|stories)", re.I),
    re.compile(r"most (?:popular|read|viewed|shared)", re.I),
    re.compile(r"trending (?:now|stories|articles)", re.I),
    re.compile(r"you may also like", re.I),
    re.compile(r"recommended (?:for you|stories|articles)", re.I),
    re.compile(r"comments? \(\d+\)", re.I),
    re.compile(r"share this (?:article|story|post)", re.I),
    re.compile(r"click (?:here|to share|to read)", re.I),
    re.compile(r"expand(?:\s+(?:article|story|all))?", re.I),
    re.compile(r"\bsave\b(?!\s+(?:the|this|your)\s+(?:date|spot))", re.I),
]

# HTML blocks to remove entirely (by class/id patterns)
_REMOVE_BLOCK_RE = re.compile(
    r"<(?:div|section|aside|nav|footer|header|form|ul|ol)"
    r"[^>]*(?:class|id)=[\"'][^\"']*"
    r"(?:cookie|consent|gdpr|banner|overlay|modal|popup|sidebar|footer|header|nav-"
    r"|menu|breadcrumb|social|share|comment|related|recommend|advert|promo|newsletter"
    r"|subscribe|signup|sign-in|signin|login|paywall|metered|subscribe-wall)"
    r"[^\"']*[\"'][^>]*>.*?</(?:div|section|aside|nav|footer|header|form|ul|ol)>",
    re.I | re.S,
)

# Try to find <article> or <main> or role="main" content
_ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.I | re.S)
_MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.I | re.S)
_ROLE_MAIN_RE = re.compile(r"<(?:div|section)[^>]*role=[\"']main[\"'][^>]*>(.*?)</(?:div|section)>", re.I | re.S)
# Common content class patterns
_CONTENT_CLASS_RE = re.compile(
    r"<(?:div|article|section)[^>]*(?:class|id)=[\"'][^\"']*"
    r"(?:article-body|article-content|post-content|entry-content|story-body|"
    r"content-body|article-text|article__body|story-content|main-content|"
    r"page-content|prose)"
    r"[^\"']*[\"'][^>]*>(.*?)</(?:div|article|section)>",
    re.I | re.S,
)


def _strip_junk_blocks(html: str) -> str:
    """Remove cookie walls, nav, footer, sidebar blocks from HTML."""
    # Remove blocks matching junk class/id patterns
    html = _REMOVE_BLOCK_RE.sub(" ", html)
    return html


def _extract_main_content(html: str) -> str:
    """Try to isolate the main article content from the page."""
    # Try <article> first
    match = _ARTICLE_RE.search(html)
    if match:
        return match.group(1)

    # Try <main>
    match = _MAIN_RE.search(html)
    if match:
        return match.group(1)

    # Try role="main"
    match = _ROLE_MAIN_RE.search(html)
    if match:
        return match.group(1)

    # Try common content class patterns
    match = _CONTENT_CLASS_RE.search(html)
    if match:
        return match.group(1)

    # Fallback: return the whole HTML
    return html


def _is_junk_line(line: str) -> bool:
    """Check if a line is boilerplate/junk."""
    stripped = line.strip()
    if not stripped or len(stripped) < 3:
        return True

    # Short lines that match junk patterns
    if len(stripped) < 120:
        for pattern in _JUNK_PATTERNS:
            if pattern.search(stripped):
                return True

    return False


def _junk_ratio(text: str) -> float:
    """Estimate what fraction of the text is boilerplate/junk."""
    lines = text.split("\n")
    if not lines:
        return 1.0

    junk_lines = sum(1 for line in lines if _is_junk_line(line))
    total = len(lines)
    return junk_lines / max(total, 1)


def html_to_text(html: str) -> str:
    """Extract readable article text from HTML, filtering boilerplate."""

    # First, strip script/style/svg/template blocks
    html = _SCRIPT_RE.sub(" ", html)

    # Remove known junk blocks (cookie walls, nav, footer, etc.)
    html = _strip_junk_blocks(html)

    # Try to isolate the main article content
    html = _extract_main_content(html)

    # Convert to text
    cleaned = _BLOCK_RE.sub("\n", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.split("\n"))

    # Filter out junk lines
    lines = [line for line in cleaned.split("\n") if not _is_junk_line(line)]
    cleaned = "\n".join(lines)

    cleaned = _NEWLINES_RE.sub("\n\n", cleaned).strip()
    return cleaned


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
    text = html_to_text(html)

    # Reject if the text is mostly junk
    if len(text) > 200:
        ratio = _junk_ratio(text)
        if ratio > 0.6:
            return "", None

    return text[: settings.max_article_chars], find_og_image(html)


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
        # Only replace if the new text is meaningful (not junk)
        if len(text) > len(hit.content) and len(text) >= settings.min_content_chars:
            hit.content = text[: limit_chars or settings.max_article_chars]
        if image and not hit.image_url:
            hit.image_url = image

    return hits
