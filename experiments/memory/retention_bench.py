"""P27: retention under utility/frequency signals, with an index-integrity check.

Builds a synthetic mixed memory, applies the retention policy, and measures:
  * how many forgettable records were removed (recall of the policy),
  * how many verified/trusted/user/used records were wrongly removed (safety),
  * stale FTS/fact rows after deletion (recovery/integrity),
  * whether kept facts remain retrievable.

    python -m experiments.memory.retention_bench
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from learning.ama import AMA
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index
from memory.retention import RetentionPolicy, apply, plan


def build(db: Database) -> dict[str, list[str]]:
    ep, fts, ids = EpisodicMemory(db), FTS5Index(db), {}
    now = time.time()
    for group, status, n in (("verified", "verified", 50), ("trusted", "trusted_material", 50),
                             ("user", "user_provided", 50), ("unverified", "unverified", 100)):
        ids[group] = []
        for i in range(n):
            e = Experience(f"{group} question {i}", f"{group} answer {i}",
                           verification_status=status, ts=now - 40 * 86400)
            ep.add(e)
            fts.add(e.id, e.text)
            ids[group].append(e.id)
    ids["retrieved"] = []
    for i in range(30):
        e = Experience(f"retrieved question {i}", f"retrieved answer {i}",
                       verification_status="unverified", ts=now - 40 * 86400)
        ep.add(e)
        fts.add(e.id, e.text)
        db.conn.execute("INSERT INTO memory_feedback(ts, exp_id, event, value, source, note) "
                        "VALUES (?,?,?,?,?,?)", (now - 86400, e.id, "retrieval_hit", 1.0, "test", ""))
        ids["retrieved"].append(e.id)
    ids["repeated"] = []
    for i in range(20):
        e = Experience(f"repeated question {i}", f"repeated answer {i}",
                       verification_status="unverified", ts=now - 40 * 86400, repeat_count=3)
        ep.add(e)
        fts.add(e.id, e.text)
        ids["repeated"].append(e.id)
    db.conn.commit()
    return ids


def main() -> None:
    db = Database()
    ids = build(db)
    policy = RetentionPolicy(max_age_days=30, protect_recent_days=7)
    planned = {exp_id for exp_id, _ in plan(db, policy)}
    forgotten = set(apply(db, policy))
    remaining = EpisodicMemory(db)
    out = {
        "planned": len(planned),
        "forgotten": len(forgotten),
        "unverified_forgotten": len(forgotten & set(ids["unverified"])) / len(ids["unverified"]),
        "unverified_over_forgotten": len(forgotten & (set(ids["verified"]) | set(ids["trusted"]) | set(ids["user"]))),
        "used_forgotten": len(forgotten & (set(ids["retrieved"]) | set(ids["repeated"]))),
        "verified_retained": sum(remaining.get(i) is not None for i in ids["verified"]) / len(ids["verified"]),
        "trusted_retained": sum(remaining.get(i) is not None for i in ids["trusted"]) / len(ids["trusted"]),
        "user_retained": sum(remaining.get(i) is not None for i in ids["user"]) / len(ids["user"]),
        "retrieved_retained": sum(remaining.get(i) is not None for i in ids["retrieved"]) / len(ids["retrieved"]),
        "repeated_retained": sum(remaining.get(i) is not None for i in ids["repeated"]) / len(ids["repeated"]),
        "integrity": remaining.reconcile_index(),
        "rows_left": remaining.count(),
    }
    # kept verified facts still retrieve, and a removed record is gone from search
    ama = AMA(db)
    kept = ama.retrieve("verified question 0", limit=3)
    out["kept_fact_retrievable"] = bool(kept) and "verified answer" in kept[0].experience.text
    out["removed_not_retrievable"] = not db.conn.execute(
        "SELECT 1 FROM fts_index WHERE memory_id = ?", (ids["unverified"][0],)).fetchone()
    ama.record_feedback(ids["verified"][0], "user_accepted")
    ama.record_feedback(ids["verified"][1], "user_rejected")
    out["utility_separate_from_truth"] = {
        "accepted": ama.utility_from_feedback(ids["verified"][0]),
        "rejected": ama.utility_from_feedback(ids["verified"][1]),
        "reliability_unchanged": remaining.get(ids["verified"][0]).reliability,
    }
    print(json.dumps(out, indent=2))
    Path("experiments/memory/results.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
