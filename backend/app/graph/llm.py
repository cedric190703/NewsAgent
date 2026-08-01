"""Structured JSON calls to the LLM, with graceful failure.

Nodes never depend on the LLM succeeding: `try_json` returns None on failure and
each node falls back to a deterministic heuristic. That is what lets the whole
graph run offline (mock provider) while staying identical in shape.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.providers.base import ChatMessage, LLMProvider

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_semaphore: asyncio.Semaphore | None = None


def _gate() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.llm_max_concurrency))
    return _semaphore


def extract_json(text: str) -> Any | None:
    """Pull the first JSON object/array out of a model response."""

    if not text:
        return None

    candidates: list[str] = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    for candidate in candidates:
        candidate = candidate.strip()
        for opener, closer in (("{", "}"), ("[", "]")):
            start = candidate.find(opener)
            end = candidate.rfind(closer)
            if start == -1 or end <= start:
                continue
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


async def try_json(
    provider: LLMProvider,
    system: str,
    user: str,
    model: type[T],
) -> T | None:
    """Ask for JSON matching `model`. Returns None if the model cannot comply."""

    schema = json.dumps(model.model_json_schema(), separators=(",", ":"))
    prompt = (
        f"{user}\n\n"
        "Reply with a single JSON object only, no prose, no markdown fences. "
        f"It must validate against this JSON schema:\n{schema}"
    )
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=prompt),
    ]

    async with _gate():
        for attempt in range(2):
            try:
                raw = await provider.generate(messages, json_mode=True)
            except Exception:
                return None

            payload = extract_json(raw)
            if payload is None:
                continue
            try:
                return model.model_validate(payload)
            except ValidationError:
                if attempt == 0:
                    messages = [
                        *messages,
                        ChatMessage(role="assistant", content=raw[:2000]),
                        ChatMessage(
                            role="user",
                            content="That did not validate. Return corrected JSON only.",
                        ),
                    ]
                    continue
                return None
    return None


async def try_text(provider: LLMProvider, system: str, user: str) -> str | None:
    async with _gate():
        try:
            result = await provider.generate(
                [
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ]
            )
        except Exception:
            return None
    return (result or "").strip() or None
