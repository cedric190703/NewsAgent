"""Shared theme matching utilities for relevance filtering."""

from __future__ import annotations

import re

# Common stop words to exclude from term matching
STOP_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "what", "how",
    "are", "was", "were", "has", "have", "not", "but", "all", "any",
    "into", "about", "after", "been", "more", "than", "only", "also",
    "its", "our", "you", "your", "they", "them", "his", "her", "she",
    "who", "why", "when", "where", "which", "will", "can", "could",
    "should", "would", "may", "might", "must", "shall",
    "in", "of", "on", "at", "to", "is", "it", "as", "by", "or", "an",
    "no", "do", "so", "if", "we", "he", "be", "up", "us",
}

# Domain synonyms: if the key word appears in the theme, also match these
SYNONYMS: dict[str, list[str]] = {
    "healthcare": ["health", "medical", "hospital", "clinical", "patient", "doctor", "nursing", "biotech", "pharma", "therapy", "diagnosis", "treatment"],
    "medical": ["health", "hospital", "clinical", "patient", "doctor", "medicine", "therapy", "diagnosis"],
    "health": ["medical", "hospital", "clinical", "patient", "wellness", "therapy", "treatment"],
    "ai": ["artificial intelligence", "machine learning", "deep learning", "neural", "llm", "gpt", "algorithm", "generative", "chatbot", "automation"],
    "artificial": ["ai", "machine learning", "neural", "algorithm", "generative"],
    "intelligence": ["ai", "machine learning", "neural", "cognitive"],
    "climate": ["emission", "carbon", "warming", "green", "renewable", "solar", "wind", "environment", "sustainability", "net zero"],
    "energy": ["solar", "wind", "battery", "renewable", "nuclear", "grid", "power", "electric", "hydrogen", "fusion"],
    "space": ["rocket", "satellite", "orbit", "nasa", "spacex", "cosmos", "astronaut", "launch", "mars", "moon"],
    "finance": ["bank", "market", "trading", "invest", "crypto", "bitcoin", "stock", "fintech", "payment", "lending"],
    "education": ["school", "student", "teacher", "learning", "university", "college", "edtech", "curriculum", "classroom"],
    "agriculture": ["farm", "crop", "food", "soil", "harvest", "livestock", "agtech", "precision farming"],
    "cybersecurity": ["hack", "malware", "ransomware", "breach", "vulnerability", "security", "threat", "encryption", "zero-day"],
    "robotics": ["robot", "automation", "drone", "autonomous", "mechanical", "actuator"],
    "transportation": ["car", "vehicle", "ev", "electric vehicle", "autonomous", "transit", "mobility", "logistics", "shipping"],
    "technology": ["tech", "software", "hardware", "digital", "innovation", "startup", "platform"],
    "business": ["company", "corporate", "enterprise", "startup", "industry", "market", "revenue"],
    "science": ["research", "study", "experiment", "discovery", "peer-reviewed", "journal"],
    "politics": ["government", "policy", "election", "congress", "parliament", "legislation", "regulation"],
    "sports": ["game", "championship", "league", "tournament", "athlete", "olympic"],
    "music": ["song", "album", "artist", "concert", "festival", "streaming"],
    "gaming": ["game", "console", "playstation", "xbox", "nintendo", "steam", "esports"],
}


def extract_theme_terms(theme: str) -> set[str]:
    """Extract matching terms from a theme string.

    - 2-char words (e.g. "AI") are included as exact-match terms
    - 4+ char words are included as substring-match terms
    - Synonyms are expanded for known domain words
    """
    words = re.findall(r"[a-z0-9]+", theme.lower())
    terms: set[str] = set()
    for w in words:
        if w in STOP_WORDS or len(w) < 2:
            continue
        terms.add(w)
        # Expand synonyms
        if w in SYNONYMS:
            for syn in SYNONYMS[w]:
                terms.add(syn)
    return terms


def extract_core_terms(theme: str) -> set[str]:
    """Extract only the original theme words (no synonyms, no stop words).

    Used for scoring where the denominator should be small.
    """
    words = re.findall(r"[a-z0-9]+", theme.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) >= 2}


def _concept_groups(theme: str) -> list[set[str]]:
    """Split theme into concept groups, each with its synonyms.

    e.g. "AI in healthcare" -> [{ai, artificial intelligence, machine learning, ...},
                                 {healthcare, health, medical, hospital, ...}]
    The stop word "in" separates the two concepts.
    """
    words = re.findall(r"[a-z0-9]+", theme.lower())
    groups: list[set[str]] = []
    current: set[str] = set()
    for w in words:
        if w in STOP_WORDS or len(w) < 2:
            if current:
                groups.append(current)
                current = set()
            continue
        current.add(w)
        if w in SYNONYMS:
            for syn in SYNONYMS[w]:
                current.add(syn)
    if current:
        groups.append(current)
    return groups


def theme_matches_both_concepts(text: str, theme: str) -> bool:
    """Check if text matches at least one term from EACH concept group.

    e.g. "AI in healthcare" requires matching AI-related terms AND health-related terms.
    This prevents articles that only mention AI (but not health) from passing.
    """
    groups = _concept_groups(theme)
    if not groups:
        return True
    if len(groups) == 1:
        return theme_matches(text, groups[0])
    lower = text.lower()
    for group in groups:
        found = False
        for term in group:
            if len(term) <= 3:
                if re.search(rf"\b{re.escape(term)}\b", lower):
                    found = True
                    break
            else:
                if term in lower:
                    found = True
                    break
        if not found:
            return False
    return True


def theme_matches(text: str, theme_terms: set[str]) -> bool:
    """Check if any theme term appears in the text.

    - Short terms (<=3 chars) use word-boundary matching to avoid false positives
      (e.g. "ai" should not match "email")
    - Longer terms use substring matching (e.g. "health" matches "healthcare")
    """
    if not theme_terms:
        return True
    lower = text.lower()
    for term in theme_terms:
        if len(term) <= 3:
            # Word-boundary match for short terms
            if re.search(rf"\b{re.escape(term)}\b", lower):
                return True
        else:
            if term in lower:
                return True
    return False


def theme_match_count(text: str, theme_terms: set[str]) -> int:
    """Count how many theme terms appear in the text."""
    if not theme_terms:
        return 0
    lower = text.lower()
    count = 0
    for term in theme_terms:
        if len(term) <= 3:
            if re.search(rf"\b{re.escape(term)}\b", lower):
                count += 1
        else:
            if term in lower:
                count += 1
    return count
