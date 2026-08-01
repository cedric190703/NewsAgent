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

from app.graph.state import ArticleScores, GoodNewsMode, RawArticle

MODE_WEIGHTS: dict[GoodNewsMode, dict[str, float]] = {
    GoodNewsMode.UPLIFTING: {
        "relevance": 0.30,
        "recency": 0.15,
        "credibility": 0.15,
        "goodness_valence": 0.30,
        "goodness_signal": 0.10,
    },
    GoodNewsMode.HIGH_SIGNAL: {
        "relevance": 0.30,
        "recency": 0.15,
        "credibility": 0.20,
        "goodness_valence": 0.00,
        "goodness_signal": 0.35,
    },
    GoodNewsMode.BALANCED: {
        "relevance": 0.30,
        "recency": 0.15,
        "credibility": 0.15,
        "goodness_valence": 0.20,
        "goodness_signal": 0.20,
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
)
NEGATIVE_TERMS = (
    "death", "deaths", "killed", "dies", "crisis", "collapse", "collapsed",
    "war", "attack", "shooting", "scandal", "fraud", "lawsuit", "layoffs",
    "outbreak", "disaster", "catastrophe", "shortfall", "delayed", "delay",
    "failure", "failed", "warns", "warning", "threat", "recall", "banned",
    "worst", "plunge", "plummet", "recession", "corruption", "abuse",
)
HYPE_TERMS = (
    "you won't believe", "shocking", "stunned", "insane", "mind-blowing",
    "this one trick", "changed everything", "goes viral", "slams", "destroys",
    "epic", "brutal", "everything you need to know", "here's why",
    "experts are stunned", "could change everything", "click",
)
SIGNAL_TERMS = (
    "according to", "study", "peer-reviewed", "researchers", "data",
    "report", "published", "analysis", "percent", "%", "survey", "trial",
    "dataset", "audit", "official", "spokesperson", "figures",
)
CLICKBAIT_TITLE_RE = re.compile(
    r"^\s*(\d{1,2})\s+(things|reasons|ways|facts|signs)\b", re.I
)


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def relevance_score(theme: str, subtopic_query: str, article: RawArticle) -> float:
    wanted = _terms(theme) | _terms(subtopic_query)
    if not wanted:
        return 0.5
    haystack = _terms(f"{article.title} {article.snippet}")
    body = _terms(article.body[:4000])

    title_overlap = len(wanted & _terms(article.title)) / len(wanted)
    head_overlap = len(wanted & haystack) / len(wanted)
    body_overlap = len(wanted & body) / len(wanted)
    raw = 0.45 * title_overlap + 0.35 * head_overlap + 0.20 * body_overlap
    return round(min(1.0, raw * 1.25), 3)


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
