"""Research node: one parallel branch per sub-topic, real fetches only."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.graph.state import (
    NewsletterState,
    RawArticle,
    ResearchTask,
    RunConfig,
    SubTopic,
    article_id,
    event,
)
from app.search.base import SearchHit, SearchQuery
from app.search.registry import get_providers, multi_search
from app.search.rss import dynamic_feed_urls, fetch_article_url

NODE = "research"
WIDEN_NODE = "widen_queries"


def _to_article(hit: SearchHit, subtopic_id: str) -> RawArticle | None:
    if not hit.url.startswith(("http://", "https://")) or not hit.title.strip():
        return None
    return RawArticle(
        id=article_id(hit.url),
        subtopic_id=subtopic_id,
        url=hit.url,
        title=hit.title.strip(),
        source_name=hit.source_name.strip() or "unknown",
        published_at=hit.published_at,
        snippet=hit.snippet.strip(),
        content=hit.content.strip(),
        image_url=hit.image_url,
        provider=hit.provider,
    )


async def research_node(task: ResearchTask) -> dict[str, Any]:
    """Runs concurrently: LangGraph dispatches one of these per sub-topic."""

    config: RunConfig = task["config"]
    subtopic: SubTopic = task["subtopic"]
    providers = get_providers(
        config.providers,
        theme=subtopic.theme or config.theme,
        custom_feeds=config.custom_feeds,
    )

    query = SearchQuery(
        query=subtopic.query,
        theme=subtopic.theme or config.theme,
        max_results=settings.results_per_subtopic,
        date_from=config.date_from,
        date_to=config.date_to,
    )

    try:
        hits = await multi_search(providers, query)
    except Exception as exc:  # provider-level failure must not kill the run
        hits = []

    # Fetch custom article URLs provided by the user
    custom_hits: list[SearchHit] = []
    if config.custom_urls:
        timeout = httpx.Timeout(settings.source_fetch_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            results = await asyncio.gather(
                *(fetch_article_url(url, client) for url in config.custom_urls),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, SearchHit):
                    custom_hits.append(r)

    all_hits = hits + custom_hits

    articles: dict[str, RawArticle] = {}
    for hit in all_hits:
        article = _to_article(hit, subtopic.id)
        if article is None:
            continue
        existing = articles.get(article.id)
        if existing is None or len(article.body) > len(existing.body):
            articles[article.id] = article

    found = list(articles.values())
    provider_names = ",".join(p.name for p in providers)
    if custom_hits:
        provider_names += ",custom_url"
    return {
        "raw_articles": found,
        "events": [
            event(
                NODE,
                "done",
                branch=subtopic.id,
                detail=f"{subtopic.label}: {len(found)} articles via {provider_names}",
                counts={"articles": len(found), "hits": len(all_hits)},
            )
        ],
    }


async def widen_queries_node(state: NewsletterState) -> dict[str, Any]:
    """Conditional retry: broaden the queries before searching again."""

    config: RunConfig = state["config"]
    attempts = state.get("search_attempts", 0)

    widened: list[SubTopic] = []
    for subtopic in state.get("subtopics", []):
        if subtopic.widened:
            widened.append(subtopic)
            continue
        stripped = " ".join(subtopic.query.split()[:4])
        widened.append(
            subtopic.model_copy(
                update={
                    "query": f"{stripped} {subtopic.theme or config.theme}".strip(),
                    "widened": True,
                    "rationale": f"{subtopic.rationale} (widened after thin results)".strip(),
                }
            )
        )

    return {
        "subtopics": widened,
        "search_attempts": attempts + 1,
        "events": [
            event(
                WIDEN_NODE,
                "done",
                detail=f"Broadened {len(widened)} queries for attempt {attempts + 1}",
                counts={"attempt": attempts + 1},
            )
        ],
    }
