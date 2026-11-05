"""EXP-014: larger frozen verified-correction benchmark (F-044).

Ten arithmetic correction cases, five seeds, two arms, and five control probes. Each case uses a
fresh stable checkpoint built from the same 20-word old capability. The verified arm trains with
replay from a stable initialization; the negative arm uses a fresh memory and no replay.

The corpus is frozen in ``corrections_v1.json`` and is author-written. Exact arithmetic is
independently re-checked when the corpus loads, but the wording and the task selection are not
independently authored. This is a control-flow and non-regression benchmark, not a language-model
fine-tune.

    python -m experiments.learning.correction_bench
"""
from __future__ import annotations

import json
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from brain.execution_trace import ExecutionTrace, TraceStep
from evaluation.ngr import NGRPolicy
from learning.cage import CAGE
from learning.corrections import parse_correction
from learning.dream import DreamConfig
from learning.loop import run_verified_correction
from learning.replay import ReplayBuffer, ReplayItem
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from plasticity.fast_weights import FastWeights
from plasticity.gated_update import GatedUpdater
from plasticity.slow_weights import CheckpointStore

N_OLD = 20
DIM = 128
SEEDS = (0, 1, 2, 3, 4)
CORPUS = Path(__file__).with_name("corrections_v1.json")
# Non-numeric old values keep the answer vocabulary from colliding with small arithmetic answers.
OLD_VALUES = ("amber", "birch", "cedar", "delta", "ember", "fjord", "garnet", "harbor",
              "indigo", "juniper", "kelp", "larch", "maple", "nickel", "onyx", "prairie",
              "quartz", "raven", "sable", "topaz")


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [max(0.0, centre - half), min(1.0, centre + half)]


def load_corpus() -> dict:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    for case in data["verified_cases"]:
        parsed = parse_correction(case["correction"])
        if parsed.state != "verified":
            raise ValueError(f"{case['id']}: corpus correction is not verified: {parsed.reason}")
        if parsed.key != case["key"] or parsed.value != case["answer"]:
            raise ValueError(f"{case['id']}: expected key/value {case['key']!r}/{case['answer']!r}, "
                             f"got {parsed.key!r}/{parsed.value!r}")
        if case["wrong_answer"] == case["answer"]:
            raise ValueError(f"{case['id']}: wrong_answer must differ from answer")
        if len({key for key in case["heldout"]}) != len(case["heldout"]):
            raise ValueError(f"{case['id']}: duplicate held-out wording")
        if case["key"] in case["heldout"]:
            raise ValueError(f"{case['id']}: training key appears in held-out wordings")
    for control in data["controls"]:
        parsed = parse_correction(control["correction"])
        if parsed.state != control["state"]:
            raise ValueError(f"{control['id']}: expected state {control['state']!r}, got {parsed.state!r}")
    return data


def make_buffer(case: dict) -> ReplayBuffer:
    buffer = ReplayBuffer()
    for i, value in enumerate(OLD_VALUES):
        buffer.add(ReplayItem(f"old-{i}", f"entity{i} old", value, category="old", verified=True))
        buffer.add(ReplayItem(f"old-h-{i}", f"old entity{i}", value, category="old",
                              verified=True, split="heldout"))
    for i, wording in enumerate(case["heldout"]):
        buffer.add(ReplayItem(f"target-h-{i}", wording, case["answer"], category="corrected",
                              verified=True, split="heldout"))
    return buffer


def make_trace(case: dict) -> ExecutionTrace:
    trace = ExecutionTrace(task=case["task"])
    trace.add(TraceStep("arithmetic", case["key"], case["answer"], 0.4, ok=True,
                        note="exact evaluator"))
    trace.add(TraceStep("language", case["task"], case["wrong_answer"], 12.0, ok=True))
    return trace


def control_trace(control: dict) -> ExecutionTrace | None:
    parsed = parse_correction(control["correction"])
    if control["trace"] == "none":
        return None
    trace = ExecutionTrace(task=parsed.key)
    if control["trace"] == "unattributable":
        # No registered verifier covers 'reasoning'; the final value alone is not enough to attribute.
        trace.add(TraceStep("reasoning", parsed.key, parsed.value, 1.0, ok=True))
        return trace
    if parsed.kind == "arithmetic" and parsed.expected is not None:
        trace.add(TraceStep("arithmetic", parsed.key, parsed.expected, 0.4, ok=True,
                            note="exact evaluator"))
    trace.add(TraceStep("language", parsed.key, parsed.value, 5.0, ok=True))
    return trace


def seed_stable(store: CheckpointStore, buffer: ReplayBuffer, seed: int) -> None:
    memory = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM, seed=seed))
    for item in buffer.training_set():
        if item.category == "old":
            memory.write(item.key, item.value)
    source = store.root / "old_memory_source.npz"
    memory.save(str(source))
    store.stage(source, "old_memory.npz")
    from evaluation.ngr import NGRResult
    store.promote("old_memory.npz", NGRResult(True, ["fixture: stable old-capability memory"], {}))


def new_candidates(store: CheckpointStore) -> int:
    return sum(1 for path in (store.root / "candidates").glob("*.npz")
               if path.name != "old_memory.npz")


def heldout_predictions(store: CheckpointStore, candidate: str, buffer: ReplayBuffer,
                        seed: int) -> list[dict]:
    memory = AdaptiveMemory.load(str(store.root / "candidates" / candidate),
                                 AMemConfig(dim_k=DIM, dim_v=DIM, seed=seed))
    vocabulary = tuple(sorted({item.value for item in buffer.training_set()}))
    return [{"key": item.key, "expected": item.value,
             "predicted": memory.recall(item.key, list(vocabulary))[0]}
            for item in buffer.heldout("corrected")]


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def run_case(case: dict, seed: int, *, initialization: str, replay: bool) -> dict:
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix=f"exp014_{_slug(case['id'])}_{seed}_")))
    buffer = make_buffer(case)
    seed_stable(store, buffer, seed)
    fast = FastWeights()
    parsed = parse_correction(case["correction"])
    cfg = DreamConfig(target="corrected", dim=DIM, min_train=1, replay=replay,
                      initialization=initialization, seed=seed)
    result = run_verified_correction(
        parsed, make_trace(case), cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer,
        store=store, policy=NGRPolicy("corrected", min_target_gain=0.5), cfg=cfg)
    dream = result.dream or {}
    predictions = (heldout_predictions(store, dream["candidate"], buffer, seed)
                   if dream.get("candidate") else [])
    candidates = new_candidates(store)
    return {
        "case": case["id"], "seed": seed, "initialization": initialization, "replay": replay,
        "stage": result.stage, "promoted": result.promoted,
        "correction_state": result.correction["state"],
        "attributed_module": (result.attribution or {}).get("module"),
        "expected_answer": case["answer"],
        "fast_recall_after": fast.recall(case["key"], [case["wrong_answer"], case["answer"]])[0],
        "fast_delta_norm": round(fast.delta_norm, 6),
        "new_candidates": candidates,
        "stable_changed": (store.current().name if store.current() else None) != "old_memory.npz",
        "old": dream.get("scores", {}).get("old"),
        "corrected": dream.get("scores", {}).get("corrected"),
        "stable_old": dream.get("stable", {}).get("old"),
        "stable_corrected": dream.get("stable", {}).get("corrected"),
        "train_n": dream.get("train_n"),
        "heldout_predictions": predictions,
        "heldout_correct": sum(1 for p in predictions if p["predicted"] == p["expected"]),
        "heldout_total": len(predictions),
        "reasons": result.reasons[:4],
    }


def run_control(control: dict, seed: int) -> dict:
    case = {"id": control["id"], "key": parse_correction(control["correction"]).key,
            "answer": parse_correction(control["correction"]).value,
            "wrong_answer": "-", "task": "control", "heldout": []}
    store = CheckpointStore(Path(tempfile.mkdtemp(
        prefix=f"exp014_control_{_slug(control['id'])}_{seed}_")))
    buffer = make_buffer({**case, "heldout": ["what is 6*7"]})   # only used if safety fails
    seed_stable(store, buffer, seed)
    fast = FastWeights()
    parsed = parse_correction(control["correction"])
    cfg = DreamConfig(target="corrected", dim=DIM, min_train=1, replay=True,
                      initialization="stable", seed=seed)
    result = run_verified_correction(
        parsed, control_trace(control), cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer,
        store=store, policy=NGRPolicy("corrected", min_target_gain=0.5), cfg=cfg)
    candidates = new_candidates(store)
    changed = (store.current().name if store.current() else None) != "old_memory.npz"
    return {
        "control": control["id"], "seed": seed,
        "expected_state": control["state"], "expected_stage": control["stage"],
        "correction_state": result.correction["state"], "stage": result.stage,
        "promoted": result.promoted, "fast_delta_norm": round(fast.delta_norm, 6),
        "new_candidates": candidates, "stable_changed": changed,
        "matched": (result.correction["state"] == control["state"]
                    and result.stage == control["stage"] and not result.promoted
                    and fast.delta_norm == 0.0 and candidates == 0 and not changed),
        "reasons": result.reasons[:3],
    }


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize(runs: list[dict]) -> dict:
    promotions = sum(1 for r in runs if r["promoted"])
    scored = [r for r in runs if r["corrected"] is not None]
    heldout_correct = sum(r["heldout_correct"] for r in runs)
    heldout_total = sum(r["heldout_total"] for r in runs)
    by_case = {}
    for case in sorted({r["case"] for r in runs}):
        rows = [r for r in runs if r["case"] == case]
        by_case[case] = {
            "runs": len(rows),
            "promotions": sum(1 for r in rows if r["promoted"]),
            "target_mean": mean([r["corrected"] for r in rows if r["corrected"] is not None]),
            "stable_target_mean": mean([r["stable_corrected"] for r in rows
                                        if r["stable_corrected"] is not None]),
            "accidental_stable_hits": sum(1 for r in rows if (r["stable_corrected"] or 0) > 0),
            "heldout_correct": sum(r["heldout_correct"] for r in rows),
            "heldout_total": sum(r["heldout_total"] for r in rows),
        }
    return {
        "runs": len(runs),
        "stages": dict(sorted(Counter(r["stage"] for r in runs).items())),
        "promotions": promotions,
        "promotion_rate": round(promotions / len(runs), 4) if runs else None,
        "promotion_rate_ci95": wilson(promotions, len(runs)),
        "fast_recall_correct": sum(1 for r in runs
                                   if r["fast_recall_after"] == r.get("expected_answer")),
        "old_mean": mean([r["old"] for r in scored]),
        "target_mean": mean([r["corrected"] for r in scored]),
        "stable_old_mean": mean([r["stable_old"] for r in scored]),
        "stable_target_mean": mean([r["stable_corrected"] for r in scored]),
        "accidental_stable_hits": sum(1 for r in runs if (r["stable_corrected"] or 0) > 0),
        "heldout_correct": heldout_correct,
        "heldout_total": heldout_total,
        "heldout_accuracy": round(heldout_correct / heldout_total, 4) if heldout_total else None,
        "new_candidates": sum(r["new_candidates"] for r in runs),
        "stable_changed": sum(1 for r in runs if r["stable_changed"]),
        "by_case": by_case,
    }


def main() -> None:
    corpus = load_corpus()
    arms: dict[str, list[dict]] = defaultdict(list)
    for seed in SEEDS:
        for case in corpus["verified_cases"]:
            arms["verified_replay"].append(run_case(
                case, seed, initialization="stable", replay=True))
            arms["verified_no_replay"].append(run_case(
                case, seed, initialization="fresh", replay=False))
    controls = [run_control(control, seed) for seed in SEEDS for control in corpus["controls"]]

    out = {
        "experiment": "EXP-014",
        "corpus": {"version": corpus["version"], "frozen_on": corpus["frozen_on"],
                   "provenance": corpus["provenance"],
                   "verified_cases": len(corpus["verified_cases"]),
                   "control_probes": len(corpus["controls"]),
                   "seeds": list(SEEDS), "n_old": N_OLD, "dim": DIM},
        "arms": {name: {"summary": summarize(rows), "runs": rows} for name, rows in arms.items()},
        "controls": {
            "summary": {
                "runs": len(controls),
                "matched": sum(1 for r in controls if r["matched"]),
                "all_refused_without_update": all(r["matched"] for r in controls),
                "new_candidates": sum(r["new_candidates"] for r in controls),
                "stable_changes": sum(1 for r in controls if r["stable_changed"]),
                "fast_updates": sum(1 for r in controls if r["fast_delta_norm"] != 0.0),
            },
            "runs": controls,
        },
        "limits": [
            "author-written synthetic corpus, not an independently authored task set",
            "exact arithmetic is the only independently verified correction type",
            "the candidate trains the NumPy adaptive memory, not the language model",
            "held-out wordings share the expression tokens with the correction key",
            "a promotion proves only that this polynomial recall passed this frozen suite",
        ],
    }
    Path("experiments/learning/correction_bench.json").write_text(json.dumps(out, indent=2),
                                                                 encoding="utf-8")
    print(json.dumps({
        "experiment": out["experiment"],
        "verified_replay": out["arms"]["verified_replay"]["summary"],
        "verified_no_replay": {k: v for k, v in out["arms"]["verified_no_replay"]["summary"].items()
                               if k != "by_case"},
        "controls": out["controls"]["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
