"""Turn a finished `Newsletter` into the flat briefing shape the query API returns.

Only a projection: nothing here re-reads sources or asks the model anything, so
a briefing can never contain a claim the newsletter did not already verify.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from app.graph.state import (
    ArticleSummary,
    Newsletter,
    NewsletterState,
    RunConfig,
    SubTopic,
)
from app.schemas.news import (
    NewsQueryRequest,
    NewsQueryResponse,
    NewsSource,
    OutputFormat,
    SourceType,
)

MAX_KEY_POINTS = 6


def to_run_config(request: NewsQueryRequest) -> RunConfig:
    now = datetime.now(timezone.utc)
    return RunConfig(
        theme=request.topic if not request.section else f"{request.topic} ({request.section})",
        subtopic_count=request.depth,
        date_from=now - timedelta(days=request.days),
        date_to=now,
        max_sources=request.max_sources,
        tone=request.tone,
        good_news_mode=request.good_news_mode,
        enable_factcheck=request.enable_factcheck,
        providers=request.providers,
    )


def _all_items(newsletter: Newsletter) -> list[ArticleSummary]:
    return [item for section in newsletter.sections for item in section.items]


def _key_points(newsletter: Newsletter) -> list[str]:
    """One bullet from each of the strongest stories, best story first."""

    items = sorted(_all_items(newsletter), key=lambda i: i.scores.composite, reverse=True)
    points: list[str] = []
    for item in items:
        bullet = next((b for b in item.bullets if b.strip()), item.headline)
        points.append(f"{bullet.strip()} ({item.source_name})")
        if len(points) >= MAX_KEY_POINTS:
            break
    return points


def _analysis(newsletter: Newsletter) -> str:
    blocks: list[str] = []
    for section in newsletter.sections:
        lines = [f"## {section.title}"]
        if section.blurb:
            lines.append(section.blurb)
        for item in section.items:
            date = item.published_at.date().isoformat() if item.published_at else "undated"
            lines.append(f"- {item.headline} — {item.source_name}, {date}")
            lines.extend(f"  - {fact.claim}" for fact in item.key_facts)
        blocks.append("\n".join(lines))

    if newsletter.conflicts:
        conflicts = ["## Conflicting reports"]
        conflicts += [
            f"- [{conflict.severity}] {conflict.claim} — {conflict.note}"
            for conflict in newsletter.conflicts
        ]
        blocks.append("\n".join(conflicts))

    if newsletter.outro:
        blocks.append(newsletter.outro)
    return "\n\n".join(blocks).strip()


def _source_type(url: str, provider_hint: str = "") -> SourceType:
    if provider_hint == "rss":
        return SourceType.RSS
    return SourceType.WEB if urlsplit(url).scheme.startswith("http") else SourceType.KNOWLEDGE_BASE


def _sources(newsletter: Newsletter) -> list[NewsSource]:
    by_id = {item.article_id: item for item in _all_items(newsletter)}
    sources: list[NewsSource] = []
    for ref in newsletter.sources:
        item = by_id.get(ref.article_id)
        summary = None
        if item is not None:
            summary = next((b for b in item.bullets if b.strip()), None)
        sources.append(
            NewsSource(
                title=ref.title,
                url=ref.url,
                source_type=_source_type(ref.url),
                publisher=ref.source_name,
                published_at=ref.published_at,
                relevance_score=item.scores.composite if item else 0.0,
                summary=summary,
                metadata={"article_id": ref.article_id},
            )
        )
    return sources


def _confidence(newsletter: Newsletter) -> str:
    items = _all_items(newsletter)
    if not items or newsletter.degraded:
        return "low"
    verified = sum(1 for item in items for fact in item.key_facts if fact.verified)
    distinct_publishers = len({item.source_name for item in items})
    if len(items) >= 5 and distinct_publishers >= 3 and verified >= 5:
        return "high"
    if len(items) >= 3 and distinct_publishers >= 2:
        return "medium"
    return "low"


def _followups(topic: str, subtopics: list[SubTopic]) -> list[str]:
    """Prefer the angles the planner actually chose over generic prompts."""

    questions = [f"What is the latest on {s.label.lower()} within {topic}?" for s in subtopics[:3]]
    questions.append(f"Which sources are most reliable for {topic}?")
    questions.append(f"What are the main risks and open questions around {topic}?")
    return questions[:5]


def _critic_notes(newsletter: Newsletter, request: NewsQueryRequest) -> list[str]:
    notes = list(newsletter.notes)
    items = _all_items(newsletter)

    if not items:
        notes.append("No articles passed the relevance threshold for this topic.")
    if newsletter.conflicts:
        notes.append(
            f"{len(newsletter.conflicts)} claim(s) are reported differently across sources."
        )
    if request.include_citations and not newsletter.sources:
        notes.append("Citations were requested but no citable source URLs survived filtering.")
    if items:
        heuristic = sum(1 for item in items if item.summarized_by == "heuristic")
        if heuristic:
            notes.append(
                f"{heuristic} of {len(items)} summaries came from the offline fallback, "
                "not the language model."
            )
    if not notes:
        notes.append("The briefing passed structure, citation and verification checks.")
    return notes


def build_response(
    request: NewsQueryRequest,
    run_id: str,
    state: NewsletterState,
) -> NewsQueryResponse:
    newsletter = state.get("newsletter")
    subtopics = list(state.get("subtopics") or [])

    if newsletter is None:
        return NewsQueryResponse(
            run_id=run_id,
            topic=request.topic,
            output_format=request.output_format,
            executive_summary=(
                "The pipeline did not produce a briefing for this topic. "
                "Try widening the date range or adding a search provider."
            ),
            key_points=[],
            analysis="",
            sources=[],
            confidence="low",
            suggested_followups=_followups(request.topic, subtopics),
            critic_notes=["The composer returned no newsletter.", *(state.get("errors") or [])],
        )

    sources = _sources(newsletter) if request.include_citations else []
    analysis = _analysis(newsletter)

    if request.output_format is OutputFormat.SOURCE_LIST:
        analysis = ""

    return NewsQueryResponse(
        run_id=run_id,
        topic=request.topic,
        output_format=request.output_format,
        executive_summary=newsletter.intro or newsletter.subtitle or newsletter.title,
        key_points=_key_points(newsletter),
        analysis=analysis,
        sources=sources,
        confidence=_confidence(newsletter),
        suggested_followups=_followups(request.topic, subtopics),
        critic_notes=_critic_notes(newsletter, request),
    )
