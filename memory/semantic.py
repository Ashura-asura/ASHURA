"""Semantic memory: reliable information only. Unverified generated claims never enter here."""
from __future__ import annotations

import time
import uuid

from .database import Database


class SemanticMemory:
    def __init__(self, db: Database):
        self.db = db

    def add_fact(self, text: str, source_exp_id: str | None, reliability: float) -> str:
        fid = uuid.uuid4().hex
        self.db.conn.execute("INSERT INTO facts(id, text, source_exp_id, reliability, ts) VALUES (?,?,?,?,?)",
                             (fid, text, source_exp_id, reliability, time.time()))
        self.db.conn.commit()
        return fid

    def count(self) -> int:
        return self.db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
