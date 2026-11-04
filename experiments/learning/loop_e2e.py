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

Synthetic, author-written, single seed. It demonstrates the control flow, not general correction
understanding or a language-model fine-tune.

    python -m experiments.learning.loop_e2e
"""
from __future__ import annotations

import json
import tempfile
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


def seed_stable(store: CheckpointStore, buffer: ReplayBuffer) -> None:
    mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM))
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
            use_trace: bool = True) -> dict:
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix=f"loop_{label}_")))
    buffer = make_buffer()
    seed_stable(store, buffer)
    fast = FastWeights()
    correction = parse_correction(text)
    fast_before, _ = fast.recall("6*7", ["42", "43"])
    cfg = DreamConfig(target="corrected", dim=DIM, min_train=1, replay=replay,
                      initialization=initialization)
    result = run_verified_correction(
        correction, trace if use_trace else None,
        cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer, store=store,
        policy=NGRPolicy("corrected", min_target_gain=0.5), cfg=cfg)
    out = {
        "stage": result.stage,
        "promoted": result.promoted,
        "correction": result.correction,
        "attribution": result.attribution,
        "decision": result.decision,
        "proposal": result.proposal,
        "fast_update": result.update,
        "dream": result.dream,
        "reasons": result.reasons,
        "fast_delta_norm": round(fast.delta_norm, 4),
        "fast_recall_before": fast_before,
        "fast_recall_after": fast.recall("6*7", ["42", "43"])[0],
        "stable_before": "old_memory.npz",
        "stable_after": store.current().name if store.current() else None,
        "candidates": len(list((store.root / "candidates").glob("*.npz"))),
    }
    return out


if __name__ == "__main__":
    arms = {
        "verified_replay": run_arm("replay", "actually, 6*7 = 42", correction_trace(),
                                   initialization="stable", replay=True),
        "verified_no_replay": run_arm("noreplay", "actually, 6*7 = 42", correction_trace(),
                                      initialization="fresh", replay=False),
        "unverified_fact": run_arm("fact", "actually, the project p12 code is 9999", None,
                                   initialization="stable", replay=True),
        "false_arithmetic": run_arm("false", "actually, 6*7 = 43", correction_trace(),
                                    initialization="stable", replay=True),
        "no_trace": run_arm("notrace", "actually, 6*7 = 42", correction_trace(),
                            initialization="stable", replay=True, use_trace=False),
    }
    out = {"experiment": "EXP-013", "n_old": N_OLD, "dim": DIM, "arms": arms,
           "limits": ["synthetic, author-written, single seed",
                      "exact arithmetic is the only independently verified correction type",
                      "the candidate trains the NumPy adaptive memory, not the language model"]}
    print(json.dumps(out, indent=2))
    Path("experiments/learning/loop.json").write_text(json.dumps(out, indent=2))
