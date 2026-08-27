from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    query: str
    max_results: int = Field(default=8, ge=1, le=50)
    date_from: datetime | None = None
    date_to: datetime | None = None
    required_terms: list[str] = Field(
        default_factory=list,
        description=(
            "Terms that define the topic, as opposed to the angle. Keyword-matching "
            "providers (RSS) use these to reject items that are not about the topic."
        ),
    )
    min_required_terms: int = Field(
        default=0,
        ge=0,
        description="How many of `required_terms` an item must contain. 0 disables the check.",
    )


class SearchHit(BaseModel):
    """A real, fetched result. Nothing here is model-generated."""

    url: str
    title: str
    source_name: str = ""
    published_at: datetime | None = None
    snippet: str = ""
    content: str = ""
    image_url: str | None = None
    provider: str = "unknown"


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        """Return real search hits, or an empty list on failure."""
