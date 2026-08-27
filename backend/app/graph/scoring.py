"""Deterministic scoring: relevance, recency, credibility, and the two
independent "good news" axes.

Axis 1 - goodness_valence: constructive / uplifting outcome (progress, wins).
Axis 2 - goodness_signal:  journalistic quality (specific, sourced, low hype).

`GoodNewsMode` only changes how the axes are *weighted*, never how they are
measured, so a run can be re-ranked without re-fetching anything.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from app.core.text import terms as _terms
from app.core.text import topic_terms
from app.graph.state import ArticleScores, GoodNewsMode, RawArticle
from app.graph.theme_match import extract_theme_terms, extract_core_terms, theme_match_count

__all__ = [
    "composite_score",
    "credibility_score",
    "explain",
    "recency_score",
    "relevance_score",
    "signal_score",
    "topic_terms",
    "topical_terms_matched",
    "valence_score",
]

MODE_WEIGHTS: dict[GoodNewsMode, dict[str, float]] = {
    GoodNewsMode.UPLIFTING: {
        "relevance": 0.38,
        "recency": 0.12,
        "credibility": 0.15,
        "goodness_valence": 0.25,
        "goodness_signal": 0.10,
    },
    GoodNewsMode.HIGH_SIGNAL: {
        "relevance": 0.38,
        "recency": 0.12,
        "credibility": 0.20,
        "goodness_valence": 0.00,
        "goodness_signal": 0.30,
    },
    GoodNewsMode.BALANCED: {
        "relevance": 0.38,
        "recency": 0.12,
        "credibility": 0.15,
        "goodness_valence": 0.17,
        "goodness_signal": 0.18,
    },
}

# --- credibility ---------------------------------------------------------

TIER_ONE = {
    "reuters.com", "apnews.com", "bbc.co.uk", "bbc.com", "ft.com",
    "nature.com", "science.org", "sciencemag.org", "nejm.org", "thelancet.com",
    "economist.com", "wsj.com", "nytimes.com", "washingtonpost.com",
    "theguardian.com", "bloomberg.com", "npr.org", "propublica.org",
}
TIER_TWO = {
    "arstechnica.com", "theverge.com", "wired.com", "technologyreview.com",
    "axios.com", "politico.com", "cnbc.com", "aljazeera.com", "dw.com",
    "lemonde.fr", "spiegel.de", "elpais.com", "scientificamerican.com",
    "ieee.org", "phys.org", "sciencedaily.com", "goodnewsnetwork.org",
    "positive.news", "reasonstobecheerful.world", "solutionsjournalism.org",
    "techcrunch.com", "engadget.com", "theinformation.com", "semafor.com",
    "restofworld.org", "calmatters.org", "grist.org", "insideclimatenews.org",
}
LOW_TRUST_MARKERS = (
    "blogspot.", ".medium.com", "wordpress.com", "substack.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "contentmarketing", "sponsored",
)

# --- lexicons ------------------------------------------------------------

POSITIVE_TERMS = (
    "breakthrough", "recovery", "recovered", "restored", "improve", "improved",
    "improvement", "record low", "record high", "cure", "cured", "success",
    "successful", "milestone", "approved", "launch", "launched", "solution",
    "solved", "progress", "rescued", "saved", "boost", "surge in access",
    "first time", "eradicated", "reforest", "protected", "cleaner", "cheaper",
    "faster", "safer", "expanded access", "funding secured", "wins", "won",
    "declines in poverty", "reduced emissions", "ahead of schedule",
    "innovation", "innovative", "achievement", "advancement", "pioneering",
    "grant", "investment", "partnership", "collaboration", "breakthrough",
    "effective", "promising", "transformative", "scalable", "sustainable",
)
NEGATIVE_TERMS = (
    "death", "deaths", "killed", "dies", "crisis", "collapse", "collapsed",
    "war", "attack", "shooting", "scandal", "fraud", "lawsuit", "layoffs",
    "outbreak", "disaster", "catastrophe", "shortfall", "delayed", "delay",
    "failure", "failed", "warns", "warning", "threat", "recall", "banned",
    "worst", "plunge", "plummet", "recession", "corruption", "abuse",
    "controversy", "controversial", "protest", "strike", "boycott", "sanction",
    "casualty", "casualties", "victim", "victims", "damage", "damaged",
)
HYPE_TERMS = (
    "you won't believe", "shocking", "stunned", "insane", "mind-blowing",
    "this one trick", "changed everything", "goes viral", "slams", "destroys",
    "epic", "brutal", "everything you need to know", "here's why",
    "experts are stunned", "could change everything", "click",
    "breaking", "must see", "watch this", "unbelievable", "jaw-dropping",
)
SIGNAL_TERMS = (
    "according to", "study", "peer-reviewed", "researchers", "data",
    "report", "published", "analysis", "percent", "%", "survey", "trial",
    "dataset", "audit", "official", "spokesperson", "figures",
    "statistics", "measured", "experiment", "control group", "sample",
    "methodology", "findings", "results", "evidence", "documented",
    "confirmed", "verified", "source", "cited", "reference",
)
CLICKBAIT_TITLE_RE = re.compile(
    r"^\s*(\d{1,2})\s+(things|reasons|ways|facts|signs)\b", re.I
)


def topical_terms_matched(theme: str, article: RawArticle) -> int:
    """How many of the topic's terms appear in the headline or lede.

    Deliberately ignores the article body: a fetched page carries navigation,
    related-story links and footers, so almost any long page overlaps almost
    any theme. What a story is *about* shows up in its title and opening.
    Returning a count rather than a ratio keeps the selection rule statable —
    "the headline or lede has to mention the topic at least once".
    """

    wanted = topic_terms(theme)
    if not wanted:
        return 1
    head = _terms(f"{article.title} {article.snippet[:400]}")
    return len(wanted & head)


def relevance_score(theme: str, subtopic_query: str, article: RawArticle) -> float:
    # Core terms (original words only) — used as denominator
    core_theme = extract_core_terms(theme)
    core_query = extract_core_terms(subtopic_query)
    core_wanted = core_theme | core_query
    if not core_wanted:
        return 0.5

    # Full synonym-expanded terms — used for counting hits
    full_theme = extract_theme_terms(theme)
    full_query = extract_theme_terms(subtopic_query)
    full_wanted = full_theme | full_query

    title = article.title
    head = f"{article.title} {article.snippet}"
    body = article.body[:4000]

    # Count hits using full synonym set, but divide by core term count
    title_hits = theme_match_count(title, full_wanted)
    head_hits = theme_match_count(head, full_wanted)
    body_hits = theme_match_count(body, full_wanted)

    denom = max(len(core_wanted), 1)
    title_overlap = min(1.0, title_hits / denom)
    head_overlap = min(1.0, head_hits / denom)
    body_overlap = min(1.0, body_hits / denom)

    # Theme terms in title are critical
    theme_denom = max(len(core_theme), 1)
    theme_in_title = min(1.0, theme_match_count(title, full_theme) / theme_denom)
    theme_in_head = min(1.0, theme_match_count(head, full_theme) / theme_denom)

    # Body keyword density: how many distinct theme terms appear in body
    body_theme_hits = theme_match_count(body, full_theme)
    body_theme_density = min(1.0, body_theme_hits / max(len(full_theme), 1))

    # Weighted: title is most important, then head, then body density
    raw = (
        0.38 * title_overlap
        + 0.22 * head_overlap
        + 0.10 * body_overlap
        + 0.20 * theme_in_title
        + 0.10 * body_theme_density
    )

    # If theme terms not even in title/snippet, penalize heavily
    if theme_in_head == 0 and full_theme:
        raw *= 0.3
    # If theme terms in title but not in body, it's likely tangential
    elif theme_in_title > 0 and body_theme_density == 0:
        raw *= 0.6

    return round(min(1.0, raw * 1.15), 3)


def recency_score(
    published_at: datetime | None,
    reference: datetime | None = None,
    half_life_days: float = 7.0,
) -> float:
    if published_at is None:
        return 0.35
    now = reference or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    published = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - published).total_seconds() / 86400)
    return round(math.pow(0.5, age_days / half_life_days), 3)


def credibility_score(article: RawArticle) -> float:
    domain = article.domain
    score = 0.5

    if domain in TIER_ONE:
        score = 0.95
    elif domain in TIER_TWO:
        score = 0.8
    elif domain.endswith((".gov", ".edu", ".ac.uk", ".int")):
        score = 0.9
    elif domain.endswith(".org"):
        score = 0.65

    if any(marker in domain for marker in LOW_TRUST_MARKERS):
        score = min(score, 0.35)
    if not article.url.startswith("https://"):
        score -= 0.05
    if len(article.body) > 1500:
        score += 0.05
    if article.published_at is None:
        score -= 0.05

    return round(max(0.05, min(1.0, score)), 3)


def valence_score(article: RawArticle) -> float:
    """Axis 1: is the *outcome* described constructive?"""

    text = f"{article.title} {article.snippet}".lower()
    positives = sum(1 for term in POSITIVE_TERMS if term in text)
    negatives = sum(1 for term in NEGATIVE_TERMS if term in text)
    title = article.title.lower()
    positives += sum(1 for term in POSITIVE_TERMS if term in title)
    negatives += sum(1 for term in NEGATIVE_TERMS if term in title)

    total = positives + negatives
    if total == 0:
        return 0.5
    return round(0.5 + 0.5 * ((positives - negatives) / total), 3)


def signal_score(article: RawArticle) -> float:
    """Axis 2: is it substantive rather than hype?"""

    text = f"{article.title} {article.snippet} {article.body[:2000]}".lower()
    signal = sum(1 for term in SIGNAL_TERMS if term in text)
    hype = sum(1 for term in HYPE_TERMS if term in text)

    score = 0.35 + min(0.45, signal * 0.07)
    score -= min(0.5, hype * 0.15)
    if CLICKBAIT_TITLE_RE.match(article.title):
        score -= 0.2
    if re.search(r"\d", article.title):
        score += 0.02
    if len(article.body) > 2500:
        score += 0.08
    if article.title.isupper():
        score -= 0.1

    return round(max(0.0, min(1.0, score)), 3)


def composite_score(scores: ArticleScores, mode: GoodNewsMode) -> float:
    weights = MODE_WEIGHTS[mode]
    total = sum(
        getattr(scores, axis) * weight for axis, weight in weights.items()
    ) / sum(weights.values())
    return round(min(1.0, max(0.0, total)), 4)


def explain(scores: ArticleScores, mode: GoodNewsMode) -> list[str]:
    reasons = [
        f"relevance {scores.relevance:.2f}",
        f"recency {scores.recency:.2f}",
        f"credibility {scores.credibility:.2f}",
    ]
    if MODE_WEIGHTS[mode]["goodness_valence"] > 0:
        reasons.append(f"constructive {scores.goodness_valence:.2f}")
    if MODE_WEIGHTS[mode]["goodness_signal"] > 0:
        reasons.append(f"signal {scores.goodness_signal:.2f}")
    return reasons
