"""Curator node: score, rank and select. Heuristics first, LLM refines."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.graph.llm import try_json
from app.graph.scoring import (
    MODE_WEIGHTS,
    composite_score,
    credibility_score,
    explain,
    recency_score,
    relevance_score,
    signal_score,
    valence_score,
)
from app.graph.state import (
    ArticleScores,
    NewsletterState,
    RawArticle,
    RunConfig,
    ScoredArticle,
    SubTopic,
    event,
)
from app.providers.base import LLMProvider

NODE = "curator"
BATCH_SIZE = 5

SYSTEM = (
    "You are a strict news curator. You judge only the text provided. "
    "You never add information that is not in the text."
)

RUBRIC = (
    "Score each item from 0.0 to 1.0 on three independent axes:\n"
    "- relevance: does it actually address the theme and angle?\n"
    "- valence: is the OUTCOME described constructive (progress, solutions, "
    "recovery, wins)? 0.0 = purely bad news, 0.5 = neutral, 1.0 = clearly good.\n"
    "- signal: is it substantive journalism (specific, sourced, verifiable, "
    "low hype)? Penalise clickbait, listicles, rage-bait, press-release fluff."
)


class CuratorItem(BaseModel):
    id: str
    relevance: float = Field(ge=0.0, le=1.0)
    valence: float = Field(ge=0.0, le=1.0)
    signal: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=200)


class CuratorBatch(BaseModel):
    items: list[CuratorItem] = Field(default_factory=list)


async def _score_batch(
    provider: LLMProvider,
    config: RunConfig,
    subtopic_by_id: dict[str, SubTopic],
    batch: list[RawArticle],
) -> dict[str, CuratorItem]:
    lines = []
    for article in batch:
        subtopic = subtopic_by_id.get(article.subtopic_id)
        lines.append(
            f"---\nid: {article.id}\n"
            f"angle: {subtopic.label if subtopic else 'general'}\n"
            f"source: {article.source_name} ({article.domain})\n"
            f"date: {article.published_at.isoformat() if article.published_at else 'unknown'}\n"
            f"title: {article.title}\n"
            f"text: {article.body[:1200]}"
        )

    user = (
        f"Theme(s): {', '.join(config.themes)}\n{RUBRIC}\n\n"
        f"Items:\n{chr(10).join(lines)}\n\n"
        "Return one entry per id, reusing the exact id strings."
    )

    parsed = await try_json(provider, SYSTEM, user, CuratorBatch)
    if parsed is None:
        return {}
    return {item.id: item for item in parsed.items}


async def curator_node(
    state: NewsletterState,
    provider: LLMProvider,
) -> dict[str, Any]:
    config: RunConfig = state["config"]
    articles: list[RawArticle] = state.get("raw_articles", [])
    subtopic_by_id = {s.id: s for s in state.get("subtopics", [])}
    reference = config.date_to or datetime.now(timezone.utc)

    if not articles:
        return {
            "scored": [],
            "selected_ids": [],
            "events": [
                event(NODE, "done", detail="No articles to score", counts={"selected": 0})
            ],
        }

    batches = [articles[i : i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    results = await asyncio.gather(
        *(_score_batch(provider, config, subtopic_by_id, batch) for batch in batches),
        return_exceptions=True,
    )
    llm_scores: dict[str, CuratorItem] = {}
    for result in results:
        if isinstance(result, dict):
            llm_scores.update(result)

    scored: list[ScoredArticle] = []
    for article in articles:
        subtopic = subtopic_by_id.get(article.subtopic_id)
        theme = (subtopic.theme if subtopic else config.theme) or config.theme
        query = subtopic.query if subtopic else config.theme

        heuristic = ArticleScores(
            relevance=relevance_score(theme, query, article),
            recency=recency_score(article.published_at, reference),
            credibility=credibility_score(article),
            goodness_valence=valence_score(article),
            goodness_signal=signal_score(article),
        )

        judged = llm_scores.get(article.id)
        reasons: list[str] = []
        if judged is not None:
            # Blend: heuristics anchor, LLM adjusts. Avoids one bad call dominating.
            heuristic.relevance = round(0.4 * heuristic.relevance + 0.6 * judged.relevance, 3)
            heuristic.goodness_valence = round(
                0.4 * heuristic.goodness_valence + 0.6 * judged.valence, 3
            )
            heuristic.goodness_signal = round(
                0.4 * heuristic.goodness_signal + 0.6 * judged.signal, 3
            )
            if judged.reason:
                reasons.append(judged.reason)

        heuristic.composite = composite_score(heuristic, config.good_news_mode)
        reasons.extend(explain(heuristic, config.good_news_mode))

        scored.append(
            ScoredArticle(
                article=article,
                scores=heuristic,
                reasons=reasons,
                scored_by="llm" if judged is not None else "heuristic",
            )
        )

    scored.sort(key=lambda item: item.scores.composite, reverse=True)

    threshold = settings.relevance_threshold
    eligible = [item for item in scored if item.scores.relevance >= threshold]
    selected = eligible[: config.target_articles]
    selected_ids = {item.article.id for item in selected}

    for item in scored:
        if item.article.id in selected_ids:
            item.verdict = "selected"
        elif item.scores.relevance >= threshold:
            item.verdict = "backup"
        else:
            item.verdict = "rejected"

    mode_weights = MODE_WEIGHTS[config.good_news_mode]
    active_axes = ",".join(k for k, v in mode_weights.items() if v > 0)
    attempts = state.get("search_attempts", 1)
    wanted = min(config.target_articles, settings.min_relevant_results)
    degraded = len(selected) < wanted and attempts >= settings.max_search_attempts

    return {
        "scored": scored,
        "selected_ids": [item.article.id for item in selected],
        "degraded": degraded,
        "events": [
            event(
                NODE,
                "done",
                detail=(
                    f"{len(selected)}/{len(scored)} selected "
                    f"(mode={config.good_news_mode.value}, axes={active_axes})"
                ),
                counts={
                    "scored": len(scored),
                    "eligible": len(eligible),
                    "selected": len(selected),
                    "llm_judged": len(llm_scores),
                },
            )
        ],
    }
