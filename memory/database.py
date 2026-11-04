"""Embedded SQLite connection. No external database service."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .text import normalize

SCHEMA = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: str = ":memory:", busy_timeout_ms: int = 5000):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        try:
            # Wait for a competing writer instead of failing immediately with "database is locked".
            self.conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            if path != ":memory:":
                self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.executescript(SCHEMA.read_text())
            self._migrate()
            self.conn.commit()
        except Exception:
            self.conn.close()
            raise

    def _migrate(self) -> None:
        """Bring databases written by older versions up to date (idempotent)."""
        c = self.conn
        cols = {r["name"] for r in c.execute("PRAGMA table_info(experiences)")}
        if "input_norm" not in cols:
            c.execute("ALTER TABLE experiences ADD COLUMN input_norm TEXT NOT NULL DEFAULT ''")
        c.execute("CREATE INDEX IF NOT EXISTS idx_exp_input_norm ON experiences(input_norm, task_category)")
        cols = {r["name"] for r in c.execute("PRAGMA table_info(experiences)")}
        if "verification_method" not in cols:
            c.execute("ALTER TABLE experiences ADD COLUMN verification_method TEXT NOT NULL DEFAULT ''")
            c.execute("""UPDATE experiences SET verification_method = CASE verification_status
                WHEN 'verified' THEN 'independent verification'
                WHEN 'trusted_material' THEN 'declared trusted source; not independently verified'
                WHEN 'user_provided' THEN 'user assertion; factual truth not independently verified'
                WHEN 'user_corrected' THEN 'user correction; factual truth not independently verified'
                ELSE 'none' END
                WHERE verification_method = ''""")
        stale = c.execute("SELECT id, input FROM experiences WHERE input_norm = ''").fetchall()
        if stale:
            c.executemany("UPDATE experiences SET input_norm = ? WHERE id = ?",
                          [(normalize(r["input"]), r["id"]) for r in stale])

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
