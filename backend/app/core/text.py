"""Shared text helpers.

These live in `core` rather than `graph.scoring` because the search layer needs
them too, and search must not depend on the graph (the graph depends on search).
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9]+")

# Words that survive the length filter but say nothing about a topic.
STOPWORDS = frozenset((
    "the", "and", "for", "with", "from", "that", "this", "into", "over",
    "under", "about", "after", "before", "are", "was", "were", "has", "have",
    "had", "its", "their", "our", "your", "what", "when", "how", "why", "who",
    "new", "news", "latest", "recent", "update", "updates", "today", "week",
    "year", "all", "any",
))

MIN_TERM_LENGTH = 3


def terms(text: str) -> set[str]:
    """Lower-cased words of at least `MIN_TERM_LENGTH` characters."""

    return {
        word
        for word in _WORD_RE.findall(text.lower())
        if len(word) >= MIN_TERM_LENGTH
    }


def topic_terms(theme: str) -> set[str]:
    """The words that actually identify a topic, stop-words removed."""

    return {term for term in terms(theme) if term not in STOPWORDS}


def required_term_count(theme: str, maximum: int, widened: bool = False) -> int:
    """How many topic terms an article must mention to count as on-topic.

    A one-word theme can only ever require one. A compound theme like "climate
    technology" means both words together — requiring just one lets any story
    that happens to say "technology" through, which is how a car review ends up
    in a climate newsletter. A widened retry relaxes to a single term, so the
    strict pass buys precision and the retry buys back recall.
    """

    available = len(topic_terms(theme))
    if maximum <= 0 or available == 0:
        return 0
    if widened:
        return 1
    return min(available, maximum)
