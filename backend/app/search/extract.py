"""Best-effort article body extraction for providers that return only snippets.

Improves on naive tag-stripping by:
- Removing cookie consent walls, sign-in overlays, and nav/footer boilerplate
- Isolating the main article content area using multiple strategies:
  1. JSON-LD structured data (schema.org Article/NewsArticle)
  2. <article>, <main>, role="main" semantic tags
  3. Common content class/id patterns (expanded)
  4. Data-attribute selectors (data-component, data-role)
  5. Paragraph density scoring (readability-like fallback)
- Detecting and rejecting junk-heavy extracted text
- Better HTTP fetching with browser-like headers and retry on 429/503
"""

from __future__ import annotations

import asyncio
import json
import re
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import settings

_SCRIPT_RE = re.compile(r"<(script|style|noscript|svg|template|iframe)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_BLOCK_RE = re.compile(r"</(p|div|section|article|li|h[1-6]|br)>", re.I)
_OG_IMAGE_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I,
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

# --- junk / boilerplate detection ---

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
    re.compile(r"view (?:original|source)", re.I),
    re.compile(r"get (?:the|our) (?:latest|daily) (?:newsletter|updates?)", re.I),
    re.compile(r"enter your email", re.I),
    re.compile(r"thank you for (?:reading|your interest)", re.I),
    re.compile(r"this (?:article|content|post) is (?:available|for)", re.I),
    re.compile(r"continue reading (?:with|on|at)", re.I),
    re.compile(r"photo (?:by|credit|:)", re.I),
    re.compile(r"getty images", re.I),
    re.compile(r"shutterstock", re.I),
    re.compile(r"bloomberg", re.I),
    re.compile(r"reuters/(?:staff|file)", re.I),
    re.compile(r"reporting by", re.I),
    re.compile(r"editing by", re.I),
    re.compile(r"additional reporting", re.I),
    re.compile(r"writing by", re.I),
]

# HTML blocks to remove entirely (by class/id patterns)
_REMOVE_BLOCK_RE = re.compile(
    r"<(?:div|section|aside|nav|footer|header|form|ul|ol|figure|figcaption)"
    r"[^>]*(?:class|id)=[\"'][^\"']*"
    r"(?:cookie|consent|gdpr|banner|overlay|modal|popup|sidebar|footer|header|nav-"
    r"|menu|breadcrumb|social|share|comment|related|recommend|advert|promo|newsletter"
    r"|subscribe|signup|sign-in|signin|login|paywall|metered|subscribe-wall|sticky"
    r"|toolbar|outbrain|taboola|zergnet|disqus|comments)"
    r"[^\"']*[\"'][^>]*>.*?</(?:div|section|aside|nav|footer|header|form|ul|ol|figure|figcaption)>",
    re.I | re.S,
)

# Try to find <article> or <main> or role="main" content
_ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.I | re.S)
_MAIN_RE = re.compile(r"<main[^>]*>(.*?)</main>", re.I | re.S)
_ROLE_MAIN_RE = re.compile(r"<(?:div|section)[^>]*role=[\"']main[\"'][^>]*>(.*?)</(?:div|section)>", re.I | re.S)

# Common content class patterns — expanded with many more site-specific patterns
_CONTENT_CLASS_RE = re.compile(
    r"<(?:div|article|section)[^>]*(?:class|id)=[\"'][^\"']*"
    r"(?:article-body|article-content|post-content|entry-content|story-body|"
    r"content-body|article-text|article__body|story-content|main-content|"
    r"page-content|prose|article-detail|article__content|story__body|"
    r"post__content|entry__content|content__body|rich-text|"
    r"article-copy|article-main|article-text__body|story-body-text|"
    r"post-body|post-text|article__text|content-article|article-layout|"
    r"news-body|news-content|story-wrap|content-wrap|"
    r"body-text|main-text|article-frame|"
    r"gutenberg-content|wp-block-post-content|elementor-post__content)"
    r"[^\"']*[\"'][^>]*>(.*?)</(?:div|article|section)>",
    re.I | re.S,
)

# Data-attribute based selectors for modern JS frameworks
_DATA_CONTENT_RE = re.compile(
    r"<(?:div|article|section)[^>]*data-(?:component|role|test-id|qa)=[\"']"
    r"(?:article-body|article-content|story-body|post-content|content-body|main-content)"
    r"[\"'][^>]*>(.*?)</(?:div|article|section)>",
    re.I | re.S,
)


def _strip_junk_blocks(html: str) -> str:
    """Remove cookie walls, nav, footer, sidebar blocks from HTML."""
    html = _REMOVE_BLOCK_RE.sub(" ", html)
    return html


def _extract_json_ld_article(html: str) -> str | None:
    """Try to extract article body from JSON-LD structured data."""
    for match in _JSON_LD_RE.finditer(html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        # Handle @graph arrays
        if isinstance(data, dict) and "@graph" in data:
            for item in data["@graph"]:
                if isinstance(item, dict) and item.get("@type") in ("Article", "NewsArticle", "BlogPosting", "TechArticle"):
                    body = item.get("articleBody") or item.get("text") or ""
                    if body and len(body) > 200:
                        return body
        elif isinstance(data, dict):
            atype = data.get("@type", "")
            if atype in ("Article", "NewsArticle", "BlogPosting", "TechArticle") or (
                isinstance(atype, list) and any(t in ("Article", "NewsArticle", "BlogPosting", "TechArticle") for t in atype)
            ):
                body = data.get("articleBody") or data.get("text") or ""
                if body and len(body) > 200:
                    return body
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") in ("Article", "NewsArticle", "BlogPosting", "TechArticle"):
                    body = item.get("articleBody") or item.get("text") or ""
                    if body and len(body) > 200:
                        return body
    return None


def _extract_main_content(html: str) -> str:
    """Try to isolate the main article content from the page."""
    # 1. Try JSON-LD structured data first (most reliable)
    json_ld_text = _extract_json_ld_article(html)
    if json_ld_text:
        return json_ld_text

    # 2. Try <article>
    match = _ARTICLE_RE.search(html)
    if match:
        return match.group(1)

    # 3. Try <main>
    match = _MAIN_RE.search(html)
    if match:
        return match.group(1)

    # 4. Try role="main"
    match = _ROLE_MAIN_RE.search(html)
    if match:
        return match.group(1)

    # 5. Try common content class patterns
    match = _CONTENT_CLASS_RE.search(html)
    if match:
        return match.group(1)

    # 6. Try data-attribute selectors
    match = _DATA_CONTENT_RE.search(html)
    if match:
        return match.group(1)

    # 7. Fallback: paragraph density scoring
    best = _paragraph_density_select(html)
    if best:
        return best

    # 8. Last resort: return the whole HTML
    return html


def _paragraph_density_select(html: str) -> str | None:
    """Select the div/section with the highest paragraph text density."""
    # Find all div/section blocks with their content
    block_re = re.compile(
        r"<(div|section)[^>]*>(.*?)</\1>",
        re.I | re.S,
    )
    best_text = None
    best_score = 0

    for match in block_re.finditer(html):
        inner = match.group(2)
        # Skip if inner is too large (likely the whole page wrapper)
        if len(inner) > len(html) * 0.9:
            continue
        # Count <p> tags and measure text
        p_count = len(re.findall(r"<p[^>]*>", inner, re.I))
        # Quick text extraction
        text = _TAG_RE.sub(" ", inner)
        text = unescape(text)
        text = _WS_RE.sub(" ", text).strip()
        text_len = len(text)

        # Skip tiny blocks
        if text_len < 500:
            continue

        # Score: paragraph count * text length, penalize if too many links
        link_count = len(re.findall(r"<a[^>]*href", inner, re.I))
        link_penalty = min(0.5, link_count / max(p_count, 1) * 0.1)
        score = p_count * text_len * (1 - link_penalty)

        if score > best_score:
            best_score = score
            best_text = inner

    return best_text


def _is_junk_line(line: str) -> bool:
    """Check if a line is boilerplate/junk."""
    stripped = line.strip()
    if not stripped or len(stripped) < 3:
        return True

    # Short lines that match junk patterns
    if len(stripped) < 150:
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

    # First, strip script/style/svg/template/iframe blocks
    html = _SCRIPT_RE.sub(" ", html)

    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)

    # Remove known junk blocks (cookie walls, nav, footer, etc.)
    html = _strip_junk_blocks(html)

    # Try to isolate the main article content
    html = _extract_main_content(html)

    # If we got JSON-LD text (already plain text), return it directly
    if "<" not in html:
        text = html
    else:
        # Convert to text
        cleaned = _BLOCK_RE.sub("\n", html)
        cleaned = _TAG_RE.sub(" ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = _WS_RE.sub(" ", cleaned)
        cleaned = "\n".join(line.strip() for line in cleaned.split("\n"))
        text = cleaned

    # Filter out junk lines
    lines = [line for line in text.split("\n") if not _is_junk_line(line)]
    text = "\n".join(lines)

    text = _NEWLINES_RE.sub("\n\n", text).strip()
    return text


def find_og_image(html: str) -> str | None:
    match = _OG_IMAGE_RE.search(html)
    return match.group(1) if match else None


# Browser-like headers to avoid being blocked
_BROWSER_HEADERS = {
    "User-Agent": settings.http_user_agent,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


async def fetch_article(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, str | None]:
    """Return (text, image_url). Empty text means extraction failed."""

    try:
        response = await client.get(
            url,
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
        )
        # Retry on 429 (rate limit) or 503 (service unavailable) with backoff
        if response.status_code in (429, 503):
            await asyncio.sleep(2)
            response = await client.get(
                url,
                follow_redirects=True,
                headers=_BROWSER_HEADERS,
            )
        response.raise_for_status()
    except (httpx.HTTPError, UnicodeDecodeError):
        return "", None

    content_type = response.headers.get("content-type", "text/html")
    if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
        return "", None

    html = response.text
    text = html_to_text(html)

    # Reject if the text is mostly junk
    if len(text) > 200:
        ratio = _junk_ratio(text)
        if ratio > 0.6:
            return "", None

    return text[: settings.max_article_chars], find_og_image(html)


# Semaphore to limit concurrent fetches
_FETCH_SEMAPHORE = asyncio.Semaphore(10)


async def enrich_hits(hits: list, limit_chars: int | None = None) -> list:
    """Fill in missing `content` for hits by fetching the article page."""

    if not settings.enable_article_extraction:
        return hits

    targets = [hit for hit in hits if len(hit.content) < settings.min_content_chars]
    if not targets:
        return hits

    timeout = httpx.Timeout(settings.source_fetch_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:

        async def _limited_fetch(hit):
            async with _FETCH_SEMAPHORE:
                return await fetch_article(client, hit.url)

        results = await asyncio.gather(
            *(_limited_fetch(hit) for hit in targets),
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
