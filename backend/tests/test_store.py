from app.graph.state import RunConfig
from tests.conftest import make_newsletter


async def test_runs_round_trip(db, run_config):
    await db.save_run("run-1", run_config)
    row = await db.get_run("run-1")
    assert row["status"] == "running"
    assert RunConfig.model_validate_json(row["config"]).theme == run_config.theme


async def test_finish_run_stores_the_newsletter(db, run_config):
    await db.save_run("run-1", run_config)
    await db.finish_run("run-1", make_newsletter(), "done")
    row = await db.get_run("run-1")
    assert row["status"] == "done"
    assert row["finished_at"]
    assert "Reef digest" in row["newsletter"]


async def test_finish_run_records_an_error(db, run_config):
    await db.save_run("run-1", run_config)
    await db.finish_run("run-1", None, "error", "boom")
    row = await db.get_run("run-1")
    assert (row["status"], row["error"]) == ("error", "boom")


async def test_missing_run_is_none(db):
    assert await db.get_run("nope") is None


async def test_list_runs_is_newest_first_and_filterable(db, run_config):
    for index in range(3):
        await db.save_run(f"run-{index}", run_config)
    await db.finish_run("run-1", None, "error", "x")

    assert [row["run_id"] for row in await db.list_runs()] == ["run-2", "run-1", "run-0"]
    assert [row["run_id"] for row in await db.list_runs(status="error")] == ["run-1"]
    assert len(await db.list_runs(limit=1)) == 1


async def test_deleting_a_run_removes_its_bookmarks(db, run_config):
    await db.save_run("run-1", run_config)
    await db.add_bookmark("run-1", "a1", "https://x.test/a", "T", "S")
    assert await db.delete_run("run-1") is True
    assert await db.list_bookmarks("run-1") == []
    assert await db.delete_run("run-1") is False


async def test_stale_running_rows_are_retired_on_startup(db, run_config):
    await db.save_run("run-1", run_config)
    assert await db.mark_stale_runs_cancelled() == 1
    row = await db.get_run("run-1")
    assert row["status"] == "cancelled"
    assert "restart" in row["error"]


async def test_prune_keeps_only_the_newest_runs(db, run_config):
    for index in range(5):
        await db.save_run(f"run-{index}", run_config)
    await db.prune_runs(keep=2)
    assert {row["run_id"] for row in await db.list_runs()} == {"run-4", "run-3"}


async def test_bookmarks_are_idempotent_and_removable(db, run_config):
    await db.save_run("run-1", run_config)
    await db.add_bookmark("run-1", "a1", "https://x.test/a", "T", "S")
    await db.add_bookmark("run-1", "a1", "https://x.test/a", "T2", "S")
    rows = await db.list_bookmarks("run-1")
    assert len(rows) == 1 and rows[0]["title"] == "T2"
    assert await db.remove_bookmark("run-1", "a1") is True
    assert await db.remove_bookmark("run-1", "a1") is False


async def test_bookmarks_span_runs_in_the_global_list(db, run_config):
    for index in range(2):
        await db.save_run(f"run-{index}", run_config)
        await db.add_bookmark(f"run-{index}", "a1", "https://x.test/a", "T", "S")
    assert len(await db.list_all_bookmarks()) == 2


async def test_feedback_is_stored_and_summarised(db):
    await db.add_feedback("f1", None, None, 5, "great")
    await db.add_feedback("f2", None, None, 3, None)
    assert await db.feedback_summary() == {"count": 2, "average_rating": 4.0}
    assert len(await db.list_feedback()) == 2


async def test_empty_feedback_summary_has_no_average(db):
    assert await db.feedback_summary() == {"count": 0, "average_rating": None}


async def test_schedules_round_trip(db, run_config):
    await db.create_schedule("s1", ["ocean", "reefs"], "0 9 * * *", run_config)
    row = await db.get_schedule("s1")
    assert row["cron_expr"] == "0 9 * * *"
    assert bool(row["enabled"]) is True

    assert await db.toggle_schedule("s1", False) is True
    assert bool((await db.get_schedule("s1"))["enabled"]) is False
    assert len(await db.list_schedules(enabled_only=True)) == 0

    assert await db.delete_schedule("s1") is True
    assert await db.delete_schedule("s1") is False


async def test_marking_a_schedule_run_records_the_run_id(db, run_config):
    from datetime import datetime, timezone

    await db.create_schedule("s1", [], "0 9 * * *", run_config)
    moment = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)
    await db.mark_schedule_run("s1", "run-9", moment)
    row = await db.get_schedule("s1")
    assert row["last_run_id"] == "run-9"
    assert row["last_run_at"].startswith("2026-08-27T09:00")
