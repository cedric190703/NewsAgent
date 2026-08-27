"""Run the graph: streaming iterator + checkpointer lifecycle."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings
from app.core.logging import get_logger
from app.graph.builder import build_graph
from app.graph.state import NewsletterState, NodeEvent, RunConfig, initial_state
from app.providers.base import LLMProvider

log = get_logger(__name__)


def _ensure_data_dir() -> None:
    os.makedirs(settings.data_dir, exist_ok=True)


@asynccontextmanager
async def checkpointer_context(persistent: bool = True):
    """SQLite checkpointer when available, in-memory otherwise."""

    if not persistent:
        yield MemorySaver()
        return

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError:
        log.warning("langgraph-checkpoint-sqlite missing; runs will not be resumable")
        yield MemorySaver()
        return

    _ensure_data_dir()
    async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db) as saver:
        yield saver


def new_run_id() -> str:
    return uuid4().hex


async def stream_run(
    config: RunConfig,
    run_id: str | None = None,
    provider: LLMProvider | None = None,
    persistent: bool = True,
    resume: bool = False,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield (node_name, update) pairs as the graph executes.

    `resume=True` continues an interrupted run from its checkpoint.
    """

    run_id = run_id or new_run_id()
    async with checkpointer_context(persistent) as checkpointer:
        graph = build_graph(provider=provider, checkpointer=checkpointer)
        runnable_config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": settings.graph_recursion_limit,
        }
        payload = None if resume else initial_state(run_id, config)
        started = time.perf_counter()
        log.info(
            "graph run starting",
            extra={
                "run": run_id,
                "theme": config.theme,
                "mode": config.good_news_mode.value,
                "resume": resume,
            },
        )

        async for chunk in graph.astream(
            payload,
            config=runnable_config,
            stream_mode="updates",
        ):
            for node, update in chunk.items():
                yield node, update

        log.info(
            "graph run complete",
            extra={"run": run_id, "seconds": round(time.perf_counter() - started, 2)},
        )


async def run_to_completion(
    config: RunConfig,
    run_id: str | None = None,
    provider: LLMProvider | None = None,
    persistent: bool = True,
) -> NewsletterState:
    run_id = run_id or new_run_id()
    async with checkpointer_context(persistent) as checkpointer:
        graph = build_graph(provider=provider, checkpointer=checkpointer)
        result = await graph.ainvoke(
            initial_state(run_id, config),
            config={
                "configurable": {"thread_id": run_id},
                "recursion_limit": settings.graph_recursion_limit,
            },
        )
    return result  # type: ignore[return-value]


async def get_run_state(run_id: str) -> NewsletterState | None:
    """Read a persisted run back out of the checkpointer."""

    async with checkpointer_context(True) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state({"configurable": {"thread_id": run_id}})
    if snapshot is None or not snapshot.values:
        return None
    return snapshot.values  # type: ignore[return-value]


def events_from(update: dict[str, Any]) -> list[NodeEvent]:
    raw = (update or {}).get("events") or []
    return [e for e in raw if isinstance(e, NodeEvent)]
