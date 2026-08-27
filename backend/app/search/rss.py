"""RSS/Atom provider. Fetches the configured feeds and keyword-matches locally.

Feed downloads are cached and single-flighted (`app.core.cache`): the graph runs
one research branch per sub-topic, and every branch wants the same feeds.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from app.core.cache import TTLCache
from app.core.config import settings
from app.core.http import fetch_text
from app.core.logging import get_logger
from app.core.text import topic_terms
from app.search.base import SearchHit, SearchQuery
from app.search.extract import enrich_hits, html_to_text

log = get_logger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# Parsed feed entries keyed by feed URL, shared across sub-topic branches.
_feed_cache: TTLCache[list[SearchHit]] = TTLCache(settings.feed_cache_ttl_seconds)


class RssProvider:
    name = "rss"

    def __init__(self, feeds: list[str]) -> None:
        self._feeds = feeds

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        if not self._feeds:
            return []

        payloads = await asyncio.gather(
            *(self._entries(feed) for feed in self._feeds),
            return_exceptions=True,
        )

        hits: list[SearchHit] = []
        for feed_url, payload in zip(self._feeds, payloads, strict=True):
            if isinstance(payload, BaseException):
                log.debug(
                    "feed failed",
                    extra={"feed": feed_url, "error": type(payload).__name__},
                )
                continue
            hits.extend(payload)

        matched = self._filter(hits, query)[: query.max_results]
        # Copy before enrichment so cached feed entries are never mutated.
        return await enrich_hits([hit.model_copy(deep=True) for hit in matched])

    async def _entries(self, feed_url: str) -> list[SearchHit]:
        return await _feed_cache.get_or_load(
            feed_url, lambda: self._load_feed(feed_url)
        )

    async def _load_feed(self, feed_url: str) -> list[SearchHit]:
        xml_text = await fetch_text(feed_url)
        if not xml_text:
            return []
        return self._parse(xml_text, feed_url)

    def _parse(self, xml_text: str, feed_url: str) -> list[SearchHit]:
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            log.debug("feed parse error", extra={"feed": feed_url})
            return []

        feed_title = (
            root.findtext("./channel/title")
            or root.findtext(f"./{ATOM}title")
            or feed_url
        ).strip()

        entries = root.findall("./channel/item") or root.findall(f"./{ATOM}entry")
        return [
            hit
            for hit in (self._entry_to_hit(entry, feed_title) for entry in entries)
            if hit is not None
        ]

    def _entry_to_hit(self, entry, feed_title: str) -> SearchHit | None:
        title = (entry.findtext("title") or entry.findtext(f"{ATOM}title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        if not link:
            link = self._atom_link(entry)
        if not title or not link:
            return None

        description = (
            entry.findtext(f"{CONTENT}encoded")
            or entry.findtext("description")
            or entry.findtext(f"{ATOM}content")
            or entry.findtext(f"{ATOM}summary")
            or ""
        )
        published = (
            entry.findtext("pubDate")
            or entry.findtext(f"{ATOM}published")
            or entry.findtext(f"{ATOM}updated")
            or entry.findtext("{http://purl.org/dc/elements/1.1/}date")
        )

        text = html_to_text(description)
        return SearchHit(
            url=link,
            title=title,
            source_name=feed_title,
            published_at=_parse_date(published),
            snippet=text[:1200],
            content=text,
            image_url=self._image(entry),
            provider=self.name,
        )

    def _atom_link(self, entry) -> str:
        """Atom entries can carry several <link>s; the alternate one is the article."""

        links = entry.findall(f"{ATOM}link")
        for rel in ("alternate", None):
            for link in links:
                if link.get("rel") == rel or (rel is None and not link.get("rel")):
                    href = link.get("href")
                    if href:
                        return href.strip()
        return (links[0].get("href") or "").strip() if links else ""

    def _image(self, entry) -> str | None:
        for tag in (f"{MEDIA}content", f"{MEDIA}thumbnail"):
            media = entry.find(tag)
            if media is not None and media.get("url"):
                return media.get("url")
        enclosure = entry.find("enclosure")
        if enclosure is not None and "image" in (enclosure.get("type") or ""):
            return enclosure.get("url")
        return None

    def _filter(self, hits: list[SearchHit], query: SearchQuery) -> list[SearchHit]:
        """Rank by keyword overlap, and require the topic terms specifically.

        Matching any word of the query is far too weak: a sub-topic query like
        "climate technology recent breakthroughs" would admit any story
        containing "recent". Topic terms are therefore gated separately, and at
        least half of them must appear.
        """

        terms = {t.lower() for t in query.query.split() if len(t) > 2}
        # Cheap prefilter mirroring the curator's rule: the topic has to be
        # mentioned, not merely one incidental word of the angle. The curator
        # re-checks this against the headline and lede before selecting.
        required = topic_terms(" ".join(query.required_terms))
        needed = min(query.min_required_terms, len(required))

        scored: list[tuple[float, datetime, SearchHit]] = []
        seen: set[str] = set()

        for hit in hits:
            if hit.url in seen or not _within_window(hit.published_at, query):
                continue
            seen.add(hit.url)
            haystack = f"{hit.title} {hit.snippet}".lower()

            if needed and sum(1 for term in required if term in haystack) < needed:
                continue

            overlap = sum(1 for term in terms if term in haystack)
            if terms and overlap == 0:
                continue
            scored.append(
                (overlap / max(len(terms), 1), hit.published_at or _EPOCH, hit)
            )

        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [hit for _, _, hit in scored]


def _within_window(published: datetime | None, query: SearchQuery) -> bool:
    if published is None:
        return True
    if query.date_from and published < _aware(query.date_from):
        return False
    return not (query.date_to and published > _aware(query.date_to))


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
