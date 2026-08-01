r"""Graph wiring.

    START -> planner
    planner   --Send fan-out--> research (one branch per sub-topic, parallel)
    research  --fan-in-------->  curator
    curator   --conditional--->  widen_queries -> research   (retry, max attempts)
                             ->  fanout_summaries
                             ->  composer                    (degraded, no results)
    fanout_summaries --Send--> summarizer (one branch per article, parallel)
    summarizer --fan-in------>  collect_summaries
    collect_summaries --cond-> factcheck -> composer -> END
                        \----> composer (fact-check disabled)
"""

from __future__ import annotations

from functools import partial
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.core.config import settings
from app.graph.nodes.composer import composer_node
from app.graph.nodes.curator import curator_node
from app.graph.nodes.factcheck import factcheck_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.research import research_node, widen_queries_node
from app.graph.nodes.summarizer import summarizer_node
from app.graph.state import (
    NewsletterState,
    ResearchTask,
    RunConfig,
    ScoredArticle,
    SummaryTask,
    event,
)
from app.providers.base import LLMProvider
from app.providers.factory import get_llm_provider

NODE_ORDER = [
    "planner",
    "research",
    "curator",
    "widen_queries",
    "summarizer",
    "factcheck",
    "composer",
]

TOPOLOGY: dict[str, Any] = {
    "nodes": [
        {"id": "planner", "label": "Planner", "kind": "single",
         "description": "Theme -> structured search angles"},
        {"id": "research", "label": "Research", "kind": "parallel",
         "description": "One branch per angle, real search providers"},
        {"id": "curator", "label": "Curator", "kind": "single",
         "description": "Relevance / recency / credibility / good-news axes"},
        {"id": "widen_queries", "label": "Widen Queries", "kind": "retry",
         "description": "Conditional retry when results are too thin"},
        {"id": "summarizer", "label": "Summarizer", "kind": "parallel",
         "description": "One branch per article, quote-verified facts"},
        {"id": "factcheck", "label": "Fact-check & Dedup", "kind": "conditional",
         "description": "Cross-checks claims, flags conflicts"},
        {"id": "composer", "label": "Composer", "kind": "single",
         "description": "Assembles the newsletter"},
    ],
    "edges": [
        {"source": "planner", "target": "research", "kind": "fanout"},
        {"source": "research", "target": "curator", "kind": "fanin"},
        {"source": "curator", "target": "widen_queries", "kind": "conditional",
         "label": "too few results"},
        {"source": "widen_queries", "target": "research", "kind": "retry"},
        {"source": "curator", "target": "summarizer", "kind": "fanout", "label": "ok"},
        {"source": "curator", "target": "composer", "kind": "conditional",
         "label": "no results"},
        {"source": "summarizer", "target": "factcheck", "kind": "fanin"},
        {"source": "summarizer", "target": "composer", "kind": "conditional",
         "label": "fact-check off"},
        {"source": "factcheck", "target": "composer", "kind": "normal"},
    ],
}


# --- fan-out helpers -----------------------------------------------------


def fan_out_research(state: NewsletterState) -> list[Send]:
    config: RunConfig = state["config"]
    attempt = state.get("search_attempts", 1)
    return [
        Send(
            "research",
            ResearchTask(
                run_id=state["run_id"],
                config=config,
                subtopic=subtopic,
                attempt=attempt,
            ),
        )
        for subtopic in state.get("subtopics", [])
    ]


async def fanout_summaries_node(state: NewsletterState) -> dict[str, Any]:
    """Marker node so the UI sees the fan-out boundary explicitly."""

    selected = len(state.get("selected_ids", []))
    return {
        "events": [
            event(
                "summarizer",
                "running",
                detail=f"Fanning out {selected} article summaries",
                counts={"branches": selected},
            )
        ]
    }


def fan_out_summaries(state: NewsletterState) -> list[Send] | str:
    config: RunConfig = state["config"]
    selected_ids = set(state.get("selected_ids", []))
    by_id: dict[str, ScoredArticle] = {
        item.article.id: item for item in state.get("scored", [])
    }

    sends = [
        Send(
            "summarizer",
            SummaryTask(
                run_id=state["run_id"],
                config=config,
                scored=by_id[article_id],
            ),
        )
        for article_id in selected_ids
        if article_id in by_id
    ]
    return sends or "composer"


# --- conditional routing -------------------------------------------------


def route_after_curator(
    state: NewsletterState,
) -> Literal["widen_queries", "fanout_summaries", "composer"]:
    selected = len(state.get("selected_ids", []))
    attempts = state.get("search_attempts", 1)
    target = min(state["config"].target_articles, settings.min_relevant_results)

    if selected >= target:
        return "fanout_summaries"
    if attempts < settings.max_search_attempts:
        return "widen_queries"
    if selected > 0:
        return "fanout_summaries"
    return "composer"


async def collect_summaries_node(state: NewsletterState) -> dict[str, Any]:
    """Fan-in join for the parallel summarizer branches."""

    summaries = state.get("summaries", [])
    facts = sum(len(summary.key_facts) for summary in summaries)
    return {
        "events": [
            event(
                "summarizer",
                "done",
                detail=f"{len(summaries)} summaries, {facts} verified facts",
                counts={"summaries": len(summaries), "facts": facts},
            )
        ]
    }


def route_after_summaries(state: NewsletterState) -> Literal["factcheck", "composer"]:
    config: RunConfig = state["config"]
    if config.enable_factcheck and settings.enable_factcheck:
        return "factcheck"
    return "composer"


# --- builder -------------------------------------------------------------


def build_graph(
    provider: LLMProvider | None = None,
    checkpointer: Any | None = None,
):
    provider = provider or get_llm_provider()
    builder = StateGraph(NewsletterState)

    builder.add_node("planner", partial(planner_node, provider=provider))
    builder.add_node("research", research_node)
    builder.add_node("curator", partial(curator_node, provider=provider))
    builder.add_node("widen_queries", widen_queries_node)
    builder.add_node("fanout_summaries", fanout_summaries_node)
    builder.add_node("summarizer", partial(summarizer_node, provider=provider))
    builder.add_node("collect_summaries", collect_summaries_node)
    builder.add_node("factcheck", partial(factcheck_node, provider=provider))
    builder.add_node("composer", partial(composer_node, provider=provider))

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", fan_out_research, ["research"])
    builder.add_edge("research", "curator")
    builder.add_conditional_edges(
        "curator",
        route_after_curator,
        ["widen_queries", "fanout_summaries", "composer"],
    )
    builder.add_conditional_edges("widen_queries", fan_out_research, ["research"])
    builder.add_conditional_edges(
        "fanout_summaries", fan_out_summaries, ["summarizer", "composer"]
    )
    builder.add_edge("summarizer", "collect_summaries")
    builder.add_conditional_edges(
        "collect_summaries", route_after_summaries, ["factcheck", "composer"]
    )
    builder.add_edge("factcheck", "composer")
    builder.add_edge("composer", END)

    return builder.compile(checkpointer=checkpointer)
