"""Provider selection: real providers whenever credentials exist, mock otherwise."""

from __future__ import annotations

import asyncio
import time
from functools import cache, lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.search.base import SearchHit, SearchProvider, SearchQuery
from app.search.mock import MockProvider
from app.search.newsapi import NewsApiProvider
from app.search.rss import RssProvider
from app.search.tavily import TavilyProvider

log = get_logger(__name__)

KNOWN_PROVIDERS = ("tavily", "newsapi", "rss", "mock")


@cache
def build_provider(name: str) -> SearchProvider | None:
    """Cached per name: providers are stateless handles, one instance is enough."""

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
    """Every real provider that is actually configured, else ("mock",)."""

    names = [n for n in ("tavily", "newsapi", "rss") if build_provider(n) is not None]
    return tuple(names) or ("mock",)


def resolve_provider_names(requested: list[str] | None = None) -> list[str]:
    names = [n for n in (requested or []) if n]
    if not names or names == ["auto"]:
        names = [n for n in settings.search_providers if n]
    if not names or names == ["auto"]:
        names = list(available_provider_names())
    unknown = [n for n in names if n not in KNOWN_PROVIDERS]
    if unknown:
        log.warning("ignoring unknown providers", extra={"providers": unknown})
    return [n for n in names if n in KNOWN_PROVIDERS]


def get_providers(requested: list[str] | None = None) -> list[SearchProvider]:
    """Resolve provider names to instances.

    `requested` empty or ["auto"] -> every configured real provider, else mock.
    """

    providers = [
        provider
        for provider in (build_provider(name) for name in resolve_provider_names(requested))
        if provider is not None
    ]
    return providers or [MockProvider()]


async def _search_one(
    provider: SearchProvider, query: SearchQuery
) -> tuple[str, list[SearchHit], float]:
    started = time.perf_counter()
    hits = await provider.search(query)
    return provider.name, hits, time.perf_counter() - started


async def multi_search(
    providers: list[SearchProvider],
    query: SearchQuery,
) -> list[SearchHit]:
    """Query every provider concurrently and flatten the results.

    A provider that fails or hangs must not take the run down with it, so each
    one gets its own timeout and its exceptions are logged, not raised.
    """

    timeout = settings.source_fetch_timeout_seconds * 2
    results = await asyncio.gather(
        *(
            asyncio.wait_for(_search_one(provider, query), timeout=timeout)
            for provider in providers
        ),
        return_exceptions=True,
    )

    hits: list[SearchHit] = []
    for provider, result in zip(providers, results, strict=True):
        if isinstance(result, BaseException):
            log.warning(
                "provider failed",
                extra={
                    "provider": provider.name,
                    "query": query.query,
                    "error": type(result).__name__,
                },
            )
            continue
        name, provider_hits, elapsed = result
        log.debug(
            "provider hits",
            extra={
                "provider": name,
                "query": query.query,
                "count": len(provider_hits),
                "seconds": round(elapsed, 2),
            },
        )
        hits.extend(provider_hits)
    return hits
