from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


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
    topic: str = Field(..., min_length=3, max_length=300)
    section: str | None = Field(default=None, max_length=120)
    output_format: OutputFormat = OutputFormat.BRIEFING
    sources: list[SourceType] = Field(default_factory=lambda: [SourceType.RSS])
    depth: int = Field(default=3, ge=1, le=5)
    include_citations: bool = True


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
    topic: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_format: OutputFormat
    executive_summary: str
    key_points: list[str]
    analysis: str
    sources: list[NewsSource]
    confidence: str
    suggested_followups: list[str]
    critic_notes: list[str]


class FeedbackRequest(BaseModel):
    result_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
