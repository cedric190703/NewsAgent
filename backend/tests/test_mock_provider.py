"""The offline provider must return schema-valid JSON, so tests and offline runs
exercise the real LLM branches instead of only the heuristic fallbacks."""

from pydantic import BaseModel, Field

from app.graph.llm import extract_json, try_json
from app.graph.nodes.composer import LlmNewsletter
from app.graph.nodes.curator import CuratorBatch
from app.graph.nodes.factcheck import LlmConflicts
from app.graph.nodes.planner import PlannerOutput
from app.graph.nodes.summarizer import LlmSummary, _verify
from app.providers.base import ChatMessage
from app.providers.mock import MockProvider


class TestSchemaCompliance:
    async def test_planner_output_validates(self):
        result = await try_json(
            MockProvider(), "sys", "Theme: coral reefs\nBreak into 3 angles", PlannerOutput
        )
        assert result is not None
        assert len(result.subtopics) == 3

    async def test_planner_angles_are_distinct(self):
        result = await try_json(
            MockProvider(), "sys", "Theme: coral reefs\nangles", PlannerOutput
        )
        queries = [subtopic.query for subtopic in result.subtopics]
        assert len(set(queries)) == len(queries)

    async def test_curator_echoes_back_the_exact_ids_it_was_given(self):
        prompt = "Items:\n---\nid: aaaa1111bbbb2222\n---\nid: cccc3333dddd4444"
        result = await try_json(MockProvider(), "sys", prompt, CuratorBatch)
        assert [item.id for item in result.items] == ["aaaa1111bbbb2222", "cccc3333dddd4444"]

    async def test_curator_scores_stay_within_the_rubric_range(self):
        prompt = "Items:\n---\nid: aaaa1111bbbb2222"
        result = await try_json(MockProvider(), "sys", prompt, CuratorBatch)
        item = result.items[0]
        for value in (item.relevance, item.valence, item.signal):
            assert 0.0 <= value <= 1.0

    async def test_summary_quotes_appear_verbatim_in_the_article(self):
        body = (
            "A twelve-month pilot reported a 34 percent improvement against baseline. "
            "Researchers said the dataset was released for independent review. "
            "Funding for a wider rollout was approved in March."
        )
        prompt = f"Title: Reef study\n\nArticle text:\n{body}\n\nWrite a factual headline"
        result = await try_json(MockProvider(), "sys", prompt, LlmSummary)

        assert result.key_facts
        for fact in result.key_facts:
            assert _verify(fact.quote, body), fact.quote

    async def test_summary_headline_comes_from_the_article_title(self):
        prompt = "Title: Reef study finds recovery\n\nArticle text:\nSome body text here."
        result = await try_json(MockProvider(), "sys", prompt, LlmSummary)
        assert result.headline == "Reef study finds recovery"

    async def test_composer_output_validates(self):
        prompt = "Theme(s): reefs\nSections:\n---\nsubtopic_id: sub-1\nangle: Recovery"
        result = await try_json(MockProvider(), "sys", prompt, LlmNewsletter)
        assert result.title and result.intro
        assert [section.subtopic_id for section in result.sections] == ["sub-1"]

    async def test_factcheck_output_validates(self):
        prompt = "Claims:\n---\nid: aaaa1111\nclaim: X\n---\nid: bbbb2222\nclaim: Y"
        result = await try_json(MockProvider(), "sys", prompt, LlmConflicts)
        assert result is not None


class TestSchemaWalker:
    async def test_optional_fields_and_enums_are_handled(self):
        class Nested(BaseModel):
            flag: bool
            count: int = Field(ge=2, le=8)

        class Payload(BaseModel):
            maybe: str | None = None
            choice: str = Field(default="a")
            nested: Nested
            items: list[Nested] = Field(default_factory=list)

        result = await try_json(MockProvider(), "sys", "anything", Payload)
        assert result is not None
        assert 2 <= result.nested.count <= 8
        assert isinstance(result.nested.flag, bool)

    async def test_max_length_constraints_are_respected(self):
        class Payload(BaseModel):
            label: str = Field(max_length=10)

        result = await try_json(MockProvider(), "sys", "anything", Payload)
        assert len(result.label) <= 10

    async def test_the_same_prompt_always_yields_the_same_answer(self):
        provider = MockProvider()
        messages = [ChatMessage(role="user", content="Theme: reefs")]
        assert await provider.generate(messages) == await provider.generate(messages)


class TestProseFallback:
    async def test_a_non_json_prompt_returns_readable_prose(self):
        output = await MockProvider().generate(
            [ChatMessage(role="user", content="Topic: reef restoration")]
        )
        assert "Executive Summary" in output
        assert "reef restoration" in output
        assert extract_json(output) is None
