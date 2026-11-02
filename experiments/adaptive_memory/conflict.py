"""EXP-005: same-key conflicting updates (closes F-009).   python -m experiments.adaptive_memory.conflict

Question: a fact is learned, then the SAME question gets a different answer. What does each memory return?
  * adaptive memory (linear associative, NumPy): by construction an overwrite - it has no notion of reliability
  * AMA + FTS5: stronger evidence supersedes (old de-indexed, kept as history); weaker evidence is stored but
    not searchable, so the reliable answer stays on top

LIMITATION: synthetic, author-written, 3 seeds. It tests the mechanism, not real usage.
"""
from __future__ import annotations

import json
import random
import statistics

from experiments.adaptive_memory.run import codebook, make_task
from learning.ama import AMA
from memory.adaptive_memory import AdaptiveMemory, AMemConfig
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index

N, N_UPDATED = 100, 40


def adaptive(seed: int, lr: float, passes: int) -> dict:
    rng = random.Random(seed)
    facts = make_task(rng, "A", N)
    cb = codebook(rng, facts, "A")
    new_vals = {}
    for i in range(N_UPDATED):
        v = str(rng.randint(1000, 9999))
        while v == facts[i][2] or v in {f[2] for f in facts}:
            v = str(rng.randint(1000, 9999))
        new_vals[i] = v
    cb = sorted(set(cb) | set(new_vals.values()))
    mem = AdaptiveMemory(AMemConfig(lr=lr)); V = mem.candidate_matrix(cb)
    for q, _, p in facts:
        mem.write(q, p)
    for i, v in new_vals.items():                       # conflicting update, same key
        mem.write(facts[i][0], v, passes)
    got_new = sum(mem.recall(facts[i][0], cb, V)[0] == v for i, v in new_vals.items()) / N_UPDATED
    got_old = sum(mem.recall(facts[i][0], cb, V)[0] == facts[i][2] for i in new_vals) / N_UPDATED
    untouched = sum(mem.recall(facts[i][0], cb, V)[0] == facts[i][2] for i in range(N_UPDATED, N)) / (N - N_UPDATED)
    return {"returns_new": got_new, "returns_old": got_old, "untouched_still_correct": untouched}


def ama_fts(seed: int, new_status: str, old_status: str = "trusted_material") -> dict:
    # Old facts are trusted_material (0.8) so that user_corrected (0.9) is genuinely stronger and unverified (0.2)
    # genuinely weaker. (A user_corrected answer does NOT override a `verified` 1.0 fact; it is flagged for review.)
    rng = random.Random(seed)
    facts = make_task(rng, "A", N)
    db = Database(); ama = AMA(db); fts = FTS5Index(db); ep = EpisodicMemory(db)
    for q, _, p in facts:
        ama.admit(Experience(q, f"code is {p}", verification_status=old_status))
    new_vals = {}
    for i in range(N_UPDATED):
        v = str(rng.randint(1000, 9999))
        while v == facts[i][2] or v in {f[2] for f in facts}:
            v = str(rng.randint(1000, 9999))
        new_vals[i] = v
        ama.admit(Experience(facts[i][0], f"code is {v}", verification_status=new_status))
    def top(q):
        h = fts.search(q, limit=1)
        return ep.get(h[0][0]).output if h else ""
    return {"returns_new": sum(f"code is {v}" == top(facts[i][0]) for i, v in new_vals.items()) / N_UPDATED,
            "returns_old": sum(f"code is {facts[i][2]}" == top(facts[i][0]) for i in new_vals) / N_UPDATED,
            "history_rows_kept": ep.count() / (N + N_UPDATED)}


def mean(rows):
    return {k: round(statistics.mean(r[k] for r in rows), 3) for k in rows[0]}


if __name__ == "__main__":
    seeds, out = [1, 2, 3], {}
    print("adaptive memory, 40 of 100 keys receive a conflicting new value (single write unless noted)")
    for lr in (0.3, 0.6, 1.0):
        for passes in (1, 3):
            r = mean([adaptive(s, lr, passes) for s in seeds]); out[f"adaptive lr={lr} passes={passes}"] = r
            print(f"  lr={lr} passes={passes}: {r}")
    for status, label in (("user_corrected", "stronger evidence (user_corrected)"), ("unverified", "weaker evidence (unverified)")):
        r = mean([ama_fts(s, status) for s in seeds]); out[f"AMA+FTS5 {status}"] = r
        print(f"AMA+FTS5, {label}: {r}")
    json.dump(out, open("experiments/adaptive_memory/conflict_results.json", "w"), indent=2)
