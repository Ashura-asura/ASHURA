"""P15/P16/P17: calibrate AMA's discard threshold and measure admission cost/storage.

Synthetic labelled stream (same author as AMA). A record is a positive when it is verified and
should be retrievable; negatives are noise, unverified claims and contradictory claims. The
reported precision/recall are about *admission policy*, not factual understanding.

    python -m experiments.ama.calibrate
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
from memory.episodic import Experience

VOCAB = ("weather meeting notes remind later thanks great hello again maybe lunch music movie coffee "
         "travel plan idea random thing ok sure here you go").split()
THRESHOLDS = (0.0, 0.2, 0.45, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0)


def make_stream(seed: int, n: int = 120) -> tuple[list[tuple[str, bool, Experience]], dict]:
    rng = random.Random(seed)
    stream: list[tuple[str, bool, Experience]] = []
    truth = {}
    for i in range(n):
        q = f"what is the access code for project P{i}"
        code, wrong = rng.randint(1000, 9999), rng.randint(1000, 9999)
        while wrong == code:
            wrong = rng.randint(1000, 9999)
        truth[q] = (str(code), str(wrong))
        stream.append(("useful", True, Experience(q, f"the code for project P{i} is {code}",
                                                  verification_status="verified")))
        if rng.random() < 0.35:
            stream.append(("repeat", True, Experience(q, f"code is {code}", verification_status="verified")))
        stream.append(("unverified", False, Experience(
            f"novel unverified question {seed}-{i}", f"model claim {seed}-{i}-{wrong}",
            verification_status="unverified")))
        stream.append(("contradiction", False, Experience(q, f"the code for project P{i} is {wrong}",
                                                          verification_status="unverified")))
        stream.append(("noise", False, Experience(
            " ".join(rng.choices(VOCAB, k=5)) + f" token{seed}_{i}a",
            " ".join(rng.choices(VOCAB, k=6)) + f" token{seed}_{i}b")))
    rng.shuffle(stream)
    return stream, truth


def run_one(seed: int, threshold: float) -> dict:
    stream, _ = make_stream(seed)
    path = os.path.join(tempfile.mkdtemp(), "cal.db")
    db = Database(path)
    ama = AMA(db, AMAConfig(discard_threshold=threshold))
    tp = fp = fn = tn = 0
    lat = []
    for kind, positive, x in stream:
        t0 = time.perf_counter()
        d = ama.admit(x)
        lat.append((time.perf_counter() - t0) * 1000)
        admitted = d.decision == "ADMITTED"
        if positive and d.decision in {"ADMITTED", "MERGED"}:
            tp += 1
        elif positive:
            fn += 1
        elif admitted:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    report = ama.storage_report()
    out = {
        "threshold": threshold,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "noise_kept": fp,
        "admit_ms_mean": round(statistics.mean(lat), 4),
        "admit_ms_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 4),
        "db_kb": round(os.path.getsize(path) / 1024, 1),
        "storage_bytes": report["total_bytes"] or report["rows"],
        "rows": report["rows"],
    }
    db.close()
    return out


def baseline(seed: int) -> dict:
    stream, _ = make_stream(seed)
    path = os.path.join(tempfile.mkdtemp(), "base.db")
    db = Database(path)
    sys_ = StoreEverything(db)
    lat = []
    for _, positive, x in stream:
        t0 = time.perf_counter(); sys_.admit(x); lat.append((time.perf_counter() - t0) * 1000)
    out = {"admit_ms_mean": round(statistics.mean(lat), 4), "db_kb": round(os.path.getsize(path) / 1024, 1),
           "rows": sys_.episodic.count()}
    db.close()
    return out


def mean(rows: list[dict]) -> dict:
    return {k: round(statistics.mean(r[k] for r in rows), 4) if isinstance(rows[0][k], (int, float)) else rows[0][k]
            for k in rows[0]}


if __name__ == "__main__":
    seeds = [1, 2, 3]
    results = {"baseline": mean([baseline(s) for s in seeds])}
    for th in THRESHOLDS:
        results[f"ama@{th}"] = mean([run_one(s, th) for s in seeds])
    best = max((r for k, r in results.items() if k.startswith("ama@")), key=lambda r: r["f1"])
    results["best_by_f1"] = best["threshold"]
    out = {"experiment": "P15-P17", "seeds": seeds, "results": results}
    print(json.dumps(out, indent=2))
    with open("experiments/ama/calibration.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
