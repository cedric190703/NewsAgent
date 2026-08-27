from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        json_mode: bool = False,
    ) -> str:
        """Generate a model response from chat messages.

        When `json_mode` is true the provider should constrain decoding to JSON
        if it supports it; callers must still validate the result.
        """
