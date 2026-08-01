"""Fact-check / dedup node (conditional): cross-check claims across sources."""

from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations
from typing import Any

from pydantic import BaseModel, Field

from app.graph.llm import try_json
from app.graph.state import (
    ArticleSummary,
    Conflict,
    NewsletterState,
    canonical_url,
    event,
)
from app.providers.base import LLMProvider

NODE = "factcheck"

SYSTEM = (
    "You compare claims from different news articles about the same subject. "
    "You only flag a conflict when the provided texts genuinely disagree. "
    "You never introduce outside knowledge."
)

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|percent|million|billion|thousand)?")
_TOKEN_RE = re.compile(r"[a-z]{4,}")


class LlmConflict(BaseModel):
    claim: str = Field(max_length=300)
    article_ids: list[str] = Field(default_factory=list)
    severity: str = Field(default="low")
    note: str = Field(default="", max_length=300)


class LlmConflicts(BaseModel):
    conflicts: list[LlmConflict] = Field(default_factory=list)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _dedupe(summaries: list[ArticleSummary]) -> tuple[list[ArticleSummary], int]:
    """Drop near-duplicate stories (same canonical URL or same headline shape)."""

    kept: list[ArticleSummary] = []
    seen_urls: set[str] = set()
    seen_shapes: set[frozenset[str]] = set()
    removed = 0

    for summary in sorted(
        summaries, key=lambda s: s.scores.composite, reverse=True
    ):
        url_key = canonical_url(summary.url)
        shape = frozenset(_TOKEN_RE.findall(summary.headline.lower()))
        duplicate_shape = any(
            _jaccard(shape, existing) >= 0.85
            for existing in seen_shapes
            if shape and existing
        )
        if url_key in seen_urls or duplicate_shape:
            removed += 1
            continue
        seen_urls.add(url_key)
        seen_shapes.add(shape)
        kept.append(summary)

    return kept, removed


def _heuristic_conflicts(summaries: list[ArticleSummary]) -> list[Conflict]:
    """Same angle + overlapping wording + different numbers = possible conflict."""

    by_subtopic: dict[str, list[ArticleSummary]] = defaultdict(list)
    for summary in summaries:
        by_subtopic[summary.subtopic_id].append(summary)

    conflicts: list[Conflict] = []
    for group in by_subtopic.values():
        for left, right in combinations(group, 2):
            for left_fact in left.key_facts:
                for right_fact in right.key_facts:
                    left_tokens = set(_TOKEN_RE.findall(left_fact.claim.lower()))
                    right_tokens = set(_TOKEN_RE.findall(right_fact.claim.lower()))
                    if len(left_tokens & right_tokens) < 4:
                        continue
                    left_nums = set(_NUMBER_RE.findall(left_fact.claim))
                    right_nums = set(_NUMBER_RE.findall(right_fact.claim))
                    if left_nums and right_nums and not (left_nums & right_nums):
                        conflicts.append(
                            Conflict(
                                claim=left_fact.claim[:280],
                                article_ids=[left.article_id, right.article_id],
                                severity="low",
                                note=(
                                    f"{left.source_name} and {right.source_name} "
                                    "report different figures for a similar claim."
                                ),
                            )
                        )
    return conflicts[:10]


async def factcheck_node(
    state: NewsletterState,
    provider: LLMProvider,
) -> dict[str, Any]:
    summaries: list[ArticleSummary] = state.get("summaries", [])
    if len(summaries) < 2:
        return {
            "conflicts": [],
            "events": [
                event(NODE, "skipped", detail="Fewer than two summaries to cross-check")
            ],
        }

    kept, removed = _dedupe(summaries)

    claims_block = "\n".join(
        f"---\nid: {summary.article_id}\nsource: {summary.source_name}\n"
        + "\n".join(f"claim: {fact.claim}" for fact in summary.key_facts)
        for summary in kept
        if summary.key_facts
    )

    conflicts: list[Conflict] = []
    if claims_block:
        parsed = await try_json(
            provider,
            SYSTEM,
            (
                "Compare these claims and list only genuine disagreements "
                f"(contradicting figures, dates or outcomes):\n{claims_block}"
            ),
            LlmConflicts,
        )
        valid_ids = {summary.article_id for summary in kept}
        if parsed is not None:
            for item in parsed.conflicts[:10]:
                ids = [i for i in item.article_ids if i in valid_ids]
                if len(ids) < 2:
                    continue
                severity = item.severity if item.severity in {"low", "medium", "high"} else "low"
                conflicts.append(
                    Conflict(
                        claim=item.claim.strip(),
                        article_ids=ids,
                        severity=severity,  # type: ignore[arg-type]
                        note=item.note.strip(),
                    )
                )

    if not conflicts:
        conflicts = _heuristic_conflicts(kept)

    updates: dict[str, Any] = {
        "conflicts": conflicts,
        "kept_ids": [summary.article_id for summary in kept],
        "events": [
            event(
                NODE,
                "done",
                detail=(
                    f"{len(conflicts)} conflict(s) flagged, {removed} duplicate(s) removed"
                ),
                counts={"conflicts": len(conflicts), "duplicates_removed": removed},
            )
        ],
    }
    return updates
