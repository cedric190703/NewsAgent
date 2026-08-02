"""Planner node: theme -> structured list of search angles."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from app.graph.llm import try_json
from app.graph.state import NewsletterState, RunConfig, SubTopic, event
from app.providers.base import LLMProvider

NODE = "planner"

FALLBACK_ANGLES = [
    ("recent breakthroughs", "{theme} breakthrough results announced"),
    ("policy and funding", "{theme} policy funding decision"),
    ("research findings", "{theme} peer-reviewed study findings"),
    ("real-world deployment", "{theme} deployment rollout results"),
    ("community impact", "{theme} community impact outcomes"),
    ("tools and launches", "{theme} launch release available"),
    ("risks and criticism", "{theme} criticism concerns audit"),
    ("what changed this week", "{theme} this week update"),
]

PLANNER_SYSTEM = (
    "You are a news editor planning research angles. You never invent facts; "
    "you only produce search queries an assistant will actually run. "
    "CRITICAL: every query MUST contain the exact theme words — never generate "
    "a query that could match unrelated topics. "
    "When a target audience is specified, prioritise angles that surface "
    "developments most useful and actionable for that audience."
)


class PlannedSubTopic(BaseModel):
    label: str = Field(max_length=80)
    query: str = Field(max_length=200)
    rationale: str = Field(default="", max_length=300)


class PlannerOutput(BaseModel):
    subtopics: list[PlannedSubTopic] = Field(default_factory=list)


def _subtopic_id(theme: str, query: str) -> str:
    return hashlib.sha1(f"{theme}|{query}".encode()).hexdigest()[:10]


def _fallback(theme: str, count: int) -> list[SubTopic]:
    picked = FALLBACK_ANGLES[:count]
    return [
        SubTopic(
            id=_subtopic_id(theme, template.format(theme=theme)),
            label=label.title(),
            query=template.format(theme=theme),
            rationale="Heuristic angle (planner LLM unavailable).",
            theme=theme,
        )
        for label, template in picked
    ]


async def _plan_theme(
    provider: LLMProvider,
    config: RunConfig,
    theme: str,
    count: int,
) -> tuple[list[SubTopic], bool]:
    window = ""
    if config.date_from or config.date_to:
        window = (
            f"Only consider news between {config.date_from or 'any time'} and "
            f"{config.date_to or 'now'}.\n"
        )

    audience_line = ""
    if config.audience.strip():
        audience_line = (
            f"Target audience: {config.audience.strip()}\n"
            "Tailor the angles to surface developments that are most "
            "useful, actionable, and relevant for this audience.\n"
        )

    user = (
        f"Theme: {theme}\n"
        f"{window}"
        f"{audience_line}"
        f"Break this theme into exactly {count} distinct research angles.\n"
        "Rules: angles must not overlap; each query MUST start with the theme "
        "words and be a short, literal news search string (no boolean operators, "
        "no quotes); prefer angles likely to surface concrete, verifiable developments. "
        "Never generate a query that could match unrelated topics."
    )

    parsed = await try_json(provider, PLANNER_SYSTEM, user, PlannerOutput)
    if parsed is None or not parsed.subtopics:
        return _fallback(theme, count), False

    subtopics: list[SubTopic] = []
    seen: set[str] = set()
    for item in parsed.subtopics[:count]:
        query = item.query.strip() or f"{theme} {item.label}".strip()
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        subtopics.append(
            SubTopic(
                id=_subtopic_id(theme, query),
                label=item.label.strip() or query,
                query=query,
                rationale=item.rationale.strip(),
                theme=theme,
            )
        )

    if not subtopics:
        return _fallback(theme, count), False
    return subtopics, True


async def planner_node(
    state: NewsletterState,
    provider: LLMProvider,
) -> dict[str, Any]:
    config: RunConfig = state["config"]
    themes = config.themes
    per_theme = max(1, config.subtopic_count // len(themes))

    subtopics: list[SubTopic] = []
    used_llm = False
    for theme in themes:
        planned, from_llm = await _plan_theme(provider, config, theme, per_theme)
        used_llm = used_llm or from_llm
        subtopics.extend(planned)

    detail = (
        f"{len(subtopics)} angles across {len(themes)} theme(s)"
        f" via {'LLM' if used_llm else 'heuristic'}"
    )
    return {
        "subtopics": subtopics,
        "search_attempts": 1,
        "events": [
            event(
                NODE,
                "done",
                detail=detail,
                counts={"subtopics": len(subtopics), "themes": len(themes)},
            )
        ],
    }
