"""Composer node: assemble the newsletter from typed summaries only.

The composer never sees article bodies — only `ArticleSummary` objects — and any
URL it emits that is not in the fetched set is stripped before it can ship.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from app.graph.llm import try_json
from app.graph.state import (
    ArticleSummary,
    Newsletter,
    NewsletterSection,
    NewsletterState,
    RunConfig,
    SourceRef,
    SubTopic,
    event,
)
from app.providers.base import LLMProvider

NODE = "composer"

SYSTEM = (
    "You are a newsletter editor. You may only use the summaries provided. "
    "Do not invent stories, statistics or URLs. Do not include any links."
)

_URL_RE = re.compile(r"https?://\S+")


class LlmSectionCopy(BaseModel):
    subtopic_id: str
    title: str = Field(default="", max_length=100)
    blurb: str = Field(default="", max_length=400)


class LlmNewsletter(BaseModel):
    title: str = Field(default="", max_length=120)
    subtitle: str = Field(default="", max_length=180)
    intro: str = Field(default="", max_length=1200)
    sections: list[LlmSectionCopy] = Field(default_factory=list)
    outro: str = Field(default="", max_length=600)


def _strip_urls(text: str) -> str:
    return _URL_RE.sub("", text).replace("  ", " ").strip()


def _group(
    summaries: list[ArticleSummary],
    subtopics: list[SubTopic],
) -> list[tuple[SubTopic, list[ArticleSummary]]]:
    by_subtopic: dict[str, list[ArticleSummary]] = defaultdict(list)
    for summary in summaries:
        by_subtopic[summary.subtopic_id].append(summary)

    groups: list[tuple[SubTopic, list[ArticleSummary]]] = []
    known_ids = set()
    for subtopic in subtopics:
        known_ids.add(subtopic.id)
        items = by_subtopic.get(subtopic.id, [])
        if items:
            items.sort(key=lambda s: s.scores.composite, reverse=True)
            groups.append((subtopic, items))

    orphans = [s for sid, group in by_subtopic.items() if sid not in known_ids for s in group]
    if orphans:
        groups.append(
            (SubTopic(id="other", label="Also worth reading", query=""), orphans)
        )
    return groups


def _fallback_copy(config: RunConfig, count: int, sections: int) -> LlmNewsletter:
    themes = ", ".join(config.themes)
    return LlmNewsletter(
        title=f"{themes}: {count} stories worth your time",
        subtitle=f"{sections} angles, {count} sources, {config.good_news_mode.value} mode",
        intro=(
            f"Here are {count} developments on {themes}, selected for "
            f"{config.good_news_mode.value.replace('_', ' ')} value. Every item "
            "links back to the article it came from."
        ),
        outro="Every claim above is quoted from its linked source.",
    )


async def composer_node(
    state: NewsletterState,
    provider: LLMProvider,
) -> dict[str, Any]:
    config: RunConfig = state["config"]
    all_summaries: list[ArticleSummary] = state.get("summaries", [])
    kept_ids = set(state.get("kept_ids") or [])
    summaries = [s for s in all_summaries if not kept_ids or s.article_id in kept_ids]
    subtopics: list[SubTopic] = state.get("subtopics", [])
    degraded = bool(state.get("degraded"))

    groups = _group(summaries, subtopics)
    allowed_urls = {s.url for s in summaries}

    if not summaries:
        newsletter = Newsletter(
            title=f"{config.theme}: no verifiable stories found",
            subtitle="",
            intro=(
                "The research pass did not return enough relevant, verifiable "
                "articles for this theme and date range. Try widening the date "
                "range, raising the source count, or adding a search provider."
            ),
            degraded=True,
            notes=["No articles passed the relevance threshold."],
        )
        return {
            "newsletter": newsletter,
            "events": [event(NODE, "done", detail="Empty newsletter", counts={"items": 0})],
        }

    digest = "\n".join(
        f"---\nsubtopic_id: {subtopic.id}\nangle: {subtopic.label}\n"
        + "\n".join(f"- {item.headline} ({item.source_name})" for item in items)
        for subtopic, items in groups
    )
    user = (
        f"Theme(s): {', '.join(config.themes)}\n"
        f"Tone: {config.tone.value}\nLength: {config.length.value}\n"
        f"Curation mode: {config.good_news_mode.value}\n\n"
        f"Sections and their stories:\n{digest}\n\n"
        "Write the newsletter title, a one-line subtitle, an intro of about "
        f"{60 if config.length.value == 'brief' else 120} words, a one-sentence "
        "blurb per section (reuse the exact subtopic_id values), and a short outro. "
        "Reference only the stories listed. No links."
    )

    parsed = await try_json(provider, SYSTEM, user, LlmNewsletter)
    if parsed is None or not parsed.intro:
        parsed = _fallback_copy(config, len(summaries), len(groups))
        composed_by = "heuristic"
    else:
        composed_by = "llm"

    blurbs = {section.subtopic_id: section for section in parsed.sections}
    sections: list[NewsletterSection] = []
    for subtopic, items in groups:
        copy = blurbs.get(subtopic.id)
        sections.append(
            NewsletterSection(
                subtopic_id=subtopic.id,
                title=_strip_urls(copy.title) if copy and copy.title else subtopic.label,
                blurb=_strip_urls(copy.blurb) if copy else "",
                items=items,
            )
        )

    sources = [
        SourceRef(
            article_id=item.article_id,
            title=item.headline,
            url=item.url,
            source_name=item.source_name,
            published_at=item.published_at,
        )
        for _, items in groups
        for item in items
        if item.url in allowed_urls
    ]

    notes: list[str] = []
    if degraded:
        notes.append("Fewer sources than requested were available for this theme.")
    unverified = sum(1 for s in summaries for f in s.key_facts if not f.verified)
    if unverified:
        notes.append(f"{unverified} unverifiable claim(s) were removed.")

    newsletter = Newsletter(
        title=_strip_urls(parsed.title) or f"{config.theme} digest",
        subtitle=_strip_urls(parsed.subtitle),
        intro=_strip_urls(parsed.intro),
        sections=sections,
        sources=sources,
        outro=_strip_urls(parsed.outro),
        conflicts=state.get("conflicts", []),
        degraded=degraded,
        notes=notes,
    )

    return {
        "newsletter": newsletter,
        "events": [
            event(
                NODE,
                "done",
                detail=f"{len(sections)} sections, {len(sources)} sources ({composed_by})",
                counts={"sections": len(sections), "items": len(sources)},
            )
        ],
    }
