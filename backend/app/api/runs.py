"""Run management: create, stream (SSE), history, export, bookmarks, schedules."""

from __future__ import annotations

import asyncio
import json
import logging
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

logger = logging.getLogger(__name__)


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


@router.post("/runs/batch")
async def create_batch_runs(
    body: dict[str, Any],
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create one run per group, using each group's theme.

    Accepts optional overrides for audience, tone, length, good_news_mode,
    subtopic_count, max_sources, enable_factcheck.
    Groups without a theme are skipped.
    """
    _check_admin(x_admin_key)
    groups = await store.list_groups()
    overrides = body or {}

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for g in groups:
        theme = (g.get("theme") or "").strip()
        if not theme:
            skipped.append({"group_id": g["group_id"], "name": g["name"], "reason": "No theme set"})
            continue

        run_id = new_run_id()
        config = RunConfig(
            theme=theme,
            audience=overrides.get("audience", ""),
            tone=overrides.get("tone", "neutral"),
            length=overrides.get("length", "standard"),
            good_news_mode=overrides.get("good_news_mode", "balanced"),
            subtopic_count=overrides.get("subtopic_count", 4),
            max_sources=overrides.get("max_sources", 20),
            enable_factcheck=overrides.get("enable_factcheck", True),
        )
        await store.save_run(run_id, config)
        created.append({
            "run_id": run_id,
            "group_id": g["group_id"],
            "group_name": g["name"],
            "theme": theme,
        })

    return {"created": created, "skipped": skipped}


# Mapping of group name keywords to newsletter themes
_GROUP_THEME_MAP = {
    "ai": "artificial intelligence and machine learning",
    "ml": "artificial intelligence and machine learning",
    "biotech": "biotechnology and pharmaceutical innovation",
    "pharma": "biotechnology and pharmaceutical innovation",
    "energy": "renewable energy and climate technology",
    "environment": "renewable energy and climate technology",
    "finance": "finance banking and fintech",
    "banking": "finance banking and fintech",
    "tech": "technology software and startups",
    "software": "technology software and startups",
    "education": "education and research innovation",
    "research": "education and research innovation",
    "policy": "policy regulation and government",
    "regulation": "policy regulation and government",
    "markets": "financial markets and investing",
    "investing": "financial markets and investing",
    "startup": "startups venture capital and entrepreneurship",
    "vc": "startups venture capital and entrepreneurship",
    "marketing": "marketing growth and digital media",
    "growth": "marketing growth and digital media",
    "design": "design creative and UX innovation",
    "creative": "design creative and UX innovation",
    "product": "product management and strategy",
    "executive": "business leadership and executive strategy",
    "data": "data science analytics and big data",
    "geopolitics": "global affairs and geopolitics",
    "global affairs": "global affairs and geopolitics",
    "asia": "Asia-Pacific business and technology news",
    "europe": "European business and technology news",
    "student": "education and academic research",
    "academic": "education and academic research",
    "consult": "consulting advisory and business strategy",
    "advisor": "consulting advisory and business strategy",
    "quick": "technology and business news summary",
    "deep": "technology and business deep analysis",
    "curated": "technology business and science curated links",
}


def _infer_theme(group_name: str) -> str:
    """Infer a newsletter theme from a group name."""
    name_lower = group_name.lower()
    for keyword, theme in _GROUP_THEME_MAP.items():
        if keyword in name_lower:
            return theme
    # Fallback: use the group name itself as the theme
    return group_name.strip()


@router.post("/runs/batch/execute")
async def execute_batch_runs(
    body: dict[str, Any],
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create AND execute one run per group in the background.

    Uses each group's theme, or infers a theme from the group name if not set.
    Runs are executed sequentially to avoid overwhelming the LLM provider.
    Each finished newsletter is linked to its group and delivered to that
    group's subscribers, unless `auto_send` is false — in which case it is
    still published to the group feed but no email is sent.
    Returns immediately with the list of created run IDs.
    """
    _check_admin(x_admin_key)
    groups = await store.list_groups()
    overrides = body or {}
    auto_send = bool(overrides.get("auto_send", True))

    created: list[dict[str, Any]] = []

    for g in groups:
        theme = (g.get("theme") or "").strip()
        if not theme:
            theme = _infer_theme(g["name"])
            # Persist the inferred theme so it shows up in the UI
            await store.create_group(
                g["group_id"], g["name"], g.get("description", ""), theme
            )

        run_id = new_run_id()
        config = RunConfig(
            theme=theme,
            audience=overrides.get("audience", ""),
            tone=overrides.get("tone", "neutral"),
            length=overrides.get("length", "standard"),
            good_news_mode=overrides.get("good_news_mode", "balanced"),
            subtopic_count=overrides.get("subtopic_count", 4),
            max_sources=overrides.get("max_sources", 20),
            enable_factcheck=overrides.get("enable_factcheck", True),
        )
        await store.save_run(run_id, config, group_id=g["group_id"])
        created.append({
            "run_id": run_id,
            "group_id": g["group_id"],
            "group_name": g["name"],
            "theme": theme,
        })

    asyncio.create_task(_run_batch(created, auto_send))

    verb = "Generating and sending" if auto_send else "Generating"
    return {
        "created": created,
        "skipped": [],
        "message": f"{verb} {len(created)} newsletters in the background.",
    }


async def _run_batch(items: list[dict[str, Any]], auto_send: bool) -> None:
    """Execute queued group runs one at a time, then publish/deliver each."""
    from app.services.mailer import send_newsletter as _send

    for item in items:
        run_id = item["run_id"]
        group_id = item["group_id"]
        try:
            run = await store.get_run(run_id)
            if run is None:
                continue
            config = RunConfig.model_validate_json(run["config"])
            final_newsletter = None
            async for _node, update in stream_run(config, run_id=run_id):
                if (update or {}).get("newsletter") is not None:
                    final_newsletter = update["newsletter"]

            await store.finish_run(
                run_id, final_newsletter, "done" if final_newsletter else "partial"
            )

            if final_newsletter is None:
                continue

            # Publish to the group feed first so it is visible in the user's
            # "My newsletters" even if the group has no subscribers yet or
            # email delivery fails.
            await store.record_delivery(run_id, [group_id])

            if auto_send:
                await _send(run_id, [group_id])
        except Exception:
            logger.exception("Batch run %s failed", run_id)
            await store.finish_run(run_id, None, "error")


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


@router.get("/newsletters/mine")
async def list_my_newsletters(
    token: str = Query(default=""),
    email: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Return newsletters for a subscriber.

    Accepts a subscriber token (preferred) or an email (legacy fallback).
    """
    subscriber = None
    if token:
        subscriber = await store.get_subscriber_by_token(token)
        if subscriber is None:
            raise HTTPException(status_code=403, detail="Invalid token")
        email = subscriber["email"]
    elif email:
        # Legacy fallback — still works but token is preferred
        pass
    else:
        raise HTTPException(status_code=400, detail="Provide token or email")
    return await store.list_newsletters_for_subscriber(email, limit)


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
async def list_subscribers(x_admin_key: str | None = Header(default=None)) -> list[dict[str, Any]]:
    _check_admin(x_admin_key)
    return await store.list_subscribers_with_groups()


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
    group_ids: str | None = Query(default=None),
    x_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(x_admin_key)
    from app.services.mailer import send_newsletter as _send
    ids = group_ids.split(",") if group_ids else []
    result = await _send(run_id, ids or None)
    return result


# --- groups (admin) ---


@router.post("/groups")
async def create_group(
    name: str,
    description: str = "",
    theme: str = "",
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    group_id = uuid4().hex[:12]
    await store.create_group(group_id, name, description, theme)
    return {"group_id": group_id, "status": "created"}


@router.get("/groups")
async def list_groups(x_admin_key: str | None = Header(default=None)) -> list[dict[str, Any]]:
    _check_admin(x_admin_key)
    return await store.list_groups()


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    deleted = await store.delete_group(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "deleted"}


@router.post("/subscribers/{subscriber_id}/groups/{group_id}")
async def add_to_group(
    subscriber_id: str,
    group_id: str,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    await store.add_subscriber_to_group(subscriber_id, group_id)
    return {"status": "added"}


@router.delete("/subscribers/{subscriber_id}/groups/{group_id}")
async def remove_from_group(
    subscriber_id: str,
    group_id: str,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    await store.remove_subscriber_from_group(subscriber_id, group_id)
    return {"status": "removed"}


# --- questions (admin) ---


@router.get("/questions")
async def list_questions(x_admin_key: str | None = Header(default=None)) -> list[dict[str, Any]]:
    _check_admin(x_admin_key)
    return await store.list_questions()


@router.post("/questions")
async def create_question(
    body: dict[str, Any],
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    qid = uuid4().hex[:12]
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Question text is required")
    position = body.get("position", 0)
    await store.create_question(qid, text, position)
    options = body.get("options", [])
    for i, opt in enumerate(options):
        oid = uuid4().hex[:12]
        await store.create_option(oid, qid, opt.get("text", "").strip(), opt.get("group_name", "").strip(), i)
    return {"question_id": qid}


@router.delete("/questions/{question_id}")
async def delete_question(
    question_id: str,
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin(x_admin_key)
    deleted = await store.delete_question(question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "deleted"}


# --- registration (public) ---


@router.post("/register")
async def register(body: dict[str, Any]) -> dict[str, Any]:
    email = body.get("email", "").strip()
    name = body.get("name", "").strip()
    answers = body.get("answers", [])
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not answers:
        raise HTTPException(status_code=400, detail="Answers are required")
    result = await store.register_subscriber(email, name, answers)
    return result


@router.post("/unsubscribe")
async def unsubscribe(body: dict[str, Any]) -> dict[str, str]:
    """Unsubscribe a user by email. Public endpoint — no auth required."""
    email = (body.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    removed = await store.unsubscribe_by_email(email)
    if removed:
        return {"status": "unsubscribed"}
    return {"status": "not_found"}
