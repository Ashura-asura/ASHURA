"""Durable job records for the background learning worker (F-045).

The store is a local SQLite file. It persists the correction/trace payload, status transitions and
the job result so a crash or restart does not silently lose a queued job. Recovery is deliberately
conservative:

* queued jobs are re-scheduled;
* running jobs are marked ``error`` with an "interrupted" reason, because a half-finished learning
  job may already have written a candidate or a checkpoint and must not be replayed blindly.

Payloads are pickled. The database is a trusted local file (the same trust boundary as the
checkpoint store); do not point it at untrusted input.
"""
from __future__ import annotations

import os
import pickle
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

TERMINAL = frozenset({"done", "error", "cancelled", "timeout"})
_SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    submitted REAL NOT NULL,
    started REAL,
    finished REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    payload BLOB,
    result BLOB,
    error TEXT,
    pid INTEGER
);
CREATE INDEX IF NOT EXISTS idx_learning_jobs_status ON learning_jobs(status, submitted);
"""


def _dump(value: Any) -> bytes | None:
    if value is None:
        return None
    return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)


def _load(blob: bytes | None) -> Any:
    if blob is None:
        return None
    try:
        return pickle.loads(blob)
    except Exception as e:  # noqa: BLE001 - an unreadable audit record must not crash the worker
        return f"<unreadable result: {type(e).__name__}: {e}>"


class SQLiteJobStore:
    """Thread-safe, crash-persistent job store for :class:`learning.worker.LearningWorker`."""

    def __init__(self, path: str = "data/learning_jobs.db", busy_timeout_ms: int = 5000):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        try:
            self.conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            if path != ":memory:":
                self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.executescript(_SCHEMA)
            self.conn.commit()
        except Exception:
            self.conn.close()
            raise

    # ---- writes -----------------------------------------------------------------------------
    def create(self, job_id: str, correction: Any, trace: Any, submitted: float | None = None) -> None:
        payload = _dump((correction, trace))
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO learning_jobs (id, status, submitted, payload) VALUES (?, 'queued', ?, ?)",
                (job_id, time.time() if submitted is None else submitted, payload),
            )

    def mark_running(self, job_id: str, pid: int | None = None) -> bool:
        """Atomically claim a queued job. Returns False if it was cancelled or claimed elsewhere."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                """UPDATE learning_jobs
                   SET status = 'running', started = ?, attempts = attempts + 1, pid = ?
                   WHERE id = ? AND status = 'queued'""",
                (time.time(), os.getpid() if pid is None else pid, job_id),
            )
            return cur.rowcount == 1

    def mark_done(self, job_id: str, result: Any) -> bool:
        return self._finish(job_id, "done", result=result)

    def mark_error(self, job_id: str, error: str) -> bool:
        return self._finish(job_id, "error", error=error)

    def mark_timeout(self, job_id: str, error: str = "job exceeded its hard timeout") -> bool:
        return self._finish(job_id, "timeout", error=error)

    def mark_cancelled(self, job_id: str, reason: str = "cancelled before it started") -> bool:
        with self._lock, self.conn:
            cur = self.conn.execute(
                """UPDATE learning_jobs SET status = 'cancelled', finished = ?, error = ?
                   WHERE id = ? AND status = 'queued'""",
                (time.time(), reason, job_id),
            )
            return cur.rowcount == 1

    def _finish(self, job_id: str, status: str, *, result: Any = None, error: str | None = None) -> bool:
        with self._lock, self.conn:
            cur = self.conn.execute(
                """UPDATE learning_jobs SET status = ?, finished = ?, result = ?, error = ?
                   WHERE id = ? AND status = 'running'""",
                (status, time.time(), _dump(result), error, job_id),
            )
            return cur.rowcount == 1

    def recover_running(self, reason: str = "interrupted by process restart") -> list[str]:
        """Mark previously running jobs as interrupted and return their ids."""
        with self._lock, self.conn:
            rows = self.conn.execute(
                "SELECT id FROM learning_jobs WHERE status = 'running' ORDER BY submitted"
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                self.conn.executemany(
                    """UPDATE learning_jobs SET status = 'error', finished = ?, error = ?
                       WHERE id = ? AND status = 'running'""",
                    [(time.time(), reason, job_id) for job_id in ids],
                )
            return ids

    # ---- reads ------------------------------------------------------------------------------
    def get(self, job_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM learning_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._as_dict(row) if row else None

    def payload(self, job_id: str) -> tuple[Any, Any] | None:
        with self._lock:
            row = self.conn.execute("SELECT payload FROM learning_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["payload"] is None:
            return None
        value = _load(row["payload"])
        return value if isinstance(value, tuple) and len(value) == 2 else None

    def queued_ids(self, exclude: Iterable[str] = (), limit: int | None = None) -> list[str]:
        excluded = set(exclude)
        with self._lock:
            rows = self.conn.execute(
                "SELECT id FROM learning_jobs WHERE status = 'queued' ORDER BY submitted"
            ).fetchall()
        ids = [row["id"] for row in rows if row["id"] not in excluded]
        return ids[:limit] if limit is not None else ids

    def has_queued(self) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM learning_jobs WHERE status = 'queued' LIMIT 1"
            ).fetchone()
        return row is not None

    def active(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM learning_jobs WHERE status IN ('queued', 'running')"
            ).fetchone()
        return int(row["n"])

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT status, COUNT(*) AS n FROM learning_jobs GROUP BY status"
            ).fetchall()
        return {row["status"]: int(row["n"]) for row in rows}

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _as_dict(self, row: sqlite3.Row) -> dict:
        return {
            "job_id": row["id"],
            "status": row["status"],
            "submitted": row["submitted"],
            "started": row["started"],
            "finished": row["finished"],
            "attempts": row["attempts"],
            "result": _load(row["result"]),
            "error": row["error"],
            "pid": row["pid"],
        }
