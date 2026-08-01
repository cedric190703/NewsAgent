"""Provider selection: real providers whenever credentials exist, mock otherwise."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.config import settings
from app.search.base import SearchHit, SearchProvider, SearchQuery
from app.search.mock import MockProvider
from app.search.newsapi import NewsApiProvider
from app.search.rss import RssProvider
from app.search.tavily import TavilyProvider


def _build(name: str) -> SearchProvider | None:
    if name == "tavily" and settings.tavily_api_key:
        return TavilyProvider(settings.tavily_api_key)
    if name == "newsapi" and settings.newsapi_key:
        return NewsApiProvider(settings.newsapi_key)
    if name == "rss" and settings.rss_feeds:
        return RssProvider(settings.rss_feeds)
    if name == "mock":
        return MockProvider()
    return None


@lru_cache
def available_provider_names() -> tuple[str, ...]:
    names = [n for n in ("tavily", "newsapi", "rss") if _build(n) is not None]
    return tuple(names) or ("mock",)


def get_providers(requested: list[str] | None = None) -> list[SearchProvider]:
    """Resolve provider names to instances.

    `requested` empty or ["auto"] -> every configured real provider, else mock.
    """

    names = list(requested or [])
    if not names or names == ["auto"]:
        names = list(settings.search_providers)
    if not names or names == ["auto"]:
        names = list(available_provider_names())

    providers = [p for p in (_build(name) for name in names) if p is not None]
    return providers or [MockProvider()]


async def multi_search(
    providers: list[SearchProvider],
    query: SearchQuery,
) -> list[SearchHit]:
    """Query every provider concurrently and flatten the results."""

    results = await asyncio.gather(
        *(provider.search(query) for provider in providers),
        return_exceptions=True,
    )

    hits: list[SearchHit] = []
    for result in results:
        if isinstance(result, BaseException):
            continue
        hits.extend(result)
    return hits
