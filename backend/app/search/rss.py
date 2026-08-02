"""RSS/Atom provider. Uses the configured feeds and keyword-matches locally."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlsplit
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.search.base import SearchHit, SearchQuery
from app.search.extract import enrich_hits, html_to_text

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def dynamic_feed_urls(theme: str) -> list[str]:
    """Generate Google News search RSS URLs based on the theme.

    These act as a free search engine — Google returns articles matching
    the keywords, packaged as RSS.
    """
    base = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    # Clean theme into search keywords
    keywords = theme.strip().lower()
    urls = [
        base.format(q=quote_plus(keywords)),
        base.format(q=quote_plus(f"{keywords} breakthrough")),
        base.format(q=quote_plus(f"{keywords} latest news")),
    ]
    return urls


async def fetch_article_url(url: str, client: httpx.AsyncClient) -> SearchHit | None:
    """Fetch a direct article URL and extract a SearchHit from the HTML."""
    try:
        response = await client.get(url, follow_redirects=True, headers={
            "User-Agent": "NewsAgent/0.2 (+https://github.com/)",
        })
        if response.status_code != 200:
            return None
        text = html_to_text(response.text)
        if not text or len(text) < 100:
            return None
        # Try to extract title from HTML
        title = ""
        for prefix in ("<title>", "<TITLE>"):
            start = response.text.find(prefix)
            if start != -1:
                end = response.text.find("</title>" if prefix == "<title>" else "</TITLE>", start)
                if end != -1:
                    title = response.text[start + len(prefix):end].strip()
                    break
        if not title:
            title = url[:80]
        return SearchHit(
            url=url,
            title=title,
            source_name=urlsplit(url).netloc,
            snippet=text[:1200],
            content=text,
            provider="custom_url",
        )
    except Exception:
        return None


class RssProvider:
    name = "rss"

    def __init__(self, feeds: list[str]) -> None:
        self._feeds = feeds

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        if not self._feeds:
            return []

        timeout = httpx.Timeout(settings.source_fetch_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            payloads = await asyncio.gather(
                *(self._fetch(client, feed) for feed in self._feeds),
                return_exceptions=True,
            )

        hits: list[SearchHit] = []
        for feed_url, payload in zip(self._feeds, payloads):
            if isinstance(payload, BaseException) or not payload:
                continue
            hits.extend(self._parse(payload, feed_url))

        matched = self._filter(hits, query)
        return await enrich_hits(matched[: query.max_results * 3])

    async def _fetch(self, client: httpx.AsyncClient, feed_url: str) -> str | None:
        try:
            response = await client.get(
                feed_url,
                follow_redirects=True,
                headers={"User-Agent": settings.http_user_agent},
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            return None

    def _parse(self, xml_text: str, feed_url: str) -> list[SearchHit]:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return []

        feed_title = (
            root.findtext("./channel/title")
            or root.findtext(f"./{ATOM}title")
            or feed_url
        ).strip()

        entries = root.findall("./channel/item") or root.findall(f"./{ATOM}entry")
        hits: list[SearchHit] = []
        for entry in entries:
            hit = self._entry_to_hit(entry, feed_title)
            if hit:
                hits.append(hit)
        return hits

    def _entry_to_hit(self, entry, feed_title: str) -> SearchHit | None:
        title = (entry.findtext("title") or entry.findtext(f"{ATOM}title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        if not link:
            link_el = entry.find(f"{ATOM}link")
            link = (link_el.get("href") if link_el is not None else "") or ""
        if not title or not link:
            return None

        description = (
            entry.findtext("description")
            or entry.findtext(f"{ATOM}summary")
            or entry.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            or ""
        )
        published = (
            entry.findtext("pubDate")
            or entry.findtext(f"{ATOM}published")
            or entry.findtext(f"{ATOM}updated")
        )

        image = None
        media = entry.find(f"{MEDIA}content") or entry.find(f"{MEDIA}thumbnail")
        if media is not None:
            image = media.get("url")
        if image is None:
            enclosure = entry.find("enclosure")
            if enclosure is not None and "image" in (enclosure.get("type") or ""):
                image = enclosure.get("url")

        text = html_to_text(description)

        # Extract real source name — Google News wraps articles but includes
        # the original source in <source> or in the title after " - "
        source_name = feed_title
        source_el = entry.find("source")
        if source_el is not None and source_el.text:
            source_name = source_el.text.strip()
        elif " - " in title:
            # Title format from Google News: "Article Title - Source Name"
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2 and len(parts[1]) < 80:
                source_name = parts[1].strip()

        return SearchHit(
            url=link,
            title=title,
            source_name=source_name,
            published_at=_parse_date(published),
            snippet=text[:1200],
            content=text,
            image_url=image,
            provider=self.name,
        )

    def _filter(self, hits: list[SearchHit], query: SearchQuery) -> list[SearchHit]:
        from app.graph.theme_match import (
            extract_theme_terms,
            theme_match_count,
            theme_matches,
            theme_matches_both_concepts,
            _concept_groups,
        )

        theme = query.theme or query.query
        groups = _concept_groups(theme)

        if len(groups) >= 2:
            # Multi-concept: require both concepts to match
            scored = [
                (theme_match_count(f"{h.title} {h.snippet}", extract_theme_terms(theme)), h)
                for h in hits
                if _within_window(h.published_at, query)
                and theme_matches_both_concepts(f"{h.title} {h.snippet}", theme)
            ]
        else:
            # Single concept: match any term
            theme_terms = extract_theme_terms(theme)
            if not theme_terms:
                return hits[: query.max_results * 3]
            scored = []
            for h in hits:
                if not _within_window(h.published_at, query):
                    continue
                haystack = f"{h.title} {h.snippet}"
                if not theme_matches(haystack, theme_terms):
                    continue
                scored.append((theme_match_count(haystack, theme_terms), h))

        scored.sort(key=lambda pair: (pair[0], pair[1].published_at or _EPOCH), reverse=True)
        return [hit for _, hit in scored]


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _within_window(published: datetime | None, query: SearchQuery) -> bool:
    if published is None:
        return True
    if query.date_from and published < _aware(query.date_from):
        return False
    if query.date_to and published > _aware(query.date_to):
        return False
    return True


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return _aware(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None
