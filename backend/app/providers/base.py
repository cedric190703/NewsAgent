from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class LLMProvider(Protocol):
    async def generate(self, messages: list[ChatMessage]) -> str:
        """Generate a model response from chat messages."""
