"""B4 slow consolidation: new-only fine-tuning vs replay-augmented fine-tuning.

B1/B2/B3 keep the recurrent weights frozen and adapt only fast state. B4 deliberately changes
the persistent parameters on a candidate and asks two questions:

H-B4:   fine-tuning on a new rule family causes old-rule forgetting beyond the 2% tolerance.
H-REPLAY: mixing replayed old-rule sequences into the same fine-tuning schedule reduces that
          forgetting while keeping most of the new-rule gain.

Both arms start from the same base checkpoint, see exactly the same new-rule sequences and use
the same optimiser schedule. The replay arm sees additional old sequences, so its total sample
count is reported; the comparison is about the method, not equal FLOPs.

Run from BrainSim/:
    python -m experiments.b4_consolidation
    python -m experiments.b4_consolidation --seeds 0,1,2,3
"""
from __future__ import annotations

import argparse
import copy
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np
import psutil
import torch

from brainsim.environment.sequence_tasks import SequenceConfig, make_rules, walk
from brainsim.learning.finetune import finetune
from brainsim.learning.replay import ReplayBuffer, ReplayConfig
from brainsim.learning.train import (TrainConfig, build_model, load_checkpoint,
                                     save_checkpoint, sequence_accuracy, train_offline)

ROOT = Path(__file__).resolve().parent.parent
RETENTION_TOLERANCE = 0.02
CHECKPOINT_DIR = ROOT / "checkpoints" / "b4"


def rule_sequences(rules, starts_per_rule: int, seq_len: int, seed: int) -> torch.Tensor:
    """Walks from a list of rules: (len(rules) * starts_per_rule, seq_len)."""
    rng = np.random.default_rng(seed)
    rows = []
    for rule in rules:
        for _ in range(starts_per_rule):
            rows.append(walk(int(rng.integers(len(rule))), rule, seq_len - 1))
    return torch.tensor(rows, dtype=torch.long)


def evaluate(model, old_val: torch.Tensor, new_val: torch.Tensor) -> dict:
    return {"old_accuracy": sequence_accuracy(model, old_val),
            "new_accuracy": sequence_accuracy(model, new_val)}


def run_seed(seed: int, base_epochs: int, finetune_epochs: int,
             checkpoint_dir: Path = CHECKPOINT_DIR) -> dict:
    seq_cfg = SequenceConfig(seed=seed)
    rules = make_rules(seq_cfg)
    old_train = rule_sequences(rules.train, 32, seq_cfg.seq_len, seed + 101)
    old_val = rule_sequences(rules.train, 16, seq_cfg.seq_len, seed + 102)
    new_fit = rule_sequences(rules.heldout, 8, seq_cfg.seq_len, seed + 103)
    new_val = rule_sequences(rules.heldout, 16, seq_cfg.seq_len, seed + 104)

    base_cfg = TrainConfig(hidden=128, epochs=base_epochs, batch_size=32, seed=seed)
    model = build_model(seq_cfg.vocab, base_cfg)
    base_history, base_seconds = train_offline(model, old_train, base_cfg, val_tokens=old_val)
    base = evaluate(model, old_val, new_val)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    base_path = checkpoint_dir / f"b4_base_s{seed}.pt"
    save_checkpoint(model, base_path, base_history, base_cfg)

    arms = {}
    for arm_name, use_replay in (("new_only", False), ("replay", True)):
        arm_model = copy.deepcopy(model)
        replay = None
        if use_replay:
            replay = ReplayBuffer(ReplayConfig(capacity=512))
            replay.add(old_train)
        arm_cfg = TrainConfig(hidden=128, epochs=finetune_epochs, batch_size=32, seed=seed)
        history, seconds = finetune(
            arm_model, new_fit, arm_cfg, epochs=finetune_epochs, replay=replay,
            replay_ratio=0.5, batch_size=32, lr=3e-3, seed=seed,
            checkpoint=checkpoint_dir / f"b4_{arm_name}_s{seed}.pt")
        after = evaluate(arm_model, old_val, new_val)
        reloaded = load_checkpoint(checkpoint_dir / f"b4_{arm_name}_s{seed}.pt")
        persisted = evaluate(reloaded, old_val, new_val)
        arms[arm_name] = {
            **after,
            "old_drop": base["old_accuracy"] - after["old_accuracy"],
            "old_retention": after["old_accuracy"] / max(base["old_accuracy"], 1e-9),
            "new_gain": after["new_accuracy"] - base["new_accuracy"],
            "within_tolerance": bool(base["old_accuracy"] - after["old_accuracy"]
                                     <= RETENTION_TOLERANCE),
            "finetune_seconds": seconds,
            "final_loss": history["loss"][-1],
            "old_examples_seen": len(old_train) if use_replay else 0,
            "new_examples_seen": len(new_fit) * finetune_epochs,
            "checkpoint": str(checkpoint_dir / f"b4_{arm_name}_s{seed}.pt"),
            "checkpoint_roundtrip": bool(
                abs(persisted["old_accuracy"] - after["old_accuracy"]) < 1e-9
                and abs(persisted["new_accuracy"] - after["new_accuracy"]) < 1e-9),
            "checkpoint_old_accuracy": persisted["old_accuracy"],
            "checkpoint_new_accuracy": persisted["new_accuracy"],
        }

    return {
        "seed": seed,
        "params": model.param_count,
        "base_train_seconds": base_seconds,
        "base_final_loss": base_history["loss"][-1],
        "base": base,
        "arms": arms,
        "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
    }


def summarise(runs: list[dict]) -> dict:
    def mean(values):
        return statistics.mean(values)

    def stdev(values):
        values = list(values)
        return statistics.pstdev(values) if len(values) > 1 else 0.0

    out = {"seeds": len(runs), "retention_tolerance": RETENTION_TOLERANCE}
    for key in ("old_accuracy", "new_accuracy"):
        out[f"base_{key}_mean"] = mean(r["base"][key] for r in runs)
        out[f"base_{key}_std"] = stdev(r["base"][key] for r in runs)
    for arm in ("new_only", "replay"):
        def values(field):
            return [r["arms"][arm][field] for r in runs]
        for field in ("old_accuracy", "new_accuracy", "old_drop", "old_retention",
                      "new_gain", "finetune_seconds"):
            out[f"{arm}_{field}_mean"] = mean(values(field))
            out[f"{arm}_{field}_std"] = stdev(values(field))
        out[f"{arm}_within_tolerance_count"] = sum(
            1 for r in runs if r["arms"][arm]["within_tolerance"])
        out[f"{arm}_checkpoint_roundtrip_count"] = sum(
            1 for r in runs if r["arms"][arm]["checkpoint_roundtrip"])
    out["replay_reduces_drop"] = bool(
        out["replay_old_drop_mean"] < out["new_only_old_drop_mean"])
    out["replay_keeps_new_accuracy"] = bool(
        out["replay_new_accuracy_mean"] >= out["new_only_new_accuracy_mean"] - 0.02)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--base-epochs", type=int, default=30)
    parser.add_argument("--finetune-epochs", type=int, default=15)
    parser.add_argument("--quick", action="store_true",
                        help="smoke run only: 2 epochs, seed 0; not a result")
    args = parser.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    base_epochs = 2 if args.quick else args.base_epochs
    finetune_epochs = 2 if args.quick else args.finetune_epochs
    if args.quick:
        seeds = seeds[:1]

    started = time.perf_counter()
    runs = [run_seed(s, base_epochs, finetune_epochs) for s in seeds]
    summary = summarise(runs)
    out = {
        "experiment": "B4 slow consolidation: new-only vs replay",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "quick": bool(args.quick),
        "warning": "smoke run only; not a result" if args.quick else None,
        "hypotheses": {
            "H-B4": "fine-tuning on new rules forgets old rules beyond 2%",
            "H-REPLAY": "replaying old sequences reduces forgetting while retaining new accuracy",
        },
        "task": "8 old permutation rules, then 8 disjoint new rules",
        "training": {
            "seeds": seeds,
            "base_epochs": base_epochs,
            "finetune_epochs": finetune_epochs,
            "hidden": 128,
            "batch_size": 32,
            "finetune_lr": 3e-3,
            "replay_ratio": 0.5,
            "replay_capacity": 512,
            "old_train_sequences": 8 * 32,
            "new_finetune_sequences": 8 * 8,
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": "cpu",
        },
        "elapsed_seconds": time.perf_counter() - started,
        "runs": runs,
        "summary": summary,
        "limits": [
            "synthetic permutation task only",
            "three seeds; CPU laptop timing is noisy",
            "the replay arm sees more examples than new-only",
            "retention is measured on new random walks from the old rules, not a separate domain",
        ],
    }
    name = "b4_consolidation_quick.json" if args.quick else "b4_consolidation.json"
    path = ROOT / "experiments" / "results" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
