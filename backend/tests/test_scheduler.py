"""The scheduler that makes stored schedules actually produce newsletters."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.graph.state import RunConfig
from app.services import store
from app.services.scheduler import Scheduler, _already_ran_this_minute, _config_from_row

NINE_AM = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
async def scheduler(db):
    instance = Scheduler(tick_seconds=1)
    yield instance
    await instance.stop()


async def wait_for(predicate, timeout: float = 10.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(0.05)
    return False


class TestDueDetection:
    async def test_a_matching_schedule_fires(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["reefs"], "0 9 * * *", run_config)
        assert await scheduler.tick(NINE_AM) == ["s1"]

    async def test_a_non_matching_schedule_does_not_fire(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["reefs"], "0 9 * * *", run_config)
        assert await scheduler.tick(NINE_AM + timedelta(hours=1)) == []

    async def test_a_disabled_schedule_does_not_fire(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["reefs"], "0 9 * * *", run_config)
        await store.toggle_schedule("s1", False)
        assert await scheduler.tick(NINE_AM) == []

    async def test_a_broken_cron_expression_is_skipped_not_fatal(self, scheduler, db, run_config):
        await store.create_schedule("bad", [], "not-a-cron", run_config)
        await store.create_schedule("good", [], "0 9 * * *", run_config)
        assert await scheduler.tick(NINE_AM) == ["good"]

    async def test_the_same_minute_does_not_fire_twice(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["reefs"], "0 9 * * *", run_config)
        assert await scheduler.tick(NINE_AM) == ["s1"]
        await wait_for(lambda: _finished(("s1",)))
        assert await scheduler.tick(NINE_AM) == []

    async def test_a_schedule_still_running_is_skipped(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["reefs"], "* * * * *", run_config)
        scheduler._running.add("s1")
        assert await scheduler.tick(NINE_AM) == []


class TestExecution:
    async def test_a_fired_schedule_produces_a_finished_run(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["coral reef restoration"], "0 9 * * *", run_config)
        await scheduler.tick(NINE_AM)

        assert await wait_for(_run_finished), "the scheduled run never completed"
        runs = await store.list_runs()
        assert runs[0]["source"] == "schedule:s1"
        assert runs[0]["status"] == "done"

    async def test_the_run_is_linked_back_to_the_schedule(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["coral reef restoration"], "0 9 * * *", run_config)
        await scheduler.tick(NINE_AM)
        await wait_for(_run_finished)

        row = await store.get_schedule("s1")
        assert row["last_run_id"]
        assert (await store.get_run(row["last_run_id"]))["status"] == "done"

    async def test_manual_trigger_runs_immediately(self, scheduler, db, run_config):
        await store.create_schedule("s1", ["coral reef restoration"], "0 3 1 1 *", run_config)
        run_id = await scheduler.trigger("s1")
        assert await wait_for(_run_finished)
        assert (await store.get_run(run_id))["status"] == "done"

    async def test_triggering_an_unknown_schedule_raises(self, scheduler, db):
        with pytest.raises(KeyError):
            await scheduler.trigger("nope")


class TestLifecycle:
    async def test_start_and_stop_are_idempotent(self, scheduler):
        scheduler.start()
        scheduler.start()
        assert scheduler.is_running
        await scheduler.stop()
        await scheduler.stop()
        assert not scheduler.is_running


class TestConfigResolution:
    def test_schedule_themes_override_the_stored_config(self, run_config):
        row = {
            "config": run_config.model_dump_json(),
            "themes": '["ocean", "reefs", "kelp"]',
        }
        config = _config_from_row(row)
        assert config.theme == "ocean"
        assert config.extra_themes == ["reefs", "kelp"]

    def test_an_empty_theme_list_keeps_the_stored_config(self, run_config):
        row = {"config": run_config.model_dump_json(), "themes": "[]"}
        assert _config_from_row(row).theme == run_config.theme

    def test_other_config_fields_survive_the_override(self):
        config = RunConfig(theme="original theme", max_sources=17, providers=["mock"])
        row = {"config": config.model_dump_json(), "themes": '["y"]'}
        resolved = _config_from_row(row)
        assert (resolved.theme, resolved.max_sources) == ("y", 17)


class TestDoubleFireGuard:
    def test_a_run_in_the_same_minute_counts_as_already_run(self):
        assert _already_ran_this_minute("2026-08-27T09:00:30+00:00", NINE_AM) is True

    def test_an_earlier_run_does_not_block(self):
        assert _already_ran_this_minute("2026-08-27T08:00:00+00:00", NINE_AM) is False

    @pytest.mark.parametrize("value", [None, "", "garbage"])
    def test_missing_or_unparseable_timestamps_do_not_block(self, value):
        assert _already_ran_this_minute(value, NINE_AM) is False

    def test_naive_timestamps_are_treated_as_utc(self):
        assert _already_ran_this_minute("2026-08-27T09:00:00", NINE_AM) is True


async def _run_finished() -> bool:
    runs = await store.list_runs(limit=1)
    return bool(runs) and runs[0]["status"] in {"done", "partial", "error"}


async def _finished(schedule_ids) -> bool:
    for schedule_id in schedule_ids:
        row = await store.get_schedule(schedule_id)
        if not row or not row["last_run_id"]:
            return False
    return True
