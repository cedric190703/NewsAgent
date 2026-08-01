"""RSS/Atom provider. Uses the configured feeds and keyword-matches locally."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.search.base import SearchHit, SearchQuery
from app.search.extract import enrich_hits, html_to_text

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


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
        return await enrich_hits(matched[: query.max_results])

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
        return SearchHit(
            url=link,
            title=title,
            source_name=feed_title,
            published_at=_parse_date(published),
            snippet=text[:1200],
            content=text,
            image_url=image,
            provider=self.name,
        )

    def _filter(self, hits: list[SearchHit], query: SearchQuery) -> list[SearchHit]:
        terms = {t.lower() for t in query.query.split() if len(t) > 2}
        scored: list[tuple[float, SearchHit]] = []
        for hit in hits:
            if not _within_window(hit.published_at, query):
                continue
            haystack = f"{hit.title} {hit.snippet}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            if terms and overlap == 0:
                continue
            scored.append((overlap / max(len(terms), 1), hit))

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
