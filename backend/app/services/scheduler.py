"""Background scheduler: turns stored schedules into actual runs.

The schedules table previously existed with no executor, so a saved schedule
never produced a newsletter. This ticks once a minute, fires every enabled
schedule whose cron expression matches, and records the run against it.

Concurrency is bounded and a schedule already running is skipped rather than
queued: a slow LLM must not let ticks pile up into a thundering herd.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger
from app.graph.runner import new_run_id, run_to_completion
from app.graph.state import Newsletter, RunConfig
from app.services import cron, store

log = get_logger(__name__)

MAX_CONCURRENT_SCHEDULED_RUNS = 2


class Scheduler:
    def __init__(self, tick_seconds: int | None = None) -> None:
        self._tick = tick_seconds or settings.scheduler_tick_seconds
        self._task: asyncio.Task | None = None
        self._jobs: set[asyncio.Task] = set()
        self._running: set[str] = set()
        self._gate = asyncio.Semaphore(MAX_CONCURRENT_SCHEDULED_RUNS)
        self._stopping = asyncio.Event()

    # --- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="scheduler")
        log.info("scheduler started", extra={"tick_seconds": self._tick})

    async def stop(self) -> None:
        """Stop the loop *and* the runs it spawned.

        In-flight runs hold the database and the HTTP client; leaving them
        detached means they keep executing against resources shutdown is busy
        closing, which surfaces as spurious errors after the app has exited.
        """

        self._stopping.set()

        jobs = list(self._jobs)
        for job in jobs:
            job.cancel()
        if self._task is not None:
            self._task.cancel()

        pending = [job for job in (*jobs, self._task) if job is not None]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        self._jobs.clear()
        self._running.clear()
        self._task = None
        log.info("scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # --- loop ------------------------------------------------------------

    async def _loop(self) -> None:
        # Align to the top of the next minute so `matches()` is not evaluated
        # twice inside one minute (which would double-fire a schedule).
        await self._sleep_to_next_minute()
        while not self._stopping.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler tick failed")
            await self._sleep_to_next_minute()

    async def _sleep_to_next_minute(self) -> None:
        now = datetime.now(timezone.utc)
        delay = self._tick - (now.second + now.microsecond / 1_000_000) % self._tick
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), timeout=max(1.0, delay))

    async def tick(self, moment: datetime | None = None) -> list[str]:
        """Fire every schedule due at `moment`. Returns the schedule ids fired."""

        moment = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc)
        due = [row for row in await store.list_schedules(enabled_only=True)
               if self._is_due(row, moment)]

        fired: list[str] = []
        for row in due:
            schedule_id = row["schedule_id"]
            if schedule_id in self._running:
                log.warning("schedule still running, skipping", extra={"schedule": schedule_id})
                continue
            self._running.add(schedule_id)
            self._spawn(self._execute(row, moment), f"schedule:{schedule_id}")
            fired.append(schedule_id)

        if fired:
            log.info("schedules fired", extra={"count": len(fired), "ids": fired})
        return fired

    async def trigger(self, schedule_id: str) -> str:
        """Fire a schedule immediately. Returns the run id it will write to."""

        row = await store.get_schedule(schedule_id)
        if row is None:
            raise KeyError(schedule_id)

        run_id = new_run_id()
        self._running.add(schedule_id)
        self._spawn(
            self._execute(row, datetime.now(timezone.utc), run_id=run_id),
            f"schedule:{schedule_id}:manual",
        )
        return run_id

    def _spawn(self, coro, name: str) -> asyncio.Task:
        """Keep a strong reference: bare create_task results can be GC'd mid-run."""

        task = asyncio.create_task(coro, name=name)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)
        return task

    def _is_due(self, row: dict, moment: datetime) -> bool:
        try:
            schedule = cron.parse(row["cron_expr"])
        except cron.CronError as exc:
            log.warning(
                "invalid cron expression",
                extra={"schedule": row["schedule_id"], "error": str(exc)},
            )
            return False
        if not schedule.matches(moment):
            return False
        return not _already_ran_this_minute(row.get("last_run_at"), moment)

    # --- execution -------------------------------------------------------

    async def _execute(
        self, row: dict, moment: datetime, run_id: str | None = None
    ) -> None:
        schedule_id = row["schedule_id"]
        run_id = run_id or new_run_id()
        try:
            config = _config_from_row(row)
        except Exception:
            log.exception("schedule config is invalid", extra={"schedule": schedule_id})
            self._running.discard(schedule_id)
            return

        # Claim the slot before awaiting the gate so a backed-up scheduler does
        # not fire the same schedule again on the next tick.
        await store.mark_schedule_run(schedule_id, run_id, moment)

        try:
            async with self._gate:
                await store.save_run(run_id, config, source=f"schedule:{schedule_id}")
                log.info(
                    "scheduled run started",
                    extra={"schedule": schedule_id, "run": run_id, "theme": config.theme},
                )
                state = await run_to_completion(config, run_id=run_id)
                newsletter = state.get("newsletter") if isinstance(state, dict) else None
                status = "done" if isinstance(newsletter, Newsletter) else "partial"
                await store.finish_run(run_id, newsletter, status)
                log.info(
                    "scheduled run finished",
                    extra={"schedule": schedule_id, "run": run_id, "status": status},
                )
        except asyncio.CancelledError:
            # Best-effort: the store may already be closing during shutdown.
            with suppress(Exception):
                await store.finish_run(
                    run_id, None, "cancelled", "scheduler shutting down"
                )
            raise
        except Exception as exc:
            log.exception("scheduled run failed", extra={"schedule": schedule_id})
            await store.finish_run(run_id, None, "error", f"{type(exc).__name__}: {exc}")
        finally:
            self._running.discard(schedule_id)


def _already_ran_this_minute(last_run_at: str | None, moment: datetime) -> bool:
    if not last_run_at:
        return False
    try:
        previous = datetime.fromisoformat(last_run_at)
    except ValueError:
        return False
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return previous.replace(second=0, microsecond=0) >= moment.replace(
        second=0, microsecond=0
    )


def _config_from_row(row: dict) -> RunConfig:
    """The schedule's themes win over whatever theme the stored config carries."""

    config = RunConfig.model_validate_json(row["config"])
    themes = json.loads(row["themes"]) if row.get("themes") else []
    themes = [t for t in themes if isinstance(t, str) and t.strip()]
    if not themes:
        return config
    return config.model_copy(update={"theme": themes[0], "extra_themes": themes[1:]})


_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler
