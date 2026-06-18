import httpx

from app.core.config import Settings
from app.providers.base import ChatMessage


class OllamaProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self._settings.ollama_model,
            "messages": [message.__dict__ for message in messages],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._settings.ollama_base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return data.get("message", {}).get("content", "").strip()
