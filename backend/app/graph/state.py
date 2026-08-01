"""Typed state for the newsletter LangGraph.

Every hand-off between nodes is a Pydantic model, never raw text. Fan-in slots
use additive/merging reducers so parallel branches cannot clobber each other.
"""

from __future__ import annotations

import hashlib
import operator
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, TypedDict
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field


class GoodNewsMode(str, Enum):
    """Two independent axes of "good", exposed as a dial."""

    UPLIFTING = "uplifting"
    HIGH_SIGNAL = "high_signal"
    BALANCED = "balanced"


class Tone(str, Enum):
    NEUTRAL = "neutral"
    WARM = "warm"
    PUNCHY = "punchy"
    ANALYTICAL = "analytical"


class Length(str, Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    DEEP = "deep"


LENGTH_TARGETS: dict[Length, dict[str, int]] = {
    Length.BRIEF: {"articles": 5, "bullets": 2, "intro_words": 60},
    Length.STANDARD: {"articles": 9, "bullets": 3, "intro_words": 110},
    Length.DEEP: {"articles": 15, "bullets": 5, "intro_words": 180},
}


class RunConfig(BaseModel):
    """User-facing run parameters."""

    theme: str = Field(min_length=3, max_length=500)
    extra_themes: list[str] = Field(default_factory=list)
    subtopic_count: int = Field(default=4, ge=1, le=8)
    date_from: datetime | None = None
    date_to: datetime | None = None
    max_sources: int = Field(default=12, ge=1, le=40)
    tone: Tone = Tone.NEUTRAL
    length: Length = Length.STANDARD
    good_news_mode: GoodNewsMode = GoodNewsMode.BALANCED
    enable_factcheck: bool = True
    providers: list[str] = Field(default_factory=list)

    @property
    def themes(self) -> list[str]:
        return [self.theme, *[t for t in self.extra_themes if t.strip()]]

    @property
    def target_articles(self) -> int:
        return min(self.max_sources, LENGTH_TARGETS[self.length]["articles"])

    @property
    def target_bullets(self) -> int:
        return LENGTH_TARGETS[self.length]["bullets"]


class SubTopic(BaseModel):
    id: str
    label: str
    query: str
    rationale: str = ""
    theme: str = ""
    widened: bool = False


class RawArticle(BaseModel):
    id: str
    subtopic_id: str
    url: str
    title: str
    source_name: str
    published_at: datetime | None = None
    snippet: str = ""
    content: str = ""
    image_url: str | None = None
    provider: str = "unknown"

    @property
    def domain(self) -> str:
        return urlsplit(self.url).netloc.lower().removeprefix("www.")

    @property
    def body(self) -> str:
        return self.content or self.snippet


class ArticleScores(BaseModel):
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)
    credibility: float = Field(default=0.0, ge=0.0, le=1.0)
    goodness_valence: float = Field(default=0.0, ge=0.0, le=1.0)
    goodness_signal: float = Field(default=0.0, ge=0.0, le=1.0)
    composite: float = Field(default=0.0, ge=0.0, le=1.0)


class ScoredArticle(BaseModel):
    article: RawArticle
    scores: ArticleScores
    verdict: Literal["selected", "rejected", "backup"] = "backup"
    reasons: list[str] = Field(default_factory=list)
    scored_by: Literal["llm", "heuristic"] = "heuristic"


class KeyFact(BaseModel):
    claim: str
    quote: str
    url: str
    verified: bool = False


class ArticleSummary(BaseModel):
    article_id: str
    subtopic_id: str
    headline: str
    bullets: list[str] = Field(default_factory=list)
    key_facts: list[KeyFact] = Field(default_factory=list)
    url: str
    source_name: str
    published_at: datetime | None = None
    image_url: str | None = None
    scores: ArticleScores = Field(default_factory=ArticleScores)
    summarized_by: Literal["llm", "heuristic"] = "heuristic"


class Conflict(BaseModel):
    claim: str
    article_ids: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "low"
    note: str = ""


class SourceRef(BaseModel):
    article_id: str
    title: str
    url: str
    source_name: str
    published_at: datetime | None = None


class NewsletterSection(BaseModel):
    subtopic_id: str
    title: str
    blurb: str = ""
    items: list[ArticleSummary] = Field(default_factory=list)


class Newsletter(BaseModel):
    title: str
    subtitle: str = ""
    intro: str = ""
    sections: list[NewsletterSection] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    outro: str = ""
    conflicts: list[Conflict] = Field(default_factory=list)
    degraded: bool = False
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


NodeStatus = Literal["pending", "running", "done", "error", "skipped"]


class NodeEvent(BaseModel):
    node: str
    status: NodeStatus
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    branch: str | None = None
    detail: str = ""
    counts: dict[str, int] = Field(default_factory=dict)


def canonical_url(url: str) -> str:
    """Strip query/fragment noise so the same story is not counted twice."""

    parts = urlsplit(url)
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme or "https", netloc, path, "", ""))


def article_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def merge_articles(
    left: list[RawArticle] | None,
    right: list[RawArticle] | None,
) -> list[RawArticle]:
    """Fan-in reducer: concatenate parallel research results, dedupe by URL."""

    merged: dict[str, RawArticle] = {}
    for article in [*(left or []), *(right or [])]:
        existing = merged.get(article.id)
        if existing is None or len(article.body) > len(existing.body):
            merged[article.id] = article
    return list(merged.values())


def merge_scored(
    left: list[ScoredArticle] | None,
    right: list[ScoredArticle] | None,
) -> list[ScoredArticle]:
    """Later scores replace earlier ones for the same article (retry-safe)."""

    merged: dict[str, ScoredArticle] = {}
    for scored in [*(left or []), *(right or [])]:
        merged[scored.article.id] = scored
    return list(merged.values())


def merge_summaries(
    left: list[ArticleSummary] | None,
    right: list[ArticleSummary] | None,
) -> list[ArticleSummary]:
    merged: dict[str, ArticleSummary] = {}
    for summary in [*(left or []), *(right or [])]:
        merged[summary.article_id] = summary
    return list(merged.values())


class NewsletterState(TypedDict, total=False):
    """The graph's shared state. Reducers marked with Annotated are fan-in safe."""

    run_id: str
    config: RunConfig
    subtopics: list[SubTopic]
    raw_articles: Annotated[list[RawArticle], merge_articles]
    scored: Annotated[list[ScoredArticle], merge_scored]
    selected_ids: list[str]
    summaries: Annotated[list[ArticleSummary], merge_summaries]
    kept_ids: list[str]
    conflicts: list[Conflict]
    newsletter: Newsletter | None
    events: Annotated[list[NodeEvent], operator.add]
    errors: Annotated[list[str], operator.add]
    search_attempts: int
    degraded: bool


class ResearchTask(TypedDict):
    """Payload sent to each parallel research branch via Send."""

    run_id: str
    config: RunConfig
    subtopic: SubTopic
    attempt: int


class SummaryTask(TypedDict):
    """Payload sent to each parallel summarizer branch via Send."""

    run_id: str
    config: RunConfig
    scored: ScoredArticle


def initial_state(run_id: str, config: RunConfig) -> NewsletterState:
    return {
        "run_id": run_id,
        "config": config,
        "subtopics": [],
        "raw_articles": [],
        "scored": [],
        "selected_ids": [],
        "summaries": [],
        "kept_ids": [],
        "conflicts": [],
        "newsletter": None,
        "events": [],
        "errors": [],
        "search_attempts": 0,
        "degraded": False,
    }


def event(node: str, status: NodeStatus, **kwargs: Any) -> NodeEvent:
    return NodeEvent(node=node, status=status, **kwargs)
