"""SQLite store for run history, bookmarks, and schedules.

Uses aiosqlite for async access. The checkpointer (LangGraph's own SQLite) is
separate and handles graph resumption; this store is for the application layer.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.core.config import settings
from app.graph.state import Newsletter, RunConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    config      TEXT NOT NULL,
    newsletter  TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    created_at  TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    topic_id    TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    config      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscribers (
    subscriber_id TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookmarks (
    run_id      TEXT NOT NULL,
    article_id  TEXT NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    source_name TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, article_id)
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY,
    themes      TEXT NOT NULL,
    cron_expr   TEXT NOT NULL,
    config      TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    last_run_at TEXT
);
"""


def _ensure_dir() -> None:
    os.makedirs(settings.data_dir, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _connect() -> aiosqlite.Connection:
    _ensure_dir()
    db = await aiosqlite.connect(settings.runs_db)
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    db = await _connect()
    try:
        await db.executescript(_SCHEMA)
        await db.commit()
    finally:
        await db.close()


async def save_run(run_id: str, config: RunConfig) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO runs (run_id, config, status, created_at) "
            "VALUES (?, ?, 'running', ?)",
            (run_id, config.model_dump_json(), _now()),
        )
        await db.commit()
    finally:
        await db.close()


async def finish_run(
    run_id: str,
    newsletter: Newsletter | None,
    status: str = "done",
) -> None:
    db = await _connect()
    try:
        await db.execute(
            "UPDATE runs SET newsletter = ?, status = ?, finished_at = ? "
            "WHERE run_id = ?",
            (
                newsletter.model_dump_json() if newsletter else None,
                status,
                _now(),
                run_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT run_id, config, status, created_at, finished_at "
            "FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_run(run_id: str) -> dict[str, Any] | None:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT run_id, config, newsletter, status, created_at, finished_at "
            "FROM runs WHERE run_id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_run(run_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def add_bookmark(
    run_id: str,
    article_id: str,
    url: str,
    title: str,
    source_name: str,
) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO bookmarks "
            "(run_id, article_id, url, title, source_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, article_id, url, title, source_name, _now()),
        )
        await db.commit()
    finally:
        await db.close()


async def remove_bookmark(run_id: str, article_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "DELETE FROM bookmarks WHERE run_id = ? AND article_id = ?",
            (run_id, article_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def list_bookmarks(run_id: str) -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT article_id, url, title, source_name, created_at "
            "FROM bookmarks WHERE run_id = ? ORDER BY created_at DESC",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def create_schedule(
    schedule_id: str,
    themes: list[str],
    cron_expr: str,
    config: RunConfig,
) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO schedules "
            "(schedule_id, themes, cron_expr, config, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                schedule_id,
                json.dumps(themes),
                cron_expr,
                config.model_dump_json(),
                _now(),
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def list_schedules() -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT schedule_id, themes, cron_expr, config, enabled, "
            "created_at, last_run_at FROM schedules ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def toggle_schedule(schedule_id: str, enabled: bool) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "UPDATE schedules SET enabled = ? WHERE schedule_id = ?",
            (1 if enabled else 0, schedule_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def delete_schedule(schedule_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "DELETE FROM schedules WHERE schedule_id = ?", (schedule_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# --- topics ---


async def create_topic(topic_id: str, title: str, config: RunConfig) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO topics (topic_id, title, config, created_at) "
            "VALUES (?, ?, ?, ?)",
            (topic_id, title, config.model_dump_json(), _now()),
        )
        await db.commit()
    finally:
        await db.close()


async def list_topics() -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT topic_id, title, config, created_at FROM topics ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_topic(topic_id: str) -> dict[str, Any] | None:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT topic_id, title, config, created_at FROM topics WHERE topic_id = ?",
            (topic_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def delete_topic(topic_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute("DELETE FROM topics WHERE topic_id = ?", (topic_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# --- newsletter listing for users ---


async def list_newsletters(limit: int = 50) -> list[dict[str, Any]]:
    """Return completed newsletters for the public user view."""
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT run_id, config, newsletter, created_at, finished_at "
            "FROM runs WHERE status IN ('done', 'partial') AND newsletter IS NOT NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            config = json.loads(row["config"]) if row["config"] else {}
            newsletter = json.loads(row["newsletter"]) if row["newsletter"] else None
            results.append({
                "run_id": row["run_id"],
                "theme": config.get("theme", "Untitled"),
                "title": (newsletter or {}).get("title", config.get("theme", "Untitled")),
                "subtitle": (newsletter or {}).get("subtitle", ""),
                "newsletter": newsletter,
                "created_at": row["created_at"],
                "finished_at": row["finished_at"],
            })
        return results
    finally:
        await db.close()


# --- subscribers ---


async def add_subscriber(subscriber_id: str, email: str, name: str = "") -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO subscribers (subscriber_id, email, name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (subscriber_id, email, name, _now()),
        )
        await db.commit()
    finally:
        await db.close()


async def list_subscribers() -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT subscriber_id, email, name, created_at FROM subscribers ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def delete_subscriber(subscriber_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "DELETE FROM subscribers WHERE subscriber_id = ?", (subscriber_id,)
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_subscriber_emails() -> list[str]:
    db = await _connect()
    try:
        cursor = await db.execute("SELECT email FROM subscribers")
        rows = await cursor.fetchall()
        return [row["email"] for row in rows]
    finally:
        await db.close()
