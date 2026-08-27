"""Tavily news search provider."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.http import fetch
from app.core.logging import get_logger
from app.search.base import SearchHit, SearchQuery

log = get_logger(__name__)

API_URL = "https://api.tavily.com/search"


class TavilyProvider:
    name = "tavily"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        payload: dict[str, object] = {
            "query": query.query,
            "topic": "news",
            "search_depth": settings.tavily_search_depth,
            "max_results": query.max_results,
            "include_raw_content": True,
            "include_images": False,
        }
        days = self._days_window(query)
        if days is not None:
            payload["days"] = days

        try:
            response = await fetch(
                API_URL,
                method="POST",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            log.warning("tavily search failed", extra={"error": type(exc).__name__})
            return []

        hits = [hit for hit in map(self._to_hit, data.get("results", [])) if hit]
        log.debug("tavily hits", extra={"query": query.query, "count": len(hits)})
        return hits

    def _days_window(self, query: SearchQuery) -> int | None:
        if query.date_from is None:
            return None
        reference = query.date_to or datetime.now(timezone.utc)
        delta = _aware(reference) - _aware(query.date_from)
        return max(1, min(365, delta.days))

    def _to_hit(self, item: dict) -> SearchHit | None:
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            return None

        content = item.get("raw_content") or item.get("content") or ""
        return SearchHit(
            url=url,
            title=title,
            source_name=_domain(url),
            published_at=_parse_iso(item.get("published_date")),
            snippet=(item.get("content") or "")[:1200],
            content=content[: settings.max_article_chars],
            provider=self.name,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return _aware(parsed)
