"""Summarizer node: one parallel branch per selected article.

Hard rule: every key fact must carry a quote that is literally present in the
fetched article text. Unverifiable facts are dropped, not shipped.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.graph.llm import try_json
from app.graph.state import (
    ArticleSummary,
    KeyFact,
    RunConfig,
    ScoredArticle,
    SummaryTask,
    event,
)
from app.providers.base import LLMProvider

NODE = "summarizer"

SYSTEM = (
    "You summarise a single news article. You may only use the article text "
    "given to you. Every key fact must include a quote copied verbatim from "
    "that text. If you cannot support a fact with a verbatim quote, omit it."
)

_WS_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class LlmKeyFact(BaseModel):
    claim: str = Field(max_length=300)
    quote: str = Field(max_length=400)


class LlmSummary(BaseModel):
    headline: str = Field(max_length=160)
    bullets: list[str] = Field(default_factory=list)
    key_facts: list[LlmKeyFact] = Field(default_factory=list)


def _normalise(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().lower()


def _verify(quote: str, body: str) -> bool:
    quote_n = _normalise(quote)
    if len(quote_n) < 15:
        return False
    return quote_n in _normalise(body)


def _heuristic_summary(scored: ScoredArticle, bullet_count: int) -> ArticleSummary:
    article = scored.article
    sentences = [s.strip() for s in _SENTENCE_RE.split(article.body) if len(s.strip()) > 40]
    bullets = sentences[:bullet_count]
    facts = [
        KeyFact(claim=sentence[:280], quote=sentence[:380], url=article.url, verified=True)
        for sentence in sentences[:2]
    ]
    return ArticleSummary(
        article_id=article.id,
        subtopic_id=article.subtopic_id,
        headline=article.title[:160],
        bullets=bullets or ([article.snippet[:280]] if article.snippet else []),
        key_facts=facts,
        url=article.url,
        source_name=article.source_name,
        published_at=article.published_at,
        image_url=article.image_url,
        scores=scored.scores,
        summarized_by="heuristic",
    )


async def summarizer_node(
    task: SummaryTask,
    provider: LLMProvider,
) -> dict[str, Any]:
    config: RunConfig = task["config"]
    scored: ScoredArticle = task["scored"]
    article = scored.article
    bullet_count = config.target_bullets

    if not article.body.strip():
        return {
            "events": [
                event(
                    NODE,
                    "skipped",
                    branch=article.id,
                    detail=f"No fetched text for {article.domain}",
                )
            ]
        }

    user = (
        f"Tone: {config.tone.value}\n"
        f"Source: {article.source_name}\n"
        f"Published: {article.published_at.isoformat() if article.published_at else 'unknown'}\n"
        f"Title: {article.title}\n\n"
        f"Article text:\n{article.body[:6000]}\n\n"
        f"Write a factual headline, exactly {bullet_count} short bullets, and up "
        "to 3 key facts. Each key fact needs a verbatim quote from the text above."
    )

    parsed = await try_json(provider, SYSTEM, user, LlmSummary)

    if parsed is None:
        summary = _heuristic_summary(scored, bullet_count)
        dropped = 0
    else:
        facts: list[KeyFact] = []
        dropped = 0
        for fact in parsed.key_facts[:3]:
            if _verify(fact.quote, article.body):
                facts.append(
                    KeyFact(
                        claim=fact.claim.strip(),
                        quote=fact.quote.strip(),
                        url=article.url,
                        verified=True,
                    )
                )
            else:
                dropped += 1

        bullets = [b.strip() for b in parsed.bullets if b.strip()][:bullet_count]
        summary = ArticleSummary(
            article_id=article.id,
            subtopic_id=article.subtopic_id,
            headline=(parsed.headline.strip() or article.title)[:160],
            bullets=bullets,
            key_facts=facts,
            url=article.url,
            source_name=article.source_name,
            published_at=article.published_at,
            image_url=article.image_url,
            scores=scored.scores,
            summarized_by="llm",
        )
        if not summary.bullets:
            summary = _heuristic_summary(scored, bullet_count)

    return {
        "summaries": [summary],
        "events": [
            event(
                NODE,
                "done",
                branch=article.id,
                detail=f"{summary.headline[:80]} ({summary.summarized_by})",
                counts={
                    "bullets": len(summary.bullets),
                    "facts": len(summary.key_facts),
                    "unverified_dropped": dropped,
                },
            )
        ],
    }
