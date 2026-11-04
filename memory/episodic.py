"""Episodic memory: what happened."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field

from .database import Database
from .text import normalize  # noqa: F401  (re-exported: other modules import it from here)

RELIABILITY_BY_STATUS = {
    "verified": 1.0,          # exact arithmetic, passing tests, deterministic outcomes
    "user_corrected": 0.9,
    "trusted_material": 0.8,
    "unverified": 0.2,        # model-generated and nothing else
}


def content_hash(inp: str, out: str) -> str:
    return hashlib.sha1(f"{normalize(inp)}\x1f{normalize(out)}".encode()).hexdigest()


@dataclass
class Experience:
    input: str
    output: str
    task_category: str = "general"
    source: str = "interaction"
    verification_status: str = "unverified"
    outcome: str = "unknown"
    reliability: float | None = None
    related_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)
    repeat_count: int = 1

    def __post_init__(self):
        if self.verification_status not in RELIABILITY_BY_STATUS:
            raise ValueError(f"unknown verification_status {self.verification_status!r}")
        if self.reliability is None:
            self.reliability = RELIABILITY_BY_STATUS[self.verification_status]

    @property
    def text(self) -> str:
        return f"{self.input}\n{self.output}"


class EpisodicMemory:
    def __init__(self, db: Database):
        self.db = db

    def add(self, e: Experience) -> str:
        self.db.conn.execute(
            """INSERT INTO experiences(id, ts, input, output, task_category, source, verification_status,
               reliability, outcome, content_hash, repeat_count, related_ids, input_norm)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e.id, e.ts, e.input, e.output, e.task_category, e.source, e.verification_status,
             e.reliability, e.outcome, content_hash(e.input, e.output), e.repeat_count, json.dumps(e.related_ids),
             normalize(e.input)),
        )
        self.db.conn.commit()
        return e.id

    def get(self, exp_id: str) -> Experience | None:
        r = self.db.conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()
        return self._row(r) if r else None

    def find_by_hash(self, h: str) -> Experience | None:
        r = self.db.conn.execute("SELECT * FROM experiences WHERE content_hash = ? LIMIT 1", (h,)).fetchone()
        return self._row(r) if r else None

    def find_by_input(self, inp: str, category: str | None = None) -> list[Experience]:
        """Exact (normalised) input matches - used for conflict detection. Uses the indexed input_norm column."""
        rows = self.db.conn.execute(
            "SELECT * FROM experiences WHERE input_norm = ? AND task_category = COALESCE(?, task_category)",
            (normalize(inp), category)).fetchall()
        return [self._row(r) for r in rows]

    def bump_repeat(self, exp_id: str, new_status: str | None = None) -> None:
        self.db.conn.execute("UPDATE experiences SET repeat_count = repeat_count + 1 WHERE id = ?", (exp_id,))
        if new_status and RELIABILITY_BY_STATUS.get(new_status, 0) > 0:
            self.db.conn.execute(
                "UPDATE experiences SET verification_status = ?, reliability = MAX(reliability, ?) WHERE id = ?",
                (new_status, RELIABILITY_BY_STATUS[new_status], exp_id))
        self.db.conn.commit()

    def filter(self, category: str | None = None, status: str | None = None, limit: int = 100) -> list[Experience]:
        rows = self.db.conn.execute(
            """SELECT * FROM experiences WHERE task_category = COALESCE(?, task_category)
               AND verification_status = COALESCE(?, verification_status) ORDER BY ts DESC LIMIT ?""",
            (category, status, limit)).fetchall()
        return [self._row(r) for r in rows]

    def delete(self, exp_id: str) -> bool:
        """Delete one experience and everything derived from it, atomically.

        Removes: the row, its FTS5 entry and derived semantic facts (database triggers), its
        dream_queue entry (FK cascade), and its id from other records' ``related_ids``.
        The admission_log is an audit trail and is intentionally kept. Returns False if absent.
        """
        c = self.db.conn
        try:
            c.execute("BEGIN IMMEDIATE") if not c.in_transaction else None
            if c.execute("SELECT 1 FROM experiences WHERE id = ?", (exp_id,)).fetchone() is None:
                c.rollback()
                return False
            for r in c.execute("SELECT id, related_ids FROM experiences WHERE related_ids LIKE ?",
                               (f"%{exp_id}%",)).fetchall():
                kept = [i for i in json.loads(r["related_ids"]) if i != exp_id]
                c.execute("UPDATE experiences SET related_ids = ? WHERE id = ?", (json.dumps(kept), r["id"]))
            c.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
            c.commit()
            return True
        except Exception:
            c.rollback()
            raise

    def reconcile_index(self) -> dict:
        """Repair stale state left by databases written before the deletion fix.

        Drops FTS5 entries and facts whose source experience no longer exists. Only call this on
        a database where every FTS entry is meant to belong to an experience (true for ASHURA's
        own memory; not for ad-hoc FTS5Index use with free-form ids).
        """
        c = self.db.conn
        fts = c.execute("DELETE FROM fts_index WHERE memory_id NOT IN (SELECT id FROM experiences)").rowcount
        facts = c.execute("DELETE FROM facts WHERE source_exp_id IS NULL").rowcount
        c.commit()
        return {"stale_fts_removed": fts, "orphan_facts_removed": facts}

    def count(self) -> int:
        return self.db.conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]

    @staticmethod
    def _row(r) -> Experience:
        return Experience(
            id=r["id"], ts=r["ts"], input=r["input"], output=r["output"], task_category=r["task_category"],
            source=r["source"], verification_status=r["verification_status"], reliability=r["reliability"],
            outcome=r["outcome"], related_ids=json.loads(r["related_ids"]), repeat_count=r["repeat_count"])
