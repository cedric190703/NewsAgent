from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.schemas.news import NewsQueryRequest, NewsSource, SourceType


class RSSFeedAgent:
    async def fetch(self, request: NewsQueryRequest) -> list[NewsSource]:
        if not settings.rss_feeds:
            return self._fallback_sources(request)

        sources: list[NewsSource] = []
        async with httpx.AsyncClient(timeout=settings.source_fetch_timeout_seconds) as client:
            for feed_url in settings.rss_feeds:
                try:
                    response = await client.get(feed_url)
                    response.raise_for_status()
                    sources.extend(self._parse_feed(response.text, feed_url, request))
                except (httpx.HTTPError, ElementTree.ParseError):
                    continue

        return sources or self._fallback_sources(request)

    def _parse_feed(
        self,
        xml_text: str,
        feed_url: str,
        request: NewsQueryRequest,
    ) -> list[NewsSource]:
        root = ElementTree.fromstring(xml_text)
        channel_title = root.findtext("./channel/title") or "RSS feed"
        items = root.findall("./channel/item")

        parsed_sources: list[NewsSource] = []
        for item in items[: request.depth * 4]:
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip() or None
            published_at = self._parse_date(item.findtext("pubDate"))

            if not title:
                continue

            relevance_score = self._score_relevance(request.topic, f"{title} {description}")
            if relevance_score <= 0.05:
                continue

            parsed_sources.append(
                NewsSource(
                    title=title,
                    url=link,
                    source_type=SourceType.RSS,
                    publisher=channel_title,
                    published_at=published_at,
                    summary=description or None,
                    relevance_score=relevance_score,
                    metadata={"feed_url": feed_url},
                )
            )

        return parsed_sources

    def _score_relevance(self, topic: str, text: str) -> float:
        topic_terms = {term.lower() for term in topic.split() if len(term) > 2}
        text_lower = text.lower()
        if not topic_terms:
            return 0.3

        matches = sum(1 for term in topic_terms if term in text_lower)
        return min(1.0, 0.2 + matches / max(len(topic_terms), 1))

    def _parse_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _fallback_sources(self, request: NewsQueryRequest) -> list[NewsSource]:
        return [
            NewsSource(
                title=f"RSS monitoring placeholder for {request.topic}",
                source_type=SourceType.RSS,
                publisher="Configured RSS feeds",
                published_at=datetime.now(timezone.utc),
                summary=(
                    "RSS ingestion is ready as an agent boundary. Add feedparser "
                    "and configured feeds to collect live articles."
                ),
                relevance_score=0.75,
            )
        ]
