"""EXP-013: end-to-end verified-correction loop (P07/P75).

Scenario: a language answer to an arithmetic question is wrong; the user corrects it; ASHURA
independently checks the correction with exact arithmetic; CAGE attributes the failing component;
a bounded fast update is applied; DREAM trains a candidate; NGR decides promotion or rollback.

Arms:
  verified_replay      verified correction + stable init + replay  -> expected promotion
  verified_no_replay   verified correction + fresh init + no replay -> expected NGR rejection
  unverified_fact      user correction ASHURA cannot check -> refused before training
  false_arithmetic     arithmetic correction that is false -> refused before training
  no_trace             verified correction without an execution trace -> refused

Synthetic, author-written, five seeds. It demonstrates the control flow, not general correction
understanding or a language-model fine-tune.

    python -m experiments.learning.loop_e2e
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from brain.execution_trace import ExecutionTrace, TraceStep
from evaluation.ngr import NGRPolicy, NGRResult
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


def make_buffer() -> ReplayBuffer:
    b = ReplayBuffer()
    for i in range(N_OLD):
        b.add(ReplayItem(f"old-{i}", f"entity{i} old", f"old-{i}", category="old", verified=True))
        b.add(ReplayItem(f"old-h-{i}", f"old entity{i}", f"old-{i}", category="old", verified=True,
                         split="heldout"))
    # Evaluation item for the corrected capability; it is not in the training split.
    b.add(ReplayItem("new-h-0", "what is 6*7", "42", category="corrected", verified=True,
                     split="heldout"))
    b.add(ReplayItem("new-h-1", "please compute 6*7", "42", category="corrected", verified=True,
                     split="heldout"))
    return b


def seed_stable(store: CheckpointStore, buffer: ReplayBuffer, seed: int = 0) -> None:
    mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM, seed=seed))
    for it in buffer.training_set():
        if it.category == "old":
            mem.write(it.key, it.value)
    tmp = Path(tempfile.mkdtemp()) / "old_memory.npz"
    mem.save(str(tmp))
    store.stage(tmp, "old_memory.npz")
    store.promote("old_memory.npz", NGRResult(True, ["fixture: stable old-capability memory"], {}))


def correction_trace() -> ExecutionTrace:
    trace = ExecutionTrace(task="what is 6*7")
    trace.add(TraceStep("arithmetic", "6*7", "42", 0.5, ok=True, note="exact evaluator"))
    trace.add(TraceStep("language", "6*7", "43", 12.0, ok=True))
    return trace


def run_arm(label: str, text: str, trace, *, initialization: str, replay: bool,
            seed: int, use_trace: bool = True) -> dict:
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix=f"loop_{label}_s{seed}_")))
    buffer = make_buffer()
    seed_stable(store, buffer, seed)
    fast = FastWeights()
    correction = parse_correction(text)
    fast_before, _ = fast.recall("6*7", ["42", "43"])
    cfg = DreamConfig(target="corrected", dim=DIM, min_train=1, replay=replay,
                      initialization=initialization, seed=seed)
    result = run_verified_correction(
        correction, trace if use_trace else None,
        cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer, store=store,
        policy=NGRPolicy("corrected", min_target_gain=0.5), cfg=cfg)
    dream = result.dream or {}
    return {
        "seed": seed,
        "stage": result.stage,
        "promoted": result.promoted,
        "correction_state": result.correction["state"],
        "attributed_module": (result.attribution or {}).get("module"),
        "fast_delta_norm": round(fast.delta_norm, 4),
        "fast_recall_before": fast_before,
        "fast_recall_after": fast.recall("6*7", ["42", "43"])[0],
        "old": dream.get("scores", {}).get("old"),
        "corrected": dream.get("scores", {}).get("corrected"),
        "stable_old": dream.get("stable", {}).get("old"),
        "stable_corrected": dream.get("stable", {}).get("corrected"),
        "train_n": dream.get("train_n"),
        "stable_changed": (store.current().name if store.current() else None) != "old_memory.npz",
        "candidates": len(list((store.root / "candidates").glob("*.npz"))),
        "reasons": result.reasons[:4],
    }


def summarize(runs: list[dict]) -> dict:
    scored = [r for r in runs if r["old"] is not None]
    return {
        "runs": len(runs),
        "stages": dict(sorted(Counter(r["stage"] for r in runs).items())),
        "promotions": sum(1 for r in runs if r["promoted"]),
        "fast_recall_after_42": sum(1 for r in runs if r["fast_recall_after"] == "42"),
        "old_mean": round(sum(r["old"] for r in scored) / len(scored), 4) if scored else None,
        "corrected_mean": (round(sum(r["corrected"] for r in scored) / len(scored), 4)
                           if scored else None),
        "stable_old_mean": (round(sum(r["stable_old"] for r in scored) / len(scored), 4)
                            if scored else None),
        "stable_corrected_mean": (round(sum(r["stable_corrected"] for r in scored) / len(scored), 4)
                                  if scored else None),
        "stable_changed": sum(1 for r in runs if r["stable_changed"]),
    }


# (arm label, correction text, needs a trace, initialization, replay)
ARMS = {
    "verified_replay": ("replay", "actually, 6*7 = 42", True, "stable", True),
    "verified_no_replay": ("noreplay", "actually, 6*7 = 42", True, "fresh", False),
    "unverified_fact": ("fact", "actually, the project p12 code is 9999", False, "stable", True),
    "false_arithmetic": ("false", "actually, 6*7 = 43", True, "stable", True),
    "no_trace": ("notrace", "actually, 6*7 = 42", True, "stable", True),
}


if __name__ == "__main__":
    runs = {name: [] for name in ARMS}
    for seed in SEEDS:
        for name, (label, text, wants_trace, initialization, replay) in ARMS.items():
            runs[name].append(run_arm(
                label, text, correction_trace() if wants_trace else None,
                initialization=initialization, replay=replay,
                seed=seed, use_trace=(wants_trace and name != "no_trace")))
    arms = {name: {"summary": summarize(r), "runs": r} for name, r in runs.items()}
    out = {"experiment": "EXP-013", "n_old": N_OLD, "dim": DIM, "seeds": list(SEEDS),
           "arms": arms,
           "limits": ["synthetic, author-written, five seeds",
                      "exact arithmetic is the only independently verified correction type",
                      "the candidate trains the NumPy adaptive memory, not the language model"]}
    print(json.dumps(out, indent=2))
    Path("experiments/learning/loop.json").write_text(json.dumps(out, indent=2))
