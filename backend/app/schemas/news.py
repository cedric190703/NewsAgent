"""Schemas for the synchronous briefing API (`/api/news/query`).

This is the "ask a question, get one structured answer" surface described in the
README. It is a *view* over the same LangGraph pipeline the streaming run API
uses — not a second pipeline — so both surfaces answer from identical evidence.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl

from app.graph.state import GoodNewsMode, Tone


class SourceType(str, Enum):
    WEB = "web"
    RSS = "rss"
    KNOWLEDGE_BASE = "knowledge_base"


class OutputFormat(str, Enum):
    BRIEFING = "briefing"
    NEWSLETTER = "newsletter"
    ANALYSIS = "analysis"
    SOURCE_LIST = "source_list"


class NewsQueryRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    section: str | None = Field(default=None, max_length=120)
    output_format: OutputFormat = OutputFormat.BRIEFING
    depth: int = Field(
        default=3, ge=1, le=5, description="Research angles to explore (1-5)."
    )
    max_sources: int = Field(default=8, ge=1, le=40)
    days: int = Field(default=14, ge=1, le=365, description="How far back to look.")
    include_citations: bool = True
    good_news_mode: GoodNewsMode = GoodNewsMode.BALANCED
    tone: Tone = Tone.NEUTRAL
    providers: list[str] = Field(
        default_factory=list, description="Empty means every configured provider."
    )
    enable_factcheck: bool = True


class NewsSource(BaseModel):
    title: str
    url: HttpUrl | None = None
    source_type: SourceType
    publisher: str | None = None
    published_at: datetime | None = None
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewsQueryResponse(BaseModel):
    result_id: UUID = Field(default_factory=uuid4)
    run_id: str
    topic: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_format: OutputFormat
    executive_summary: str
    key_points: list[str]
    analysis: str
    sources: list[NewsSource]
    confidence: str = Field(description="high | medium | low")
    suggested_followups: list[str]
    critic_notes: list[str]
