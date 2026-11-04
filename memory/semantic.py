"""Semantic memory: verified information only.

A reliability number or a status string is not verification evidence by itself (P29). A fact must
name the verified source experience it came from, and the provenance/derivation are stored with it.
"""
from __future__ import annotations

import json
import time
import uuid

from .database import Database


class SemanticMemory:
    def __init__(self, db: Database):
        self.db = db

    def add_fact(self, text: str, source_exp_id: str, reliability: float,
                 derivation: str = "", commit: bool = True) -> str:
        """Store a fact only when its source episode is independently verified.

        Raises ValueError when the source is missing or not verified. Keeping the derivation with
        the fact means a later reviewer can inspect why it was admitted.
        """
        if not source_exp_id:
            raise ValueError("a semantic fact requires a source experience")
        row = self.db.conn.execute(
            """SELECT input, output, verification_status, verification_method, reliability
               FROM experiences WHERE id = ?""", (source_exp_id,)).fetchone()
        if row is None:
            raise ValueError(f"source experience {source_exp_id!r} does not exist")
        if row["verification_status"] != "verified":
            raise ValueError(
                f"source experience is {row['verification_status']!r}, not independently verified")
        if reliability < row["reliability"]:
            raise ValueError("fact reliability cannot be lower than its verified source")
        provenance = {
            "source_exp_id": source_exp_id,
            "verification": row["verification_status"],
            "verification_method": row["verification_method"],
            "derivation": derivation or f"fact extracted from verified experience {source_exp_id}",
            "admitted_ts": time.time(),
        }
        fid = uuid.uuid4().hex
        # The source episode already stores the same text. Keep a copy only when the fact is a
        # genuine derivation that differs from it (P17: no blind payload duplication).
        stored_text = "" if text.strip() == f"{row['input']}\n{row['output']}".strip() else text
        self.db.conn.execute(
            """INSERT INTO facts(id, text, source_exp_id, reliability, verification_method,
               provenance, derivation, ts) VALUES (?,?,?,?,?,?,?,?)""",
            (fid, stored_text, source_exp_id, reliability, row["verification_method"],
             json.dumps(provenance), provenance["derivation"], time.time()))
        if commit:
            self.db.conn.commit()
        return fid

    def get(self, fact_id: str) -> dict | None:
        r = self.db.conn.execute(
            """SELECT f.*, e.input AS source_input, e.output AS source_output
               FROM facts f LEFT JOIN experiences e ON e.id = f.source_exp_id
               WHERE f.id = ?""", (fact_id,)).fetchone()
        if not r:
            return None
        out = {**dict(r), "provenance": json.loads(r["provenance"])}
        if not out["text"] and out["source_input"] is not None:
            out["text"] = f"{out['source_input']}\n{out['source_output']}"
        return out

    def count(self) -> int:
        return self.db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
