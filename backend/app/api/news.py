"""Synchronous briefing API and user feedback.

`POST /api/news/query` runs the same LangGraph pipeline the streaming API uses
and waits for it, returning one structured answer. Use `/api/runs` + the SSE
stream when you want progress; use this when you just want the result.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import FeedbackRequest, FeedbackResponse
from app.core.config import settings
from app.core.logging import get_logger
from app.graph.runner import new_run_id, run_to_completion
from app.schemas.news import NewsQueryRequest, NewsQueryResponse
from app.services import store
from app.services.briefing import build_response, to_run_config

log = get_logger(__name__)

router = APIRouter()

# A briefing runs planner -> research -> curator -> summarizer -> composer, and
# each stage may call the LLM. Bound it so a wedged model cannot pin a worker.
QUERY_TIMEOUT_MULTIPLIER = 12


@router.post("/query", response_model=NewsQueryResponse)
async def query_news(request: NewsQueryRequest) -> NewsQueryResponse:
    config = to_run_config(request)
    run_id = new_run_id()
    timeout = settings.llm_timeout_seconds * QUERY_TIMEOUT_MULTIPLIER

    await store.save_run(run_id, config, source="query")
    log.info("briefing started", extra={"run": run_id, "topic": request.topic})

    try:
        state = await asyncio.wait_for(
            run_to_completion(config, run_id=run_id), timeout=timeout
        )
    except TimeoutError as exc:
        await store.finish_run(run_id, None, "error", "timed out")
        raise HTTPException(
            status_code=504,
            detail=f"The pipeline did not finish within {timeout}s. "
            "Lower `depth`/`max_sources`, or use the streaming run API.",
        ) from exc
    except Exception as exc:
        await store.finish_run(run_id, None, "error", f"{type(exc).__name__}: {exc}")
        log.exception("briefing failed", extra={"run": run_id})
        raise HTTPException(status_code=500, detail="The pipeline failed.") from exc

    newsletter = state.get("newsletter") if isinstance(state, dict) else None
    await store.finish_run(run_id, newsletter, "done" if newsletter else "partial")

    response = build_response(request, run_id, state)
    log.info(
        "briefing finished",
        extra={
            "run": run_id,
            "sources": len(response.sources),
            "confidence": response.confidence,
        },
    )
    return response


@router.post(
    "/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED
)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Persisted so answer quality can be tracked over time."""

    if request.run_id and await store.get_run(request.run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    feedback_id = uuid4().hex
    await store.add_feedback(
        feedback_id,
        request.run_id,
        request.article_id,
        request.rating,
        request.comment,
    )
    log.info(
        "feedback recorded",
        extra={"run": request.run_id, "rating": request.rating},
    )
    return FeedbackResponse(feedback_id=feedback_id)


@router.get("/feedback", summary="Recorded feedback, newest first")
async def list_feedback(
    run_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    return {
        "summary": await store.feedback_summary(),
        "items": await store.list_feedback(run_id, limit),
    }
