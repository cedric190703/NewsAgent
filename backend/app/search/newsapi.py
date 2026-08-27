"""NewsAPI.org provider. Returns descriptions only, so bodies are back-filled."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.core.http import fetch
from app.core.logging import get_logger
from app.search.base import SearchHit, SearchQuery
from app.search.extract import enrich_hits

log = get_logger(__name__)

API_URL = "https://newsapi.org/v2/everything"


class NewsApiProvider:
    name = "newsapi"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        params: dict[str, str | int] = {
            "q": query.query,
            "pageSize": min(query.max_results, 100),
            "sortBy": "publishedAt",
            "language": settings.newsapi_language,
        }
        if query.date_from:
            params["from"] = _iso_day(query.date_from)
        if query.date_to:
            params["to"] = _iso_day(query.date_to)

        try:
            response = await fetch(
                API_URL,
                params=params,
                headers={"X-Api-Key": self._api_key},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            log.warning("newsapi search failed", extra={"error": type(exc).__name__})
            return []

        if data.get("status") == "error":
            log.warning("newsapi error", extra={"message": data.get("message", "")[:200]})
            return []

        hits = [hit for hit in map(self._to_hit, data.get("articles", [])) if hit]
        return await enrich_hits(hits)

    def _to_hit(self, item: dict) -> SearchHit | None:
        url = item.get("url")
        title = item.get("title")
        if not url or not title or title == "[Removed]":
            return None

        source = (item.get("source") or {}).get("name") or ""
        description = item.get("description") or ""
        return SearchHit(
            url=url,
            title=title,
            source_name=source,
            published_at=_parse_iso(item.get("publishedAt")),
            snippet=description,
            content=(item.get("content") or description),
            image_url=item.get("urlToImage"),
            provider=self.name,
        )


def _iso_day(value: datetime) -> str:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
