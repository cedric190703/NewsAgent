"""Ollama chat provider.

Local models are slow and occasionally drop a connection mid-generation, so
transient failures get one retry. Anything still failing raises: `app.graph.llm`
turns that into a heuristic fallback rather than a failed run.
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.providers.base import ChatMessage

log = get_logger(__name__)

RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.PoolTimeout)


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._settings.ollama_base_url.rstrip("/"),
                timeout=httpx.Timeout(self._settings.llm_timeout_seconds),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
    ) -> str:
        payload: dict = {
            "model": self._settings.ollama_model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": False,
            "options": {"temperature": self._settings.llm_temperature},
        }
        if json_mode:
            payload["format"] = "json"

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self._http().post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return (data.get("message") or {}).get("content", "").strip()
            except RETRYABLE as exc:
                last_error = exc
                log.warning(
                    "ollama call failed, retrying",
                    extra={"attempt": attempt + 1, "error": type(exc).__name__},
                )
                await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:200]
                log.error(
                    "ollama rejected the request",
                    extra={"status": exc.response.status_code, "detail": detail},
                )
                raise

        assert last_error is not None
        raise last_error

    async def health(self) -> dict[str, object]:
        """Is the daemon reachable, and is the configured model actually pulled?"""

        try:
            response = await self._http().get("/api/tags", timeout=5.0)
            response.raise_for_status()
            tags = [model.get("name", "") for model in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as exc:
            return {"reachable": False, "error": type(exc).__name__, "model_available": False}

        wanted = self._settings.ollama_model
        available = wanted in tags or f"{wanted}:latest" in tags
        return {"reachable": True, "model_available": available, "models": tags[:20]}
