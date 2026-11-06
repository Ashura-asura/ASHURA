"""Persistent chat sessions for the local web UI.

The UI keeps conversation history in its own SQLite file so the operator can reopen a chat after a
restart without touching the episodic-memory database. Connections are opened per operation; the
web worker and HTTP threads therefore never share a connection.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sessions (
    id      TEXT PRIMARY KEY,
    title   TEXT NOT NULL,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    meta       TEXT NOT NULL DEFAULT '{}',
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated);
"""


class SessionStore:
    def __init__(self, path: str = "data/ui_sessions.db"):
        self.path = str(path)
        self._memory = self.path == ":memory:"
        self._memory_conn = None
        self._lock = threading.RLock()
        if self._memory:
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            if not self._memory:
                conn.execute("PRAGMA journal_mode = WAL")

    @contextmanager
    def _connect(self):
        if self._memory:
            with self._lock:
                conn = self._memory_conn
                if conn is None:
                    raise RuntimeError("session store is closed")
                try:
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA busy_timeout = 5000")
                    yield conn
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
            return
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        with self._lock:
            if self._memory_conn is not None:
                self._memory_conn.close()
                self._memory_conn = None

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row is not None else None

    def create(self, title: str = "New chat") -> dict:
        now = time.time()
        session_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute("INSERT INTO sessions(id, title, created, updated) VALUES (?,?,?,?)",
                         (session_id, title.strip() or "New chat", now, now))
        return self.get(session_id)

    def get(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._dict(row)

    def list(self, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT s.*, COUNT(m.id) AS message_count
                   FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
                   GROUP BY s.id ORDER BY s.updated DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def messages(self, session_id: str, limit: int | None = 200,
                 before: int | None = None) -> list[dict]:
        """Return messages in ascending order.

        ``limit=None`` returns the whole transcript. Otherwise the newest
        ``limit`` messages are returned, or the newest messages older than the
        ``before`` message id when it is supplied.
        """
        with self._connect() as conn:
            if limit is None:
                rows = conn.execute(
                    """SELECT id, role, content, meta, ts FROM messages
                       WHERE session_id = ? ORDER BY id""", (session_id,)).fetchall()
            else:
                limit = max(1, min(int(limit), 1000))
                if before is None:
                    rows = list(reversed(conn.execute(
                        """SELECT id, role, content, meta, ts FROM messages
                           WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                        (session_id, limit)).fetchall()))
                else:
                    rows = list(reversed(conn.execute(
                        """SELECT id, role, content, meta, ts FROM messages
                           WHERE session_id = ? AND id < ?
                           ORDER BY id DESC LIMIT ?""",
                        (session_id, int(before), limit)).fetchall()))
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["meta"] = json.loads(item["meta"] or "{}")
            except json.JSONDecodeError:
                item["meta"] = {}
            out.append(item)
        return out

    def count_messages(self, session_id: str) -> int:
        with self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,)).fetchone()[0])

    def has_older(self, session_id: str, before_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? AND id < ? LIMIT 1",
                (session_id, int(before_id))).fetchone()
        return row is not None

    def append(self, session_id: str, role: str, content: str, meta: dict | None = None) -> dict:
        now = time.time()
        with self._connect() as conn:
            session = conn.execute("SELECT title FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                raise ValueError(f"unknown session {session_id!r}")
            cursor = conn.execute(
                "INSERT INTO messages(session_id, role, content, meta, ts) VALUES (?,?,?,?,?)",
                (session_id, role, content, json.dumps(meta or {}, default=str), now))
            title = session["title"]
            if role == "user" and (not title or title == "New chat"):
                title = " ".join(content.split())[:60] or "New chat"
            conn.execute("UPDATE sessions SET updated = ?, title = ? WHERE id = ?",
                         (now, title, session_id))
            message_id = cursor.lastrowid
        return {"id": message_id, "session_id": session_id, "role": role, "content": content,
                "meta": meta or {}, "ts": now}

    def history(self, session_id: str, limit: int = 8) -> list[tuple[str, str]]:
        """Return recent completed (user, assistant) pairs for the language prompt."""
        messages = self.messages(session_id, limit=max(2, limit * 2 + 2))
        pairs: list[tuple[str, str]] = []
        pending: str | None = None
        for message in messages:
            if message["role"] == "user":
                pending = message["content"]
            elif message["role"] == "assistant" and pending is not None:
                pairs.append((pending, message["content"]))
                pending = None
        return pairs[-limit:]

    def rename(self, session_id: str, title: str) -> dict | None:
        title = " ".join((title or "").split())[:80]
        if not title:
            raise ValueError("title must not be empty")
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET title = ?, updated = ? WHERE id = ?",
                         (title, time.time(), session_id))
        return self.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
