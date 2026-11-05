"""SQLite FTS5 implementation of MemoryIndex."""
from __future__ import annotations

import re

from .database import Database
from .index import MemoryIndex

_TOKEN = re.compile(r"\w+", re.UNICODE)


def to_match_query(query: str) -> str:
    """Turn free text into a safe FTS5 query (quoted tokens OR-ed). Avoids FTS syntax errors."""
    tokens = _TOKEN.findall(query.lower())
    return " OR ".join(f'"{t}"' for t in tokens)


class FTS5Index(MemoryIndex):
    def __init__(self, db: Database):
        self.db = db

    def add(self, memory_id: str, text: str, commit: bool = True) -> None:
        self.delete(memory_id, commit=False)  # idempotent update
        self.db.conn.execute("INSERT INTO fts_index(memory_id, text) VALUES (?, ?)", (memory_id, text))
        if commit:
            self.db.conn.commit()

    def search(self, query: str, limit: int = 5) -> list[tuple[str, float]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        q = to_match_query(query)
        if not q:
            return []
        rows = self.db.conn.execute(
            "SELECT memory_id, bm25(fts_index) AS r FROM fts_index WHERE fts_index MATCH ? ORDER BY r LIMIT ?",
            (q, limit),
        ).fetchall()
        # bm25() is lower = better (negative); expose higher = better.
        return [(r["memory_id"], -r["r"]) for r in rows]

    def delete(self, memory_id: str, commit: bool = True) -> None:
        self.db.conn.execute("DELETE FROM fts_index WHERE memory_id = ?", (memory_id,))
        if commit:
            self.db.conn.commit()

    def count(self) -> int:
        return self.db.conn.execute("SELECT COUNT(*) FROM fts_index").fetchone()[0]
