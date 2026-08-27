"""End-to-end graph behaviour with the offline providers.

The mock LLM returns schema-valid JSON, so these exercise the real LLM branches
of every node — not just the heuristic fallbacks.
"""

import pytest

from app.core.config import settings
from app.graph.builder import (
    TOPOLOGY,
    fan_out_research,
    fan_out_summaries,
    route_after_curator,
    route_after_summaries,
)
from app.graph.runner import events_from, new_run_id, run_to_completion
from app.graph.state import (
    ArticleScores,
    Newsletter,
    RawArticle,
    RunConfig,
    ScoredArticle,
    SubTopic,
    article_id,
    canonical_url,
    merge_articles,
    merge_summaries,
)
from app.providers.mock import MockProvider
from tests.conftest import make_summary


class TestCanonicalisation:
    @pytest.mark.parametrize(
        "left,right",
        [
            ("https://a.test/story", "https://www.a.test/story"),
            ("https://a.test/story", "https://a.test/story/"),
            ("https://a.test/story", "https://a.test/story?utm_source=x"),
            ("https://a.test/story", "https://a.test/story#section"),
            ("https://A.TEST/story", "https://a.test/story"),
        ],
    )
    def test_equivalent_urls_collapse_to_one_id(self, left, right):
        assert canonical_url(left) == canonical_url(right)
        assert article_id(left) == article_id(right)

    def test_different_paths_keep_different_ids(self):
        assert article_id("https://a.test/one") != article_id("https://a.test/two")


class TestReducers:
    def _article(self, url: str, content: str = "") -> RawArticle:
        return RawArticle(
            id=article_id(url), subtopic_id="s", url=url, title="t",
            source_name="S", content=content,
        )

    def test_parallel_branches_merge_without_clobbering(self):
        left = [self._article("https://a.test/1")]
        right = [self._article("https://a.test/2")]
        assert len(merge_articles(left, right)) == 2

    def test_duplicate_urls_keep_the_longest_body(self):
        short = [self._article("https://a.test/1", "short")]
        long = [self._article("https://a.test/1", "a much longer body")]
        merged = merge_articles(short, long)
        assert len(merged) == 1 and merged[0].content == "a much longer body"

    def test_none_branches_are_tolerated(self):
        assert merge_articles(None, None) == []
        assert len(merge_articles(None, [self._article("https://a.test/1")])) == 1

    def test_later_summaries_replace_earlier_ones(self):
        first = [make_summary(1, headline="old")]
        second = [make_summary(1, headline="new")]
        merged = merge_summaries(first, second)
        assert len(merged) == 1 and merged[0].headline == "new"


class TestRouting:
    def _state(self, selected=0, attempts=1, target=4):
        return {
            "config": RunConfig(theme="reefs", max_sources=target),
            "selected_ids": [f"id{i}" for i in range(selected)],
            "search_attempts": attempts,
        }

    def test_enough_results_go_straight_to_summaries(self):
        assert route_after_curator(self._state(selected=8)) == "fanout_summaries"

    def test_thin_results_trigger_a_widened_retry(self):
        assert route_after_curator(self._state(selected=1, attempts=1)) == "widen_queries"

    def test_retries_are_capped(self):
        attempts = settings.max_search_attempts
        assert route_after_curator(self._state(selected=1, attempts=attempts)) == "fanout_summaries"

    def test_no_results_after_retries_goes_to_the_composer(self):
        attempts = settings.max_search_attempts
        assert route_after_curator(self._state(selected=0, attempts=attempts)) == "composer"

    def test_factcheck_is_skipped_when_disabled_in_the_run_config(self):
        state = {"config": RunConfig(theme="reefs", enable_factcheck=False)}
        assert route_after_summaries(state) == "composer"

    def test_factcheck_runs_when_enabled(self):
        state = {"config": RunConfig(theme="reefs", enable_factcheck=True)}
        assert route_after_summaries(state) == "factcheck"


class TestFanOut:
    def test_one_research_branch_per_subtopic(self):
        state = {
            "run_id": "r", "config": RunConfig(theme="reefs"), "search_attempts": 1,
            "subtopics": [SubTopic(id=f"s{i}", label="l", query="q") for i in range(3)],
        }
        sends = fan_out_research(state)
        assert len(sends) == 3
        assert {send.node for send in sends} == {"research"}

    def test_summary_fan_out_covers_every_selected_article(self):
        scored = [
            ScoredArticle(
                article=RawArticle(
                    id=f"a{i}", subtopic_id="s", url=f"https://a.test/{i}",
                    title="t", source_name="S",
                ),
                scores=ArticleScores(),
            )
            for i in range(3)
        ]
        state = {
            "run_id": "r", "config": RunConfig(theme="reefs"),
            "selected_ids": ["a0", "a1", "a2"], "scored": scored,
        }
        assert len(fan_out_summaries(state)) == 3

    def test_no_selection_routes_to_the_composer(self):
        state = {
            "run_id": "r", "config": RunConfig(theme="reefs"),
            "selected_ids": [], "scored": [],
        }
        assert fan_out_summaries(state) == "composer"


class TestTopology:
    def test_every_edge_endpoint_is_a_declared_node(self):
        ids = {node["id"] for node in TOPOLOGY["nodes"]}
        for edge in TOPOLOGY["edges"]:
            assert edge["source"] in ids, edge
            assert edge["target"] in ids, edge

    def test_nodes_declare_the_fields_the_ui_renders(self):
        for node in TOPOLOGY["nodes"]:
            assert {"id", "label", "kind", "description"} <= set(node)


class TestEndToEnd:
    async def test_run_produces_a_newsletter_from_verified_sources(self, run_config):
        state = await run_to_completion(
            run_config, run_id=new_run_id(), provider=MockProvider(), persistent=False
        )
        newsletter = state["newsletter"]

        assert isinstance(newsletter, Newsletter)
        assert newsletter.sections and newsletter.sources
        assert not state["errors"]

        items = [item for section in newsletter.sections for item in section.items]
        assert items, "expected at least one story"

        # Nothing may ship that was not actually fetched.
        fetched_urls = {article.url for article in state["raw_articles"]}
        assert {item.url for item in items} <= fetched_urls
        assert {source.url for source in newsletter.sources} <= fetched_urls

    async def test_every_shipped_fact_is_quote_verified(self, run_config):
        state = await run_to_completion(
            run_config, run_id=new_run_id(), provider=MockProvider(), persistent=False
        )
        bodies = {article.url: article.body for article in state["raw_articles"]}

        checked = 0
        for section in state["newsletter"].sections:
            for item in section.items:
                for fact in item.key_facts:
                    assert fact.verified
                    normalise = " ".join(fact.quote.lower().split())
                    body = " ".join(bodies[item.url].lower().split())
                    assert normalise in body
                    checked += 1
        assert checked > 0, "expected the run to produce verifiable facts"

    async def test_the_mock_llm_drives_the_llm_branches_not_the_fallbacks(self, run_config):
        state = await run_to_completion(
            run_config, run_id=new_run_id(), provider=MockProvider(), persistent=False
        )
        items = [i for s in state["newsletter"].sections for i in s.items]
        assert any(item.summarized_by == "llm" for item in items)
        assert any(scored.scored_by == "llm" for scored in state["scored"])

    async def test_the_run_emits_an_event_for_each_stage(self, run_config):
        state = await run_to_completion(
            run_config, run_id=new_run_id(), provider=MockProvider(), persistent=False
        )
        nodes = {event.node for event in state["events"]}
        assert {"planner", "research", "curator", "summarizer", "composer"} <= nodes

    async def test_composer_degrades_gracefully_when_nothing_is_found(self, monkeypatch):
        """No sources must still yield a newsletter that says so, not a crash."""

        class EmptyProvider:
            name = "empty"

            async def search(self, query):
                return []

        # research.py imports the symbol directly, so patch it there.
        monkeypatch.setattr(
            "app.graph.nodes.research.get_providers",
            lambda requested=None: [EmptyProvider()],
        )
        config = RunConfig(theme="a topic with no coverage", subtopic_count=1, max_sources=2)
        state = await run_to_completion(
            config, run_id=new_run_id(), provider=MockProvider(), persistent=False
        )

        newsletter = state["newsletter"]
        assert isinstance(newsletter, Newsletter)
        assert newsletter.degraded is True
        assert newsletter.sections == []
        assert newsletter.notes

    async def test_length_setting_caps_the_number_of_stories(self):
        brief = RunConfig(theme="coral reefs", length="brief", max_sources=40, providers=["mock"])
        state = await run_to_completion(
            brief, run_id=new_run_id(), provider=MockProvider(), persistent=False
        )
        items = [i for s in state["newsletter"].sections for i in s.items]
        assert len(items) <= brief.target_articles


def test_events_from_ignores_non_event_payloads():
    assert events_from({"events": ["not an event", None]}) == []
    assert events_from({}) == []
    assert events_from(None) == []


class TestTopicalityGate:
    """An off-topic story must not be rescued by a generous LLM relevance score."""

    async def test_an_off_topic_article_is_rejected_despite_a_high_llm_score(self):
        from app.graph.nodes.curator import curator_node
        from app.providers.mock import MockProvider
        from tests.conftest import make_article

        on_topic = make_article(
            url="https://reuters.com/on-topic",
            title="Climate technology funding hits record",
            body="A climate technology fund reported record backing this quarter.",
        )
        off_topic = make_article(
            url="https://reuters.com/off-topic",
            title="The Porsche 911 GT3 punches above its weight",
            body="The GT3 piles on power, technology and luxury for the track.",
        )
        state = {
            "config": RunConfig(theme="climate technology", max_sources=10),
            "raw_articles": [on_topic, off_topic],
            "subtopics": [
                SubTopic(id="sub-1", label="Funding", query="climate technology funding",
                         theme="climate technology")
            ],
            "search_attempts": 1,
        }
        for article in (on_topic, off_topic):
            article.subtopic_id = "sub-1"

        result = await curator_node(state, provider=MockProvider())

        assert result["selected_ids"] == [on_topic.id]
        rejected = next(s for s in result["scored"] if s.article.id == off_topic.id)
        assert rejected.verdict == "rejected"
        assert "off-topic" in rejected.reasons[0]
