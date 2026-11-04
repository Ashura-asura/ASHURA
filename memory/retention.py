"""Forgetting policy (spec Phase 1: "store, retrieve, update and forget appropriately selected experiences").

Deliberately conservative. A record is only a forgetting *candidate* if ALL hold:
  * it is unverified (model-generated, nothing confirmed it) - verified / corrected / trusted items are never forgotten;
  * it was never reinforced (repeat_count == 1);
  * it is older than `max_age_days`;
  * it is not conflict evidence (no related_ids, and no other record points at it) - history is kept (D-005);
  * it is not waiting in the dream_queue.
An optional row cap forgets the oldest candidates first; it never touches non-candidates, so the cap can be
exceeded rather than destroy reliable data. Deletion goes through EpisodicMemory.delete (index + facts cleaned),
and every forgotten record is written to admission_log as FORGOTTEN with its reason (audit trail).

    python -m memory.retention --db data/ashura.db            # dry run: show what would be forgotten
    python -m memory.retention --db data/ashura.db --apply
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass

from .database import Database
from .episodic import EpisodicMemory


@dataclass
class RetentionPolicy:
    max_age_days: float = 30.0
    max_rows: int = 0            # 0 = no cap
    protect_recent_days: float = 7.0   # recently retrieved/used records are not forgotten

    @classmethod
    def from_dict(cls, d: dict) -> "RetentionPolicy":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def plan(db: Database, policy: RetentionPolicy | None = None, now: float | None = None) -> list[tuple[str, str]]:
    """[(exp_id, reason)] that the policy would forget, oldest first. Changes nothing."""
    pol, now = policy or RetentionPolicy(), now if now is not None else time.time()
    c = db.conn
    referenced: set[str] = set()
    for r in c.execute("SELECT related_ids FROM experiences WHERE related_ids != '[]'"):
        referenced.update(json.loads(r["related_ids"]))
    queued = {r[0] for r in c.execute("SELECT exp_id FROM dream_queue")}
    # Retrieval frequency is a utility signal (P18/P27). A record used recently is protected even
    # if it is old, instead of deleting the very thing that is working.
    recent = {r["exp_id"] for r in c.execute(
        """SELECT DISTINCT exp_id FROM memory_feedback
           WHERE ts >= ? AND event IN ('retrieval_hit', 'user_accepted', 'task_completed')""",
        (now - pol.protect_recent_days * 86400,))}
    candidates = [
        r for r in c.execute(
            """SELECT id, ts, related_ids FROM experiences
               WHERE verification_status = 'unverified' AND repeat_count = 1 ORDER BY ts ASC""")
        if r["related_ids"] == "[]" and r["id"] not in referenced
        and r["id"] not in queued and r["id"] not in recent
    ]
    out: list[tuple[str, str]] = []
    cutoff = now - pol.max_age_days * 86400
    for r in candidates:
        if r["ts"] < cutoff:
            out.append((r["id"], f"unverified, never reinforced, older than {pol.max_age_days:g} days"))
    if pol.max_rows:
        total = c.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
        chosen = {i for i, _ in out}
        excess = total - len(out) - pol.max_rows
        for r in candidates:                      # oldest first
            if excess <= 0:
                break
            if r["id"] not in chosen:
                out.append((r["id"], f"over row cap {pol.max_rows}: oldest unreinforced unverified record")); excess -= 1
    return out


def apply(db: Database, policy: RetentionPolicy | None = None, now: float | None = None) -> list[str]:
    """Forget what plan() selects. Returns the ids removed."""
    mem, forgotten = EpisodicMemory(db), []
    for exp_id, reason in plan(db, policy, now):
        if mem.delete(exp_id):
            db.conn.execute("INSERT INTO admission_log(ts, exp_id, decision, score, features, reason) VALUES (?,?,?,?,?,?)",
                            (time.time(), exp_id, "FORGOTTEN", None, "{}", reason))
            forgotten.append(exp_id)
    db.conn.commit()
    return forgotten


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ashura.db")
    ap.add_argument("--config", default="config/ashura.toml", help="read [retention] defaults from this file")
    ap.add_argument("--max-age-days", type=float, default=None)
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    base = RetentionPolicy()
    try:                                   # the [retention] section existed in the config but was never read
        import tomllib
        with open(a.config, "rb") as f:
            base = RetentionPolicy.from_dict(tomllib.load(f).get("retention", {}))
    except FileNotFoundError:
        pass
    pol = RetentionPolicy(base.max_age_days if a.max_age_days is None else a.max_age_days,
                          base.max_rows if a.max_rows is None else a.max_rows)
    db = Database(a.db)
    p = plan(db, pol)
    print(f"{len(p)} record(s) would be forgotten" + ("" if a.apply else " (dry run; pass --apply to delete)"))
    for i, why in p[:20]:
        print(f"  {i[:8]}  {why}")
    if a.apply:
        print(f"forgot {len(apply(db, pol))} record(s)")


if __name__ == "__main__":
    main()
