"""Provider selection: real providers whenever credentials exist, mock otherwise."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from app.core.config import settings
from app.search.base import SearchHit, SearchProvider, SearchQuery
from app.search.mock import MockProvider
from app.search.newsapi import NewsApiProvider
from app.search.rss import RssProvider, dynamic_feed_urls
from app.search.tavily import TavilyProvider


def _build(name: str, extra_feeds: list[str] | None = None) -> SearchProvider | None:
    if name == "tavily" and settings.tavily_api_key:
        return TavilyProvider(settings.tavily_api_key)
    if name == "newsapi" and settings.newsapi_key:
        return NewsApiProvider(settings.newsapi_key)
    if name == "rss":
        feeds = list(settings.rss_feeds)
        if extra_feeds:
            feeds.extend(extra_feeds)
        if feeds:
            return RssProvider(feeds)
    if name == "mock":
        return MockProvider()
    return None


@lru_cache
def available_provider_names() -> tuple[str, ...]:
    names = [n for n in ("tavily", "newsapi", "rss") if _build(n) is not None]
    return tuple(names) or ("mock",)


def get_providers(
    requested: list[str] | None = None,
    theme: str = "",
    custom_feeds: list[str] | None = None,
) -> list[SearchProvider]:
    """Resolve provider names to instances.

    `requested` empty or ["auto"] -> every configured real provider, else mock.
    `theme` is used to generate dynamic Google News search RSS feeds.
    `custom_feeds` are extra RSS URLs provided by the user.
    """

    names = list(requested or [])
    if not names or names == ["auto"]:
        names = list(settings.search_providers)
    if not names or names == ["auto"]:
        names = list(available_provider_names())

    # Build extra feeds: dynamic theme-based + user-provided
    extra_feeds: list[str] = []
    if theme:
        extra_feeds.extend(dynamic_feed_urls(theme))
    if custom_feeds:
        extra_feeds.extend(custom_feeds)

    providers = [p for p in (_build(name, extra_feeds) for name in names) if p is not None]
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
