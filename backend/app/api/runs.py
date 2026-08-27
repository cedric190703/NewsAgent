"""Run management: create, stream (SSE), history, export, bookmarks, schedules."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import (
    BookmarkRequest,
    BookmarkResponse,
    CreateRunResponse,
    RunDetail,
    RunRequest,
    RunSummary,
    ScheduleRequest,
    ScheduleResponse,
    ScheduleToggleRequest,
)
from app.core.logging import get_logger
from app.graph.builder import TOPOLOGY
from app.graph.runner import events_from, new_run_id, stream_run
from app.graph.state import Newsletter, RunConfig
from app.services import cron, store
from app.services.exporter import ExportError, to_html, to_markdown, to_pdf

log = get_logger(__name__)

router = APIRouter()

EXPORT_FORMATS = {
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "html": ("text/html; charset=utf-8", "html"),
    "pdf": ("application/pdf", "pdf"),
}


def _sse(event: str, payload: str) -> dict[str, str]:
    return {"event": event, "data": payload}


def _error_event(message: str) -> dict[str, str]:
    return _sse("error", json.dumps({"message": message}))


@router.get("/graph/topology", summary="Static description of the LangGraph pipeline")
async def get_topology() -> dict[str, Any]:
    return TOPOLOGY


@router.post("/runs", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(request: RunRequest) -> CreateRunResponse:
    """Register a run. Execution starts when the client opens the stream."""

    run_id = new_run_id()
    await store.save_run(run_id, RunConfig(**request.model_dump()))
    log.info("run created", extra={"run": run_id, "theme": request.theme})
    return CreateRunResponse(run_id=run_id)


@router.get("/runs/{run_id}/stream", summary="Server-sent events for a run")
async def stream_run_events(run_id: str) -> EventSourceResponse:
    """Streams node events, then the finished newsletter.

    A disconnect cancels the generator, so the terminal states (`cancelled`,
    `error`) are written from `finally` — otherwise a closed tab would leave the
    run stuck at `running` forever.
    """

    async def event_generator():
        final_newsletter: Newsletter | None = None
        run_status = "error"
        failure: str | None = None

        try:
            run = await store.get_run(run_id)
            if run is None:
                yield _error_event("Run not found")
                yield _sse("done", json.dumps({"status": "not_found"}))
                run_status = "not_found"
                return

            config = RunConfig.model_validate_json(run["config"])

            async for _node, update in stream_run(config, run_id=run_id):
                update = update or {}
                for evt in events_from(update):
                    yield _sse("node", evt.model_dump_json())
                if update.get("newsletter") is not None:
                    final_newsletter = update["newsletter"]
                for error in update.get("errors") or []:
                    yield _error_event(str(error))

            run_status = "done" if final_newsletter else "partial"

            if final_newsletter is not None:
                yield _sse("newsletter", final_newsletter.model_dump_json())
            yield _sse("done", json.dumps({"status": run_status}))

        except asyncio.CancelledError:
            run_status = "cancelled"
            failure = "client disconnected"
            raise
        except Exception as exc:
            run_status = "error"
            failure = f"{type(exc).__name__}: {exc}"
            log.exception("run failed", extra={"run": run_id})
            yield _error_event(str(exc))
            yield _sse("done", json.dumps({"status": "error"}))
        finally:
            if run_status != "not_found":
                await store.finish_run(run_id, final_newsletter, run_status, failure)
                log.info("run finished", extra={"run": run_id, "status": run_status})

    return EventSourceResponse(event_generator())


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    run_status: str | None = Query(default=None, alias="status"),
) -> list[RunSummary]:
    rows = await store.list_runs(limit, run_status)
    return [RunSummary(**_decode_run(row)) for row in rows]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str) -> RunDetail:
    row = await store.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    decoded = _decode_run(row)
    decoded["newsletter"] = json.loads(row["newsletter"]) if row.get("newsletter") else None
    return RunDetail(**decoded)


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict[str, str]:
    if not await store.delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "deleted"}


@router.get("/runs/{run_id}/export/{fmt}", summary="Download a run as Markdown, HTML or PDF")
async def export_run(run_id: str, fmt: str) -> Response:
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Format must be one of: {', '.join(EXPORT_FORMATS)}",
        )

    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.get("newsletter"):
        raise HTTPException(
            status_code=409,
            detail=f"Run has no newsletter yet (status: {run.get('status')})",
        )

    newsletter = Newsletter.model_validate_json(run["newsletter"])
    media_type, extension = EXPORT_FORMATS[fmt]

    if fmt == "markdown":
        body: str | bytes = to_markdown(newsletter)
    elif fmt == "html":
        body = to_html(newsletter)
    else:
        try:
            body = to_pdf(newsletter)
        except ExportError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="newsletter-{run_id}.{extension}"'
        },
    )


# --- bookmarks -----------------------------------------------------------


@router.post(
    "/runs/{run_id}/bookmarks",
    response_model=BookmarkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_bookmark(run_id: str, request: BookmarkRequest) -> BookmarkResponse:
    if await store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await store.add_bookmark(
        run_id, request.article_id, request.url, request.title, request.source_name
    )
    saved = [
        row
        for row in await store.list_bookmarks(run_id)
        if row["article_id"] == request.article_id
    ]
    return BookmarkResponse(**saved[0])


@router.delete("/runs/{run_id}/bookmarks/{article_id}")
async def remove_bookmark(run_id: str, article_id: str) -> dict[str, str]:
    if not await store.remove_bookmark(run_id, article_id):
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return {"status": "removed"}


@router.get("/runs/{run_id}/bookmarks", response_model=list[BookmarkResponse])
async def list_bookmarks(run_id: str) -> list[BookmarkResponse]:
    return [BookmarkResponse(**row) for row in await store.list_bookmarks(run_id)]


@router.get("/bookmarks", response_model=list[BookmarkResponse], summary="Saved articles")
async def list_all_bookmarks(
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[BookmarkResponse]:
    return [BookmarkResponse(**row) for row in await store.list_all_bookmarks(limit)]


# --- schedules -----------------------------------------------------------


@router.post(
    "/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED
)
async def create_schedule(request: ScheduleRequest) -> ScheduleResponse:
    schedule_id = uuid4().hex
    await store.create_schedule(
        schedule_id, request.themes, request.cron_expr, request.config
    )
    row = await store.get_schedule(schedule_id)
    return _schedule_response(row or {})


@router.get("/schedules", response_model=list[ScheduleResponse])
async def list_schedules() -> list[ScheduleResponse]:
    return [_schedule_response(row) for row in await store.list_schedules()]


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def toggle_schedule(
    schedule_id: str, request: ScheduleToggleRequest
) -> ScheduleResponse:
    if not await store.toggle_schedule(schedule_id, request.enabled):
        raise HTTPException(status_code=404, detail="Schedule not found")
    row = await store.get_schedule(schedule_id)
    return _schedule_response(row or {})


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict[str, str]:
    if not await store.delete_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}


@router.post("/schedules/{schedule_id}/run", response_model=CreateRunResponse)
async def run_schedule_now(schedule_id: str) -> CreateRunResponse:
    """Fire a schedule immediately, without waiting for its cron slot."""

    from app.services.scheduler import get_scheduler

    try:
        run_id = await get_scheduler().trigger(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    return CreateRunResponse(run_id=run_id, status="started")


# --- helpers -------------------------------------------------------------


def _decode_run(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    raw_config = decoded.pop("config", None)
    decoded["config"] = json.loads(raw_config) if raw_config else None
    decoded.pop("newsletter", None)
    return decoded


def _schedule_response(row: dict[str, Any]) -> ScheduleResponse:
    return ScheduleResponse(
        schedule_id=row.get("schedule_id", ""),
        themes=json.loads(row["themes"]) if row.get("themes") else [],
        cron_expr=row.get("cron_expr", ""),
        config=json.loads(row["config"]) if row.get("config") else None,
        enabled=bool(row.get("enabled", 0)),
        created_at=row.get("created_at", ""),
        last_run_at=row.get("last_run_at"),
        last_run_id=row.get("last_run_id"),
        next_run_at=cron.describe_next(row.get("cron_expr", "")),
    )
