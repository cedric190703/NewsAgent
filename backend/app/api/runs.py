"""Run management: create, stream (SSE), history, export, bookmarks, schedules."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.graph.builder import TOPOLOGY
from app.graph.runner import events_from, new_run_id, stream_run
from app.graph.state import (
    GoodNewsMode,
    Length,
    Newsletter,
    RunConfig,
    Tone,
)
from app.services import store
from app.services.exporter import to_html, to_markdown, to_pdf

router = APIRouter()


def _check_admin(x_admin_key: str | None) -> None:
    if x_admin_key != settings.admin_password:
        raise HTTPException(status_code=403, detail="Admin access required")


class RunRequest(RunConfig):
    """Re-export RunConfig so the API schema matches the graph's config."""


@router.get("/graph/topology")
async def get_topology() -> dict[str, Any]:
    return TOPOLOGY


@router.post("/runs")
async def create_run(request: RunRequest, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    _check_admin(x_admin_key)
    run_id = new_run_id()
    config = RunConfig(**request.model_dump())
    await store.save_run(run_id, config)
    return {"run_id": run_id, "status": "created"}


@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str) -> EventSourceResponse:
    """SSE endpoint: streams node events and final newsletter as they happen."""

    async def event_generator():
        try:
            run = await store.get_run(run_id)
            if run is None:
                yield {"event": "error", "data": json.dumps({"message": "Run not found"})}
                return

            config = RunConfig.model_validate_json(run["config"])
            final_newsletter: Newsletter | None = None

            async for node, update in stream_run(config, run_id=run_id):
                for evt in events_from(update):
                    yield {
                        "event": "node",
                        "data": evt.model_dump_json(),
                    }
                if (update or {}).get("newsletter") is not None:
                    final_newsletter = update["newsletter"]
                for error in (update or {}).get("errors") or []:
                    yield {"event": "error", "data": json.dumps({"message": error})}

            status = "done" if final_newsletter else "partial"
            await store.finish_run(run_id, final_newsletter, status)

            if final_newsletter:
                yield {
                    "event": "newsletter",
                    "data": final_newsletter.model_dump_json(),
                }
            yield {"event": "done", "data": json.dumps({"status": status})}

        except Exception as exc:
            await store.finish_run(run_id, None, "error")
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


@router.get("/runs")
async def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    runs = await store.list_runs(limit)
    for run in runs:
        run["config"] = json.loads(run["config"]) if run.get("config") else None
    return runs


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run["config"] = json.loads(run["config"]) if run.get("config") else None
    run["newsletter"] = json.loads(run["newsletter"]) if run.get("newsletter") else None
    return run


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict[str, str]:
    deleted = await store.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "deleted"}


@router.get("/runs/{run_id}/export/{fmt}")
async def export_run(run_id: str, fmt: str) -> Response:
    if fmt not in ("markdown", "html", "pdf"):
        raise HTTPException(status_code=400, detail="Format must be markdown, html, or pdf")

    run = await store.get_run(run_id)
    if run is None or not run.get("newsletter"):
        raise HTTPException(status_code=404, detail="Run or newsletter not found")

    newsletter = Newsletter.model_validate_json(run["newsletter"])

    if fmt == "markdown":
        return Response(
            content=to_markdown(newsletter),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.md"'},
        )
    if fmt == "html":
        return Response(
            content=to_html(newsletter),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{run_id}.html"'},
        )
    try:
        pdf_bytes = to_pdf(newsletter)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.pdf"'},
    )


@router.post("/runs/{run_id}/bookmarks")
async def add_bookmark(
    run_id: str, article_id: str, url: str, title: str, source_name: str
) -> dict[str, str]:
    await store.add_bookmark(run_id, article_id, url, title, source_name)
    return {"status": "bookmarked"}


@router.delete("/runs/{run_id}/bookmarks/{article_id}")
async def remove_bookmark(run_id: str, article_id: str) -> dict[str, str]:
    removed = await store.remove_bookmark(run_id, article_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return {"status": "removed"}


@router.get("/runs/{run_id}/bookmarks")
async def list_bookmarks(run_id: str) -> list[dict[str, Any]]:
    return await store.list_bookmarks(run_id)


@router.post("/schedules")
async def create_schedule(
    themes: list[str], cron_expr: str, config: RunRequest
) -> dict[str, str]:
    schedule_id = uuid4().hex
    run_config = RunConfig(**config.model_dump())
    await store.create_schedule(schedule_id, themes, cron_expr, run_config)
    return {"schedule_id": schedule_id, "status": "created"}


@router.get("/schedules")
async def list_schedules() -> list[dict[str, Any]]:
    schedules = await store.list_schedules()
    for sched in schedules:
        sched["themes"] = json.loads(sched["themes"]) if sched.get("themes") else []
        sched["config"] = json.loads(sched["config"]) if sched.get("config") else None
    return schedules


@router.patch("/schedules/{schedule_id}")
async def toggle_schedule(schedule_id: str, enabled: bool) -> dict[str, str]:
    updated = await store.toggle_schedule(schedule_id, enabled)
    if not updated:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "updated"}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict[str, str]:
    deleted = await store.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"status": "deleted"}


# --- topics (admin) ---


@router.post("/topics")
async def create_topic(
    title: str,
    config: RunRequest,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    topic_id = uuid4().hex[:12]
    run_config = RunConfig(**config.model_dump())
    await store.create_topic(topic_id, title, run_config)
    return {"topic_id": topic_id, "status": "created"}


@router.get("/topics")
async def list_topics() -> list[dict[str, Any]]:
    topics = await store.list_topics()
    for t in topics:
        t["config"] = json.loads(t["config"]) if t.get("config") else None
    return topics


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: str) -> dict[str, Any]:
    topic = await store.get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic["config"] = json.loads(topic["config"]) if topic.get("config") else None
    return topic


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str, x_admin_key: str | None = Header(default=None)) -> dict[str, str]:
    _check_admin(x_admin_key)
    deleted = await store.delete_topic(topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"status": "deleted"}


# --- newsletters (public, for users) ---


@router.get("/newsletters")
async def list_newsletters(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    return await store.list_newsletters(limit)


# --- subscribers (admin) ---


@router.post("/subscribers")
async def add_subscriber(
    email: str,
    name: str = "",
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    subscriber_id = uuid4().hex[:12]
    await store.add_subscriber(subscriber_id, email, name)
    return {"subscriber_id": subscriber_id, "status": "added"}


@router.get("/subscribers")
async def list_subscribers() -> list[dict[str, Any]]:
    return await store.list_subscribers()


@router.delete("/subscribers/{subscriber_id}")
async def delete_subscriber(
    subscriber_id: str,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    deleted = await store.delete_subscriber(subscriber_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subscriber not found")
    return {"status": "deleted"}


# --- send newsletter to mailing list (admin) ---


@router.post("/runs/{run_id}/send")
async def send_newsletter(
    run_id: str,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(x_admin_key)
    from app.services.mailer import send_newsletter as _send
    result = await _send(run_id)
    return result
