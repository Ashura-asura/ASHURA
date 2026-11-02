"""EXP-001: AMA vs store-everything on a synthetic stream.   python -m experiments.ama.run

LIMITATION: the stream is synthetic and written by the same author as AMA. A good result here
shows the mechanism works on this kind of data; it is NOT evidence about real usage.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import tempfile
import time

from learning.ama import AMA, AMAConfig, StoreEverything
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index

VOCAB = ("project access code what is the please tell me about random thing ok sure here you go weather today "
         "meeting notes remind later thanks great hello again maybe lunch music movie coffee travel plan idea").split()


def make_stream(seed: int, n_facts=200, n_noise=600):
    rng = random.Random(seed)
    items, truth = [], {}
    for i in range(n_facts):
        q = f"what is the access code for project P{i}"
        code, wrong = rng.randint(1000, 9999), rng.randint(1000, 9999)
        while wrong == code:
            wrong = rng.randint(1000, 9999)
        truth[q] = (str(code), str(wrong))
        items.append(("fact", Experience(q, f"The access code for project P{i} is {code}", verification_status="verified")))
        for _ in range(rng.randint(0, 3)):    # exact repeats with formatting noise
            items.append(("repeat", Experience(q.upper() + " ", f"the access code for project p{i} is {code}.", verification_status="verified")))
        if rng.random() < 0.2:                # reworded restatement (same truth)
            items.append(("reword", Experience(q, f"code is {code}", verification_status="verified")))
        if rng.random() < 0.3:                # contradicting, unverified model claim
            items.append(("wrong", Experience(q, f"The access code for project P{i} is {wrong}", verification_status="unverified")))
    for _ in range(n_noise):
        items.append(("noise", Experience(" ".join(rng.choices(VOCAB, k=6)), " ".join(rng.choices(VOCAB, k=8)))))
    rng.shuffle(items)
    return items, truth


def evaluate(db: Database, truth: dict) -> dict:
    fts, ep = FTS5Index(db), EpisodicMemory(db)
    hit3 = acc1 = false_top1 = 0
    lat = []
    for q, (code, wrong) in truth.items():
        s = time.perf_counter()
        hits = fts.search(q, limit=3)
        lat.append((time.perf_counter() - s) * 1000)
        texts = [ep.get(h).output for h, _ in hits if ep.get(h)]
        hit3 += any(code in t for t in texts)
        if texts:
            acc1 += code in texts[0]
            false_top1 += (wrong in texts[0]) and (code not in texts[0])
    n = len(truth)
    return {"hit@3": hit3 / n, "acc@1": acc1 / n, "false_memory_top1": false_top1 / n,
            "retrieval_ms_mean": statistics.mean(lat), "retrieval_ms_p95": sorted(lat)[int(0.95 * (n - 1))]}


def run_one(seed: int, system: str, cfg: AMAConfig | None = None) -> dict:
    items, truth = make_stream(seed)
    path = os.path.join(tempfile.mkdtemp(), "exp.db")
    db = Database(path)
    sys_ = StoreEverything(db) if system == "baseline" else AMA(db, cfg)
    counts = {}
    t0 = time.perf_counter()
    for kind, x in items:
        d = sys_.admit(x)
        counts.setdefault(kind, {}).setdefault(d.decision, 0)
        counts[kind][d.decision] += 1
    admit_ms = (time.perf_counter() - t0) * 1000 / len(items)
    db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    out = {"stream_items": len(items), "episodic_rows": EpisodicMemory(db).count(), "fts_rows": FTS5Index(db).count(),
           "db_kb": os.path.getsize(path) / 1024, "admit_ms_per_item": admit_ms, **evaluate(db, truth)}
    n_noise = counts.get("noise", {})
    out["noise_kept_frac"] = (n_noise.get("ADMITTED", 0)) / max(1, sum(n_noise.values())) if system != "baseline" else 1.0
    nr = counts.get("reword", {})
    out["false_review_rate_rewords"] = nr.get("REVIEW_REQUIRED", 0) / max(1, sum(nr.values())) if system != "baseline" else 0.0
    wr = counts.get("wrong", {})
    out["wrong_claims_blocked_from_index"] = (wr.get("REVIEW_REQUIRED", 0) + wr.get("DISCARDED", 0)) / max(1, sum(wr.values())) if system != "baseline" else 0.0
    db.close()
    return out


def mean(rows: list[dict]) -> dict:
    return {k: round(statistics.mean(r[k] for r in rows), 4) for k in rows[0]}


if __name__ == "__main__":
    seeds = [1, 2, 3]
    results = {"baseline": mean([run_one(s, "baseline") for s in seeds])}
    for th in (0.45, 0.8, 1.0, 1.2):
        results[f"ama@{th}"] = mean([run_one(s, "ama", AMAConfig(discard_threshold=th)) for s in seeds])
    keys = ["episodic_rows", "fts_rows", "db_kb", "hit@3", "acc@1", "false_memory_top1", "retrieval_ms_mean",
            "noise_kept_frac", "false_review_rate_rewords", "wrong_claims_blocked_from_index", "admit_ms_per_item"]
    print(f"{'system':<10}" + "".join(f"{k[:14]:>16}" for k in keys))
    for name, r in results.items():
        print(f"{name:<10}" + "".join(f"{r[k]:>16.3f}" for k in keys))
    json.dump(results, open("experiments/ama/results.json", "w"), indent=2)
