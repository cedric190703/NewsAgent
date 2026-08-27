"""Offline LLM stand-in that returns *schema-valid* JSON.

The graph asks for structured output and falls back to heuristics whenever the
model cannot comply. A mock that returns prose therefore exercises only the
fallback path, which is the opposite of what a test provider is for. This one
reads the JSON schema out of the prompt (`try_json` appends it) and synthesises
a conforming instance, so `LLM_PROVIDER=mock` runs the *real* LLM branches.

Values are derived from the prompt where the field name says they must be:
`id` / `subtopic_id` are echoed back verbatim (the curator and composer match on
them), and `quote` pulls a real sentence from the article text so the
summarizer's verbatim-quote check passes the way it would with a real model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.providers.base import ChatMessage

_SCHEMA_RE = re.compile(r"validate against this JSON schema:\s*(\{.*\})\s*$", re.S)
_ID_RE = re.compile(r"^id:\s*([0-9a-zA-Z_-]{4,})\s*$", re.M)
_SUBTOPIC_ID_RE = re.compile(r"^subtopic_id:\s*([0-9a-zA-Z_-]{4,})\s*$", re.M)
_ARTICLE_TEXT_RE = re.compile(r"Article text:\s*(.+?)(?:\n\nWrite |\Z)", re.S)
_TITLE_RE = re.compile(r"^Title:\s*(.+)$", re.M)
_THEME_RE = re.compile(r"^Theme(?:\(s\))?:\s*(.+)$", re.M)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

MAX_DEPTH = 6

_ANGLES = (
    "recent breakthroughs",
    "policy and funding",
    "research findings",
    "real-world deployment",
    "risks and criticism",
)


class MockProvider:
    """Deterministic: the same prompt always yields the same response."""

    name = "mock"

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
    ) -> str:
        prompt = "\n".join(message.content for message in messages)
        schema = _extract_schema(prompt)

        if schema is None:
            return _prose(prompt)
        return json.dumps(_instance(schema, schema, _Context(prompt)), default=str)


class _Context:
    """Values scraped from the prompt that the generated JSON must echo back."""

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        self.ids = _ID_RE.findall(prompt)
        self.subtopic_ids = _SUBTOPIC_ID_RE.findall(prompt)
        self.theme = (_THEME_RE.search(prompt) or _blank()).group(1).strip() or "the topic"
        self.title = (_TITLE_RE.search(prompt) or _blank()).group(1).strip()
        self.sentences = _sentences(prompt)
        self.index = 0
        self._cursors: dict[str, int] = {}

    def at(self, pool: str) -> str | None:
        """Pick by sibling position, so related fields agree with each other."""

        values: list[str] = getattr(self, pool)
        return values[self.index % len(values)] if values else None

    def next(self, pool: str) -> str | None:
        """Round-robin through a scraped pool so repeated fields differ."""

        values: list[str] = getattr(self, pool)
        if not values:
            return None
        index = self._cursors.get(pool, 0)
        self._cursors[pool] = index + 1
        return values[index % len(values)]


def _blank() -> re.Match:
    return re.match(r"(?P<g>)", "")


def _sentences(prompt: str) -> list[str]:
    body = _ARTICLE_TEXT_RE.search(prompt)
    if body is None:
        return []
    return [
        s.strip() for s in _SENTENCE_RE.split(body.group(1)) if 25 < len(s.strip()) < 350
    ]


def _extract_schema(prompt: str) -> dict[str, Any] | None:
    match = _SCHEMA_RE.search(prompt)
    if not match:
        return None
    try:
        schema = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return schema if isinstance(schema, dict) else None


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Follow a local `$ref` (Pydantic nests sub-models under `$defs`)."""

    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    node: Any = root
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return schema
        node = node[part]
    return node if isinstance(node, dict) else schema


def _clip(text: str, schema: dict[str, Any]) -> str:
    limit = schema.get("maxLength")
    return text[:limit] if isinstance(limit, int) else text


def _string_for(field: str, schema: dict[str, Any], ctx: _Context) -> str:
    """Field-name heuristics, so generated JSON survives the graph's own checks."""

    lowered = field.lower()

    if lowered in ("id", "article_id"):
        return _clip(ctx.next("ids") or "mock-id", schema)
    if lowered == "subtopic_id":
        return _clip(ctx.next("subtopic_ids") or ctx.next("ids") or "mock-subtopic", schema)
    if lowered in ("quote", "claim", "bullet"):
        # A quote must appear verbatim in the article text or the summarizer
        # drops it; indexing by sibling position keeps each fact's claim and
        # quote pointing at the same sentence.
        sentence = ctx.at("sentences")
        if sentence is not None:
            return _clip(sentence, schema)
        return _clip(f"A mock {lowered} about {ctx.theme}.", schema)
    if lowered in ("blurb", "intro", "outro", "note", "rationale"):
        return _clip(
            f"Mock {lowered} covering {ctx.theme} "
            f"({_ANGLES[ctx.index % len(_ANGLES)]}), generated offline.",
            schema,
        )
    if lowered == "headline":
        return _clip(ctx.title or f"{ctx.theme}: mock headline", schema)
    if lowered in ("title", "label"):
        angle = _ANGLES[ctx.index % len(_ANGLES)]
        return _clip(f"{ctx.theme.title()}: {angle.title()}", schema)
    if lowered == "subtitle":
        return _clip(f"A mock digest on {ctx.theme}", schema)
    if lowered == "query":
        return _clip(f"{ctx.theme} {_ANGLES[ctx.index % len(_ANGLES)]}", schema)
    if lowered == "severity":
        return "low"

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return str(enum[0])
    return _clip(f"mock {lowered}", schema)


def _number_for(field: str, schema: dict[str, Any]) -> float | int:
    low = schema.get("minimum", 0)
    high = schema.get("maximum", 1 if schema.get("type") == "number" else 3)
    value = (float(low) + float(high)) / 2
    if schema.get("type") == "integer":
        return int(value)
    # Distinct-ish per axis so downstream blending is not a constant.
    nudge = {"relevance": 0.22, "valence": 0.14, "signal": 0.08}.get(field, 0.0)
    return round(min(float(high), value + nudge), 3)


def _array_length(
    field: str, schema: dict[str, Any], root: dict[str, Any], ctx: _Context
) -> int:
    """One entry per scraped id where the caller matches on ids, else a small list."""

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        properties = _resolve(item_schema, root).get("properties", {})
        if "id" in properties and ctx.ids:
            return len(ctx.ids)
        if "subtopic_id" in properties and ctx.subtopic_ids:
            return len(ctx.subtopic_ids)
    if field == "article_ids":
        return min(2, len(ctx.ids)) or 0
    return int(schema.get("minItems", 0)) or 3


def _instance(
    schema: dict[str, Any],
    root: dict[str, Any],
    ctx: _Context,
    field: str = "",
    depth: int = 0,
) -> Any:
    if depth > MAX_DEPTH:
        return None

    schema = _resolve(schema, root)

    # `str | None` becomes anyOf[str, null]; take the first non-null branch.
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if isinstance(options, list):
            concrete = [o for o in options if isinstance(o, dict) and o.get("type") != "null"]
            if concrete:
                return _instance(concrete[0], root, ctx, field, depth + 1)
            return None

    if "const" in schema:
        return schema["const"]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        return schema["enum"][0]

    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "string")

    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        return {
            name: _instance(sub, root, ctx, name, depth + 1)
            for name, sub in properties.items()
        }
    if kind == "array":
        item_schema = schema.get("items")
        if not isinstance(item_schema, dict):
            return []
        count = _array_length(field, schema, root, ctx)
        items = []
        for index in range(count):
            ctx.index = index
            items.append(_instance(item_schema, root, ctx, _singular(field), depth + 1))
        ctx.index = 0
        return items
    if kind == "boolean":
        return True
    if kind in ("number", "integer"):
        return _number_for(field, schema)
    if kind == "null":
        return None
    return _string_for(field, schema, ctx)


def _singular(field: str) -> str:
    if field.endswith("ies"):
        return f"{field[:-3]}y"
    return field[:-1] if field.endswith("s") else field


def _prose(prompt: str) -> str:
    """Free-text path, used when the caller did not ask for JSON."""

    topic = "the requested topic"
    match = re.search(r"^(?:Topic|Theme\(s\)):\s*(.+)$", prompt, re.M)
    if match:
        topic = match.group(1).strip()

    return (
        "Executive Summary\n"
        f"{topic} is being monitored through the AI News Agent pipeline.\n\n"
        "Key Points\n"
        "- Source material is normalised and deduplicated before generation.\n"
        "- Writer and critic stages are separated to improve answer quality.\n"
        "- Citations are attached whenever external sources are available.\n\n"
        "Analysis\n"
        "This mock provider confirms the pipeline is reachable without a local "
        "Ollama model. Enable a real provider for substantive analysis."
    )
