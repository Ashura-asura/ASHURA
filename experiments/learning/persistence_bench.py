"""EXP-017: consolidation persistence and retention across a process restart (F-043/A02/A03).

EXP-014 shows that a verified correction can train a NumPy candidate, pass NGR and predict held-out
wordings inside one process. This experiment asks the narrower persistence question: after the
promoted candidate is written to ``CheckpointStore`` and the process exits, can a fresh process load
the stable artifact, still solve the corrected held-out wordings, retain the old capability, and
restore the parent checkpoint by rollback?

This is not a language-model fine-tune. The candidate is the small NumPy adaptive memory; the
``tony:7b`` weights are untouched.

    python -m experiments.learning.persistence_bench
    python -m experiments.learning.persistence_bench --verify <checkpoint-root> --case <id> --seed 0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from evaluation.latency import rss_mb
from evaluation.ngr import NGRPolicy
from learning.cage import CAGE
from learning.corrections import parse_correction
from learning.dream import DreamConfig
from learning.loop import run_verified_correction
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from plasticity.fast_weights import FastWeights
from plasticity.gated_update import GatedUpdater
from plasticity.slow_weights import CheckpointStore

from experiments.learning.correction_bench import (
    DIM,
    load_corpus,
    make_buffer,
    make_trace,
    seed_stable,
)

RESULT = Path("experiments/learning/persistence.json")
SEEDS = (0, 1)
OLD_CHECKPOINT = "old_memory.npz"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _size_kb(path: str | Path) -> float:
    return round(Path(path).stat().st_size / 1024, 1)


def _case(case_id: str) -> dict:
    corpus = load_corpus()
    for case in corpus["verified_cases"]:
        if case["id"] == case_id:
            return case
    raise KeyError(f"unknown case {case_id!r}")


def _vocabulary(case: dict) -> tuple[str, ...]:
    """The same fixed vocabulary DREAM derives from the training split plus the correction."""
    buffer = make_buffer(case)
    values = {item.value for item in buffer.training_set()}
    values.add(case["answer"])
    return tuple(sorted(values))


def _score(memory: AdaptiveMemory, items, vocabulary: tuple[str, ...]) -> dict:
    predictions = []
    for item in items:
        predicted, _ = memory.recall(item.key, list(vocabulary))
        predictions.append({
            "id": item.id,
            "category": item.category,
            "key": item.key,
            "expected": item.value,
            "predicted": predicted,
            "correct": predicted == item.value,
        })
    by_category: dict[str, list[bool]] = {}
    for row in predictions:
        by_category.setdefault(row["category"], []).append(row["correct"])
    return {
        "predictions": predictions,
        "correct": sum(1 for row in predictions if row["correct"]),
        "total": len(predictions),
        "by_category": {
            category: {"correct": sum(values), "total": len(values)}
            for category, values in sorted(by_category.items())
        },
    }


def write_case(case: dict, seed: int, root: str) -> dict:
    """Run the verified-correction loop in this process and promote the candidate."""
    started = time.perf_counter()
    store = CheckpointStore(root)
    buffer = make_buffer(case)
    seed_stable(store, buffer, seed)
    fast = FastWeights()
    parsed = parse_correction(case["correction"])
    cfg = DreamConfig(target="corrected", dim=DIM, min_train=1, replay=True,
                      initialization="stable", seed=seed)
    result = run_verified_correction(
        parsed, make_trace(case), cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer,
        store=store, policy=NGRPolicy("corrected", min_target_gain=0.5), cfg=cfg)
    current = store.current()
    artifact = store.load(current) if current else None
    dream = result.dream or {}
    return {
        "pid": os.getpid(),
        "case": case["id"],
        "seed": seed,
        "stage": result.stage,
        "promoted": result.promoted,
        "stable_name": current.name if current else None,
        "stable_artifact": current.artifact if current else None,
        "stable_sha256": _sha256(artifact) if artifact else None,
        "stable_size_kb": _size_kb(artifact) if artifact else None,
        "write_ms": round((time.perf_counter() - started) * 1000, 3),
        "rss_mb": round(rss_mb(), 1),
        "dream_target": dream.get("scores", {}).get("corrected"),
        "dream_old": dream.get("scores", {}).get("old"),
    }


def verify_case(root: str, case_id: str, seed: int) -> dict:
    """Fresh-process side: load the promoted artifact, evaluate it, then roll back."""
    started = time.perf_counter()
    case = _case(case_id)
    store = CheckpointStore(root)
    current = store.current()
    if current is None:
        return {"pid": os.getpid(), "case": case_id, "error": "no stable checkpoint"}
    artifact = store.load(current)
    vocabulary = _vocabulary(case)
    buffer = make_buffer(case)

    memory = AdaptiveMemory.load(str(artifact), AMemConfig(dim_k=DIM, dim_v=DIM, seed=seed))
    promoted = _score(memory, buffer.heldout(), vocabulary)

    parent = store.rollback()
    parent_artifact = store.load(parent)
    parent_memory = AdaptiveMemory.load(
        str(parent_artifact), AMemConfig(dim_k=DIM, dim_v=DIM, seed=seed))
    restored = _score(parent_memory, buffer.heldout(), vocabulary)

    return {
        "pid": os.getpid(),
        "case": case_id,
        "seed": seed,
        "stable_name": current.name,
        "stable_artifact": current.artifact,
        "stable_sha256": _sha256(artifact),
        "verify_ms": round((time.perf_counter() - started) * 1000, 3),
        "rss_mb": round(rss_mb(), 1),
        "promoted": promoted,
        "rollback": {
            "parent_name": parent.name,
            "parent_artifact": parent.artifact,
            "scores": restored,
        },
    }


def _run_verify(root: str, case_id: str, seed: int) -> dict:
    command = [sys.executable, "-m", "experiments.learning.persistence_bench",
               "--verify", root, "--case", case_id, "--seed", str(seed)]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=120)
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": "verify process did not return JSON",
                "returncode": proc.returncode, "stdout": proc.stdout[-500:],
                "stderr": proc.stderr[-500:]}


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return round(ordered[middle] if len(ordered) % 2 else
                 (ordered[middle - 1] + ordered[middle]) / 2, 3)


def summarize(runs: list[dict]) -> dict:
    checked = [r for r in runs if r.get("verified") and "promoted" in r["verified"]]
    target_correct = sum(r["verified"]["promoted"]["by_category"].get(
        "corrected", {}).get("correct", 0) for r in checked)
    target_total = sum(r["verified"]["promoted"]["by_category"].get(
        "corrected", {}).get("total", 0) for r in checked)
    old_correct = sum(r["verified"]["promoted"]["by_category"].get(
        "old", {}).get("correct", 0) for r in checked)
    old_total = sum(r["verified"]["promoted"]["by_category"].get(
        "old", {}).get("total", 0) for r in checked)
    rollback_restored = 0
    for r in checked:
        rollback = r["verified"]["rollback"]
        scores = rollback["scores"]["by_category"]
        if (rollback["parent_name"] == OLD_CHECKPOINT
                and scores.get("old", {}).get("correct") == scores.get("old", {}).get("total")
                and scores.get("corrected", {}).get("correct") == 0):
            rollback_restored += 1
    return {
        "runs": len(runs),
        "promotions": sum(1 for r in runs if r["written"]["promoted"]),
        "restart_checks": len(checked),
        "verify_failures": sum(1 for r in runs
                               if r.get("verified") and "error" in r["verified"]),
        "restart_artifact_matches": sum(
            1 for r in checked
            if r["verified"]["stable_name"] == r["written"]["stable_name"]
            and r["verified"]["stable_sha256"] == r["written"]["stable_sha256"]),
        "target_correct": target_correct,
        "target_total": target_total,
        "target_accuracy": round(target_correct / target_total, 4) if target_total else None,
        "old_correct": old_correct,
        "old_total": old_total,
        "old_accuracy": round(old_correct / old_total, 4) if old_total else None,
        "rollback_restored": rollback_restored,
        "stable_size_kb_max": max((r["written"]["stable_size_kb"] for r in runs
                                   if r["written"]["stable_size_kb"] is not None), default=None),
        "rss_mb_max": max((r["written"]["rss_mb"] for r in runs), default=None),
        "write_ms_p50": _median([r["written"]["write_ms"] for r in runs]),
        "verify_ms_p50": _median([r["verified"]["verify_ms"] for r in checked]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EXP-017 consolidation persistence")
    parser.add_argument("--verify", metavar="ROOT")
    parser.add_argument("--case", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", default=str(RESULT))
    args = parser.parse_args()

    if args.verify:
        if not args.case:
            parser.error("--verify requires --case")
        result = verify_case(args.verify, args.case, args.seed)
        print(json.dumps(result))
        return 0 if "error" not in result else 1

    corpus = load_corpus()
    started = time.perf_counter()
    runs = []
    for seed in SEEDS:
        for case in corpus["verified_cases"]:
            root = tempfile.mkdtemp(prefix=f"exp017_{_slug(case['id'])}_{seed}_")
            written = write_case(case, seed, root)
            verified = _run_verify(root, case["id"], seed) if written["promoted"] else None
            runs.append({"written": written, "verified": verified})

    out = {
        "experiment": "EXP-017",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset": "experiments/learning/corrections_v1.json (author-written, frozen)",
        "configuration": {"dim": DIM, "seeds": list(SEEDS), "cases": len(corpus["verified_cases"]),
                          "replay": True, "initialization": "stable"},
        "runtime_s": round(time.perf_counter() - started, 2),
        "summary": summarize(runs),
        "runs": runs,
        "limits": [
            "the candidate is the NumPy adaptive memory, not tony:7b",
            "the corpus is author-written; held-out wordings share expression tokens with the key",
            "this measures persistence and retention, not general language capability",
            "one fresh process per promoted candidate; no shared-database or concurrent writers",
        ],
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["summary"], indent=2))
    return 0 if (out["summary"]["restart_checks"] == out["summary"]["promotions"]
                 and out["summary"]["target_accuracy"] == 1.0
                 and out["summary"]["old_accuracy"] == 1.0
                 and out["summary"]["rollback_restored"] == out["summary"]["restart_checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
