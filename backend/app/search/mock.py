"""Deterministic offline provider for tests and graph inspection.

It is clearly labelled as synthetic: every URL points at example.com so mock
output can never be mistaken for a real citation.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from app.search.base import SearchHit, SearchQuery

_OUTLETS = [
    ("The Signal Review", 0.9),
    ("Constructive Wire", 0.8),
    ("Global Ledger", 0.7),
    ("Daily Pulse Blog", 0.4),
]

_FRAMES = [
    (
        "{query}: pilot programme reports measurable improvement",
        "A twelve-month pilot covering {query} reported a 34 percent improvement "
        "against its baseline, according to figures published by the programme. "
        "Researchers said the result held across all three test regions and that "
        "the dataset has been released for independent review. Funding for a "
        "wider rollout was approved on 3 March.",
    ),
    (
        "{query}: researchers publish peer-reviewed results",
        "A peer-reviewed study on {query} found consistent effects across a "
        "sample of 4,120 participants. The authors cautioned that the effect "
        "size shrank in follow-up measurements, but described the direction of "
        "travel as encouraging. The paper lists 18 co-authors across 6 institutions.",
    ),
    (
        "You won't BELIEVE what {query} means for you",
        "Experts are stunned. Sources say {query} could change everything, "
        "maybe. Click through for the 27 things nobody tells you about it. "
        "No figures were provided and no researcher was named.",
    ),
    (
        "{query}: coalition announces recovery milestone",
        "A coalition of local groups working on {query} announced it had passed "
        "its recovery milestone eight weeks early. The group said 1,900 people "
        "were directly affected and that the approach will be documented so "
        "other regions can copy it.",
    ),
    (
        "{query}: rollout delayed after audit finds gaps",
        "An independent audit of {query} identified gaps in reporting and the "
        "rollout has been delayed by at least two quarters. The auditor "
        "recorded a 12 percent shortfall against the stated target.",
    ),
]


class MockProvider:
    name = "mock"

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        seed = int(hashlib.sha1(query.query.encode()).hexdigest()[:8], 16)
        now = query.date_to or datetime.now(timezone.utc)
        slug = query.query.lower().replace(" ", "-")[:60]

        hits: list[SearchHit] = []
        for index in range(min(query.max_results, len(_FRAMES) * 2)):
            frame_title, frame_body = _FRAMES[(seed + index) % len(_FRAMES)]
            outlet, _ = _OUTLETS[(seed + index) % len(_OUTLETS)]
            published = now - timedelta(days=(seed + index * 3) % 20, hours=index)
            hits.append(
                SearchHit(
                    url=f"https://example.com/{outlet.lower().replace(' ', '-')}/{slug}-{index}",
                    title=frame_title.format(query=query.query),
                    source_name=outlet,
                    published_at=published,
                    snippet=frame_body.format(query=query.query)[:300],
                    content=frame_body.format(query=query.query),
                    provider=self.name,
                )
            )
        return hits
