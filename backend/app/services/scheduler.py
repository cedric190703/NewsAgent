"""Background scheduler that executes recurring newsletter schedules.

Runs as an asyncio task started on app startup. Polls enabled schedules
every 60 seconds and executes those that are due.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.core.config import settings
from app.graph.runner import new_run_id, stream_run
from app.graph.state import RunConfig
from app.services import store

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 60  # seconds

# Simple interval mapping: keyword -> hours
_INTERVAL_HOURS: dict[str, int] = {
    "hourly": 1,
    "daily": 24,
    "weekly": 168,
    "monthly": 720,
}


def _parse_interval_hours(cron_expr: str) -> int | None:
    """Parse a cron expression into an interval in hours.

    Supports:
    - Simple keywords: hourly, daily, weekly, monthly
    - 'every Nh' or 'every N hours'
    - Cron-like '0 */N * * *' (every N hours)
    """
    expr = cron_expr.strip().lower()

    if expr in _INTERVAL_HOURS:
        return _INTERVAL_HOURS[expr]

    # "every 6h" or "every 6 hours"
    if expr.startswith("every "):
        rest = expr[6:].strip()
        # Extract number
        num_str = ""
        for ch in rest:
            if ch.isdigit():
                num_str += ch
            else:
                break
        if num_str:
            return int(num_str)

    # Cron-like: "0 */6 * * *" -> every 6 hours
    parts = expr.split()
    if len(parts) == 5 and "*/" in parts[1]:
        try:
            n = int(parts[1].replace("*/", ""))
            return n
        except ValueError:
            pass

    # Default: daily
    return 24


def _is_due(schedule: dict[str, Any], now: datetime) -> bool:
    """Check if a schedule is due to run based on its last_run_at."""
    if not schedule.get("enabled"):
        return False

    interval_h = _parse_interval_hours(schedule.get("cron_expr", "daily"))
    if interval_h is None or interval_h <= 0:
        return False

    last_run = schedule.get("last_run_at")
    if not last_run:
        # Never run — run immediately
        return True

    try:
        last_dt = datetime.fromisoformat(last_run)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True

    next_due = last_dt + timedelta(hours=interval_h)
    return now >= next_due


async def _execute_schedule(schedule: dict[str, Any]) -> None:
    """Execute a schedule: create and run a newsletter for each theme."""
    from app.services.mailer import send_newsletter as _send

    themes = json.loads(schedule["themes"]) if schedule.get("themes") else []
    config_data = json.loads(schedule["config"]) if schedule.get("config") else {}
    schedule_id = schedule["schedule_id"]

    if not themes:
        logger.warning("Schedule %s has no themes, skipping", schedule_id)
        await store.update_schedule_last_run(schedule_id)
        return

    # Find groups matching the themes
    groups = await store.list_groups()
    theme_to_group: dict[str, dict[str, Any] | None] = {}
    for theme in themes:
        matched = None
        for g in groups:
            g_theme = (g.get("theme") or "").strip().lower()
            g_name = g["name"].strip().lower()
            if g_theme == theme.lower() or g_name == theme.lower():
                matched = g
                break
        theme_to_group[theme] = matched

    base_config = RunConfig.model_validate(config_data)

    for theme, group in theme_to_group.items():
        run_id = new_run_id()
        config = base_config.model_copy(update={"theme": theme})
        group_id = group["group_id"] if group else None
        await store.save_run(run_id, config, group_id=group_id)

        try:
            final_newsletter = None
            async for _node, update in stream_run(config, run_id=run_id):
                if (update or {}).get("newsletter") is not None:
                    final_newsletter = update["newsletter"]

            await store.finish_run(
                run_id, final_newsletter, "done" if final_newsletter else "partial"
            )

            if final_newsletter is not None and group_id:
                await store.record_delivery(run_id, [group_id])
                await _send(run_id, [group_id])

            logger.info("Schedule %s: completed run %s for theme '%s'", schedule_id, run_id, theme)
        except Exception:
            logger.exception("Schedule %s: run %s failed", schedule_id, run_id)
            await store.finish_run(run_id, None, "error")

    await store.update_schedule_last_run(schedule_id)


async def _scheduler_loop() -> None:
    """Main scheduler loop — polls for due schedules and executes them."""
    logger.info("Scheduler loop started")
    while True:
        try:
            schedules = await store.list_schedules()
            now = datetime.now(timezone.utc)

            due = [s for s in schedules if _is_due(s, now)]

            if due:
                logger.info("Scheduler: %d schedule(s) due", len(due))

            for sched in due:
                try:
                    logger.info("Executing schedule %s (%s)", sched["schedule_id"], sched.get("cron_expr"))
                    await _execute_schedule(sched)
                except Exception:
                    logger.exception("Failed to execute schedule %s", sched["schedule_id"])

        except Exception:
            logger.exception("Scheduler loop error")

        await asyncio.sleep(_POLL_INTERVAL)


_scheduler_task: asyncio.Task | None = None


def start_scheduler() -> None:
    """Start the background scheduler task. Safe to call once."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        logger.info("Background scheduler started")


def stop_scheduler() -> None:
    """Stop the background scheduler task."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Background scheduler stopped")
    _scheduler_task = None
