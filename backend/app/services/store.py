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

CREATE TABLE IF NOT EXISTS groups (
    group_id    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    theme       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriber_groups (
    subscriber_id TEXT NOT NULL,
    group_id      TEXT NOT NULL,
    PRIMARY KEY (subscriber_id, group_id),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(subscriber_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS run_deliveries (
    run_id      TEXT NOT NULL,
    group_id    TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (run_id, group_id),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS questions (
    question_id   TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    position      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question_options (
    option_id     TEXT PRIMARY KEY,
    question_id   TEXT NOT NULL,
    text          TEXT NOT NULL,
    group_name    TEXT NOT NULL DEFAULT '',
    position      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subscriber_responses (
    subscriber_id TEXT NOT NULL,
    question_id   TEXT NOT NULL,
    option_id     TEXT NOT NULL,
    answered_at   TEXT NOT NULL,
    PRIMARY KEY (subscriber_id, question_id),
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(subscriber_id) ON DELETE CASCADE
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
        # Migrations: add theme column to groups if missing
        try:
            await db.execute("ALTER TABLE groups ADD COLUMN theme TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # Column already exists
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


async def record_delivery(run_id: str, group_ids: list[str]) -> None:
    """Record which groups a newsletter was sent to."""
    if not group_ids:
        return
    db = await _connect()
    try:
        now = _now()
        for gid in group_ids:
            await db.execute(
                "INSERT OR IGNORE INTO run_deliveries (run_id, group_id, sent_at) VALUES (?, ?, ?)",
                (run_id, gid, now),
            )
        await db.commit()
    finally:
        await db.close()


async def list_newsletters_for_subscriber(email: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return newsletters delivered to groups that the subscriber (by email) belongs to."""
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT r.run_id, r.config, r.newsletter, r.created_at, r.finished_at "
            "FROM runs r "
            "INNER JOIN run_deliveries rd ON rd.run_id = r.run_id "
            "INNER JOIN subscriber_groups sg ON sg.group_id = rd.group_id "
            "INNER JOIN subscribers s ON s.subscriber_id = sg.subscriber_id "
            "WHERE s.email = ? AND r.status IN ('done', 'partial') AND r.newsletter IS NOT NULL "
            "GROUP BY r.run_id "
            "ORDER BY r.created_at DESC LIMIT ?",
            (email, limit),
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


async def get_subscriber_group_names(subscriber_id: str) -> list[str]:
    """Return group names a subscriber belongs to."""
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT g.name FROM groups g "
            "INNER JOIN subscriber_groups sg ON sg.group_id = g.group_id "
            "WHERE sg.subscriber_id = ? ORDER BY g.name",
            (subscriber_id,),
        )
        return [row["name"] for row in await cursor.fetchall()]
    finally:
        await db.close()


async def get_subscriber_with_groups_by_email(email: str) -> dict[str, Any] | None:
    """Return subscriber info with their group names and ids."""
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT subscriber_id, email, name FROM subscribers WHERE email = ?", (email,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        subscriber = dict(row)
        cursor = await db.execute(
            "SELECT g.group_id, g.name FROM groups g "
            "INNER JOIN subscriber_groups sg ON sg.group_id = g.group_id "
            "WHERE sg.subscriber_id = ? ORDER BY g.name",
            (subscriber["subscriber_id"],),
        )
        groups = [dict(r) for r in await cursor.fetchall()]
        subscriber["groups"] = groups
        return subscriber
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


async def get_subscriber_emails_by_groups(group_ids: list[str]) -> list[str]:
    """Return emails of subscribers belonging to any of the given groups."""
    if not group_ids:
        return []
    placeholders = ",".join("?" * len(group_ids))
    db = await _connect()
    try:
        cursor = await db.execute(
            f"SELECT DISTINCT s.email FROM subscribers s "
            f"JOIN subscriber_groups sg ON s.subscriber_id = sg.subscriber_id "
            f"WHERE sg.group_id IN ({placeholders})",
            group_ids,
        )
        rows = await cursor.fetchall()
        return [row["email"] for row in rows]
    finally:
        await db.close()


# --- groups ---


async def create_group(group_id: str, name: str, description: str = "", theme: str = "") -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO groups (group_id, name, description, theme, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (group_id, name, description, theme, _now()),
        )
        await db.commit()
    finally:
        await db.close()


async def list_groups() -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT g.group_id, g.name, g.description, g.theme, g.created_at, "
            "COUNT(sg.subscriber_id) AS subscriber_count "
            "FROM groups g "
            "LEFT JOIN subscriber_groups sg ON g.group_id = sg.group_id "
            "GROUP BY g.group_id ORDER BY g.created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def delete_group(group_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute("DELETE FROM groups WHERE group_id = ?", (group_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def add_subscriber_to_group(subscriber_id: str, group_id: str) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO subscriber_groups (subscriber_id, group_id) VALUES (?, ?)",
            (subscriber_id, group_id),
        )
        await db.commit()
    finally:
        await db.close()


async def remove_subscriber_from_group(subscriber_id: str, group_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute(
            "DELETE FROM subscriber_groups WHERE subscriber_id = ? AND group_id = ?",
            (subscriber_id, group_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def get_subscriber_groups(subscriber_id: str) -> list[dict[str, Any]]:
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT g.group_id, g.name FROM groups g "
            "JOIN subscriber_groups sg ON g.group_id = sg.group_id "
            "WHERE sg.subscriber_id = ? ORDER BY g.name",
            (subscriber_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def list_subscribers_with_groups() -> list[dict[str, Any]]:
    """List all subscribers with their group memberships."""
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT subscriber_id, email, name, created_at FROM subscribers ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        subscribers = [dict(row) for row in rows]
        # Batch fetch all group memberships
        cursor = await db.execute(
            "SELECT sg.subscriber_id, g.group_id, g.name "
            "FROM subscriber_groups sg JOIN groups g ON sg.group_id = g.group_id"
        )
        group_rows = await cursor.fetchall()
        groups_by_sub: dict[str, list[dict[str, str]]] = {}
        for row in group_rows:
            sid = row["subscriber_id"]
            groups_by_sub.setdefault(sid, []).append({
                "group_id": row["group_id"],
                "name": row["name"],
            })
        for sub in subscribers:
            sub["groups"] = groups_by_sub.get(sub["subscriber_id"], [])
        return subscribers
    finally:
        await db.close()


# --- questions & registration ---


async def create_question(question_id: str, text: str, position: int = 0) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO questions (question_id, text, position, created_at) VALUES (?, ?, ?, ?)",
            (question_id, text, position, _now()),
        )
        await db.commit()
    finally:
        await db.close()


async def delete_question(question_id: str) -> bool:
    db = await _connect()
    try:
        cursor = await db.execute("DELETE FROM questions WHERE question_id = ?", (question_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def create_option(option_id: str, question_id: str, text: str, group_name: str, position: int = 0) -> None:
    db = await _connect()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO question_options (option_id, question_id, text, group_name, position) "
            "VALUES (?, ?, ?, ?, ?)",
            (option_id, question_id, text, group_name, position),
        )
        await db.commit()
    finally:
        await db.close()


async def list_questions() -> list[dict[str, Any]]:
    """List all questions with their options."""
    db = await _connect()
    try:
        cursor = await db.execute(
            "SELECT question_id, text, position FROM questions ORDER BY position"
        )
        questions = [dict(row) for row in await cursor.fetchall()]
        for q in questions:
            cursor = await db.execute(
                "SELECT option_id, text, group_name, position FROM question_options "
                "WHERE question_id = ? ORDER BY position",
                (q["question_id"],),
            )
            q["options"] = [dict(row) for row in await cursor.fetchall()]
        return questions
    finally:
        await db.close()


async def register_subscriber(
    email: str,
    name: str,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Register a subscriber, store their answers, and assign to groups.

    answers: list of {"question_id": ..., "option_ids": [str, ...]}

    Returns {"subscriber_id": ..., "assigned_groups": [...]}
    """
    import uuid

    subscriber_id = uuid.uuid4().hex[:12]
    db = await _connect()
    try:
        # Create subscriber (or update if exists)
        existing = await db.execute(
            "SELECT subscriber_id FROM subscribers WHERE email = ?", (email,)
        )
        existing_row = await existing.fetchone()
        if existing_row:
            subscriber_id = existing_row["subscriber_id"]
            await db.execute(
                "UPDATE subscribers SET name = ? WHERE subscriber_id = ?",
                (name, subscriber_id),
            )
        else:
            await db.execute(
                "INSERT INTO subscribers (subscriber_id, email, name, created_at) VALUES (?, ?, ?, ?)",
                (subscriber_id, email, name, _now()),
            )

        # Clear old responses for this subscriber
        await db.execute(
            "DELETE FROM subscriber_responses WHERE subscriber_id = ?",
            (subscriber_id,),
        )

        # Store responses and collect group names
        group_votes: dict[str, int] = {}
        for ans in answers:
            qid = ans["question_id"]
            option_ids = ans.get("option_ids", [])
            if isinstance(option_ids, str):
                option_ids = [option_ids]
            for oid in option_ids:
                await db.execute(
                    "INSERT OR REPLACE INTO subscriber_responses (subscriber_id, question_id, option_id, answered_at) "
                    "VALUES (?, ?, ?, ?)",
                    (subscriber_id, qid, oid, _now()),
                )
                # Look up group_name for this option
                cursor = await db.execute(
                    "SELECT group_name FROM question_options WHERE option_id = ?", (oid,)
                )
                row = await cursor.fetchone()
                if row and row["group_name"]:
                    group_votes[row["group_name"]] = group_votes.get(row["group_name"], 0) + 1

        # Assign to groups: all groups that got at least 1 vote
        assigned_groups: list[str] = []
        for gname, votes in group_votes.items():
            if votes > 0:
                # Find or create group
                cursor = await db.execute(
                    "SELECT group_id FROM groups WHERE name = ?", (gname,)
                )
                row = await cursor.fetchone()
                if row:
                    gid = row["group_id"]
                else:
                    gid = uuid.uuid4().hex[:12]
                    await db.execute(
                        "INSERT INTO groups (group_id, name, description, created_at) VALUES (?, ?, ?, ?)",
                        (gid, gname, f"Auto-created from registration: {gname}", _now()),
                    )
                # Assign subscriber to group
                await db.execute(
                    "INSERT OR IGNORE INTO subscriber_groups (subscriber_id, group_id) VALUES (?, ?)",
                    (subscriber_id, gid),
                )
                assigned_groups.append(gname)

        await db.commit()
        return {"subscriber_id": subscriber_id, "assigned_groups": assigned_groups}
    finally:
        await db.close()
