"""Request and response models for the HTTP API.

Scalars declared bare in a route signature become *query* parameters, which is
how the bookmark and schedule endpoints ended up with a contract the frontend
could not call. Every write endpoint takes an explicit body model instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.graph.state import RunConfig
from app.services import cron


class RunRequest(RunConfig):
    """Run parameters. Mirrors the graph's own config so they cannot drift."""


class CreateRunResponse(BaseModel):
    run_id: str
    status: str = "created"


class BookmarkRequest(BaseModel):
    article_id: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    source_name: str = Field(default="unknown", max_length=200)


class BookmarkResponse(BaseModel):
    run_id: str
    article_id: str
    url: str
    title: str
    source_name: str
    created_at: str


class ScheduleRequest(BaseModel):
    themes: list[str] = Field(default_factory=list, max_length=10)
    cron_expr: str = Field(min_length=1, max_length=120)
    config: RunConfig

    @field_validator("cron_expr")
    @classmethod
    def _check_cron(cls, value: str) -> str:
        try:
            cron.parse(value)
        except cron.CronError as exc:
            raise ValueError(f"invalid cron expression: {exc}") from exc
        return value

    @field_validator("themes")
    @classmethod
    def _clean_themes(cls, value: list[str]) -> list[str]:
        return [theme.strip() for theme in value if theme.strip()]


class ScheduleToggleRequest(BaseModel):
    enabled: bool


class ScheduleResponse(BaseModel):
    schedule_id: str
    themes: list[str]
    cron_expr: str
    config: RunConfig | None = None
    enabled: bool
    created_at: str
    last_run_at: str | None = None
    last_run_id: str | None = None
    next_run_at: str | None = None


class RunSummary(BaseModel):
    run_id: str
    config: RunConfig | None = None
    status: str
    error: str | None = None
    source: str = "manual"
    created_at: str
    finished_at: str | None = None


class RunDetail(RunSummary):
    newsletter: dict[str, Any] | None = None


class FeedbackRequest(BaseModel):
    run_id: str | None = Field(default=None, max_length=64)
    article_id: str | None = Field(default=None, max_length=64)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    feedback_id: str
    status: str = "recorded"


class StatusResponse(BaseModel):
    app_name: str
    version: str
    environment: str
    llm_provider: str
    llm_model: str
    search_providers: list[str]
    using_real_data: bool
    rss_feeds_count: int
    factcheck_enabled: bool
    scheduler_running: bool


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, Any]
