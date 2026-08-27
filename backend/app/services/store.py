"""SQLite store for run history, bookmarks, feedback, and schedules.

One connection is opened for the process and guarded by a lock. The previous
open/close-per-query approach paid a file-open and a WAL handshake on every
call, and SSE streaming issues a lot of small writes. LangGraph's own SQLite
checkpointer is separate and handles graph resumption; this store is the
application layer.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.core.config import settings
from app.core.logging import get_logger
from app.graph.state import Newsletter, RunConfig

log = get_logger(__name__)

RunStatus = str  # "running" | "done" | "partial" | "error" | "cancelled"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    config      TEXT NOT NULL,
    newsletter  TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    error       TEXT,
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status  ON runs (status);

CREATE TABLE IF NOT EXISTS bookmarks (
    run_id      TEXT NOT NULL,
    article_id  TEXT NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    source_name TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_created ON bookmarks (created_at DESC);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY,
    run_id      TEXT,
    article_id  TEXT,
    rating      INTEGER NOT NULL,
    comment     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_run ON feedback (run_id);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY,
    themes      TEXT NOT NULL,
    cron_expr   TEXT NOT NULL,
    config      TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    last_run_at TEXT,
    last_run_id TEXT
);
"""

# Columns added after the first release; SQLite has no "ADD COLUMN IF NOT EXISTS".
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("runs", "error", "ALTER TABLE runs ADD COLUMN error TEXT"),
    ("runs", "source", "ALTER TABLE runs ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"),
    ("schedules", "last_run_id", "ALTER TABLE schedules ADD COLUMN last_run_id TEXT"),
)

_db: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _conn() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("store.init_db() has not been called")
    return _db


async def init_db() -> None:
    """Open the connection and bring the schema up to date. Idempotent."""

    global _db
    async with _lock:
        if _db is not None:
            return
        os.makedirs(settings.data_dir, exist_ok=True)
        db = await aiosqlite.connect(settings.runs_db)
        db.row_factory = aiosqlite.Row
        # WAL lets the SSE reader and the scheduler writer coexist.
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(_SCHEMA)
        await _migrate(db)
        await db.commit()
        _db = db
        log.info("store ready", extra={"path": settings.runs_db})


async def _migrate(db: aiosqlite.Connection) -> None:
    for table, column, statement in _MIGRATIONS:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        columns = {row["name"] for row in await cursor.fetchall()}
        if column not in columns:
            await db.execute(statement)
            log.info("migrated schema", extra={"table": table, "column": column})


async def close_db() -> None:
    global _db
    async with _lock:
        if _db is not None:
            await _db.close()
            _db = None


async def _write(sql: str, params: tuple = ()) -> int:
    db = await _conn()
    async with _lock:
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.rowcount


async def _rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    db = await _conn()
    cursor = await db.execute(sql, params)
    return [dict(row) for row in await cursor.fetchall()]


async def _row(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = await _rows(sql, params)
    return rows[0] if rows else None


# --- runs ----------------------------------------------------------------


async def save_run(run_id: str, config: RunConfig, source: str = "manual") -> None:
    await _write(
        "INSERT OR REPLACE INTO runs (run_id, config, status, source, created_at) "
        "VALUES (?, ?, 'running', ?, ?)",
        (run_id, config.model_dump_json(), source, _now()),
    )


async def finish_run(
    run_id: str,
    newsletter: Newsletter | None,
    status: RunStatus = "done",
    error: str | None = None,
) -> None:
    await _write(
        "UPDATE runs SET newsletter = ?, status = ?, error = ?, finished_at = ? "
        "WHERE run_id = ?",
        (
            newsletter.model_dump_json() if newsletter else None,
            status,
            error,
            _now(),
            run_id,
        ),
    )


async def list_runs(limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
    if status:
        return await _rows(
            "SELECT run_id, config, status, error, source, created_at, finished_at "
            "FROM runs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    return await _rows(
        "SELECT run_id, config, status, error, source, created_at, finished_at "
        "FROM runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


async def get_run(run_id: str) -> dict[str, Any] | None:
    return await _row(
        "SELECT run_id, config, newsletter, status, error, source, created_at, "
        "finished_at FROM runs WHERE run_id = ?",
        (run_id,),
    )


async def delete_run(run_id: str) -> bool:
    deleted = await _write("DELETE FROM runs WHERE run_id = ?", (run_id,))
    if deleted:
        await _write("DELETE FROM bookmarks WHERE run_id = ?", (run_id,))
    return deleted > 0


async def mark_stale_runs_cancelled() -> int:
    """A run left 'running' by a crash or restart can never resume; retire it.

    Called at startup so history does not fill with rows that spin forever.
    """

    return await _write(
        "UPDATE runs SET status = 'cancelled', error = 'interrupted by restart', "
        "finished_at = ? WHERE status = 'running'",
        (_now(),),
    )


async def prune_runs(keep: int | None = None) -> int:
    """Keep the newest `keep` runs; drop the rest with their bookmarks."""

    keep = keep if keep is not None else settings.run_history_limit
    await _write(
        "DELETE FROM bookmarks WHERE run_id IN ("
        "  SELECT run_id FROM runs ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
        (keep,),
    )
    return await _write(
        "DELETE FROM runs WHERE run_id IN ("
        "  SELECT run_id FROM runs ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
        (keep,),
    )


# --- bookmarks -----------------------------------------------------------


async def add_bookmark(
    run_id: str,
    article_id: str,
    url: str,
    title: str,
    source_name: str,
) -> None:
    await _write(
        "INSERT OR REPLACE INTO bookmarks "
        "(run_id, article_id, url, title, source_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, article_id, url, title, source_name, _now()),
    )


async def remove_bookmark(run_id: str, article_id: str) -> bool:
    removed = await _write(
        "DELETE FROM bookmarks WHERE run_id = ? AND article_id = ?",
        (run_id, article_id),
    )
    return removed > 0


async def list_bookmarks(run_id: str) -> list[dict[str, Any]]:
    return await _rows(
        "SELECT run_id, article_id, url, title, source_name, created_at "
        "FROM bookmarks WHERE run_id = ? ORDER BY created_at DESC",
        (run_id,),
    )


async def list_all_bookmarks(limit: int = 200) -> list[dict[str, Any]]:
    """Every saved article across runs — the reading list, not a per-run view."""

    return await _rows(
        "SELECT run_id, article_id, url, title, source_name, created_at "
        "FROM bookmarks ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


# --- feedback ------------------------------------------------------------


async def add_feedback(
    feedback_id: str,
    run_id: str | None,
    article_id: str | None,
    rating: int,
    comment: str | None,
) -> None:
    await _write(
        "INSERT OR REPLACE INTO feedback "
        "(feedback_id, run_id, article_id, rating, comment, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (feedback_id, run_id, article_id, rating, comment, _now()),
    )


async def list_feedback(run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if run_id:
        return await _rows(
            "SELECT * FROM feedback WHERE run_id = ? ORDER BY created_at DESC LIMIT ?",
            (run_id, limit),
        )
    return await _rows(
        "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)
    )


async def feedback_summary() -> dict[str, Any]:
    row = await _row(
        "SELECT COUNT(*) AS count, AVG(rating) AS average FROM feedback"
    )
    count = int((row or {}).get("count") or 0)
    average = (row or {}).get("average")
    return {"count": count, "average_rating": round(average, 2) if average else None}


# --- schedules -----------------------------------------------------------


async def create_schedule(
    schedule_id: str,
    themes: list[str],
    cron_expr: str,
    config: RunConfig,
) -> None:
    await _write(
        "INSERT OR REPLACE INTO schedules "
        "(schedule_id, themes, cron_expr, config, enabled, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (schedule_id, json.dumps(themes), cron_expr, config.model_dump_json(), _now()),
    )


async def list_schedules(enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = (
        "SELECT schedule_id, themes, cron_expr, config, enabled, created_at, "
        "last_run_at, last_run_id FROM schedules"
    )
    if enabled_only:
        sql += " WHERE enabled = 1"
    return await _rows(f"{sql} ORDER BY created_at DESC")


async def get_schedule(schedule_id: str) -> dict[str, Any] | None:
    return await _row(
        "SELECT schedule_id, themes, cron_expr, config, enabled, created_at, "
        "last_run_at, last_run_id FROM schedules WHERE schedule_id = ?",
        (schedule_id,),
    )


async def toggle_schedule(schedule_id: str, enabled: bool) -> bool:
    updated = await _write(
        "UPDATE schedules SET enabled = ? WHERE schedule_id = ?",
        (1 if enabled else 0, schedule_id),
    )
    return updated > 0


async def mark_schedule_run(schedule_id: str, run_id: str, when: datetime) -> None:
    await _write(
        "UPDATE schedules SET last_run_at = ?, last_run_id = ? WHERE schedule_id = ?",
        (when.astimezone(timezone.utc).isoformat(), run_id, schedule_id),
    )


async def delete_schedule(schedule_id: str) -> bool:
    deleted = await _write(
        "DELETE FROM schedules WHERE schedule_id = ?", (schedule_id,)
    )
    return deleted > 0
