"""JSON coaxing and the graceful-failure contract every node depends on."""

import dataclasses

import pytest
from pydantic import BaseModel, Field

from app.graph.llm import extract_json, try_json, try_text
from app.providers.base import ChatMessage


class Payload(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=1.0)


class StubProvider:
    name = "stub"

    def __init__(self, *responses: str | Exception) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, messages, *, json_mode: bool = False) -> str:
        self.calls += 1
        response = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


class TestExtractJson:
    def test_bare_object(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_block(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_unlabelled_fence(self):
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_object_surrounded_by_prose(self):
        assert extract_json('Sure! Here it is:\n{"a": 1}\nHope that helps.') == {"a": 1}

    def test_array_payload(self):
        assert extract_json("[1, 2, 3]") == [1, 2, 3]

    @pytest.mark.parametrize("text", ["", "no json here", "{unclosed", "}{"])
    def test_unparseable_input_returns_none(self, text):
        assert extract_json(text) is None


class TestTryJson:
    async def test_valid_first_response_is_returned(self):
        provider = StubProvider('{"name": "x", "score": 0.5}')
        result = await try_json(provider, "sys", "user", Payload)
        assert (result.name, result.score) == ("x", 0.5)
        assert provider.calls == 1

    async def test_an_invalid_response_is_retried_once(self):
        provider = StubProvider('{"name": "x", "score": 9}', '{"name": "x", "score": 0.5}')
        result = await try_json(provider, "sys", "user", Payload)
        assert result is not None
        assert provider.calls == 2

    async def test_two_invalid_responses_give_up_rather_than_loop(self):
        provider = StubProvider('{"score": 9}', '{"score": 9}')
        assert await try_json(provider, "sys", "user", Payload) is None
        assert provider.calls == 2

    async def test_a_provider_exception_becomes_none_not_a_crash(self):
        """This is what lets every node fall back to heuristics."""

        provider = StubProvider(RuntimeError("ollama is down"))
        assert await try_json(provider, "sys", "user", Payload) is None

    async def test_the_schema_is_included_in_the_prompt(self):
        captured = {}

        class Capturing(StubProvider):
            async def generate(self, messages, *, json_mode: bool = False):
                captured["prompt"] = messages[-1].content
                captured["json_mode"] = json_mode
                return '{"name": "x", "score": 0.5}'

        await try_json(Capturing(), "sys", "user", Payload)
        assert "JSON schema" in captured["prompt"]
        assert captured["json_mode"] is True


class TestTryText:
    async def test_text_is_stripped(self):
        assert await try_text(StubProvider("  hello  "), "sys", "user") == "hello"

    async def test_empty_output_is_none(self):
        assert await try_text(StubProvider("   "), "sys", "user") is None

    async def test_provider_failure_is_none(self):
        assert await try_text(StubProvider(RuntimeError("down")), "sys", "user") is None

    async def test_json_mode_is_not_requested_for_text(self):
        captured = {}

        class Capturing(StubProvider):
            async def generate(self, messages, *, json_mode: bool = False):
                captured["json_mode"] = json_mode
                return "text"

        await try_text(Capturing(), "sys", "user")
        assert captured["json_mode"] is False


def test_chat_message_is_immutable():
    """Prompts are built by several nodes; a shared message must not be edited."""

    message = ChatMessage(role="user", content="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.content = "y"
