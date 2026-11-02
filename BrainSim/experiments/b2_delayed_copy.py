"""B2: delayed recall — recurrent core vs parameter-matched fixed MLP (blueprint B2/B6).

Hypotheses
----------
H-B2 : the recurrent core solves delayed recall on delays it was trained on.
H-DELAY: because the GRU tracks the blank delay in its state, it generalizes to delays longer
         than any seen in training better than a non-recurrent MLP that receives the same
         cue/blank/GO window.
H-COST: the GRU's advantage, if any, is reported against parameters, training time and
        per-delay accuracy, not only a single headline number.

Both arms see identical data and are trained on the same recall objective. Delays 2, 4, 6 and 8
are trained on; delays 1, 12, 16 and 20 are held out (1 is shorter, 12–20 are longer than any
training delay). Three seeds; CPU.

Run from BrainSim/:
    python -m experiments.b2_delayed_copy
    python -m experiments.b2_delayed_copy --quick
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from dataclasses import asdict
from pathlib import Path

import psutil
import torch

from brainsim.core.fixed_baseline import FixedWindowMLP
from brainsim.core.model import BrainSim
from brainsim.environment.delayed_copy import DelayedCopyConfig, make_batch
from brainsim.learning.delayed_copy_train import (evaluate_fixed, evaluate_gru,
                                                  make_fixed_dataset, train_fixed, train_gru)
from brainsim.learning.train import TrainConfig, build_model, save_checkpoint

ROOT = Path(__file__).resolve().parent.parent


def run_one(cfg: DelayedCopyConfig, seed: int, epochs: int, dataset_size: int,
            hidden: int, fixed_hidden: int, checkpoint_dir: Path | None) -> dict:
    tokens, cues, mask = make_fixed_dataset(cfg, dataset_size, seed=seed + 100)
    train_cfg = TrainConfig(hidden=hidden, epochs=epochs, seed=seed, batch_size=64,
                            checkpoint=str(checkpoint_dir / f"b2_gru_s{seed}.pt")
                            if checkpoint_dir else None)
    gru = build_model(cfg.vocab, train_cfg)
    gru, gru_history, gru_seconds = train_gru(gru, cfg, tokens, cues, mask, epochs=epochs,
                                              seed=seed, device="cpu")
    if checkpoint_dir is not None:
        save_checkpoint(gru, checkpoint_dir / f"b2_gru_s{seed}.pt", gru_history, train_cfg)

    torch.manual_seed(seed)
    fixed = FixedWindowMLP(cfg, hidden=fixed_hidden)
    fixed, fixed_history, fixed_seconds = train_fixed(fixed, cfg, tokens, cues, mask,
                                                      epochs=epochs, seed=seed, device="cpu")

    evaluations = {}
    for delay in cfg.eval_delays:
        batch = make_batch(cfg, 256, delays=(delay,), seed=seed * 1000 + delay + 7)
        evaluations[str(delay)] = {
            "gru": evaluate_gru(gru, cfg, batch),
            "fixed": evaluate_fixed(fixed, cfg, batch),
            "trained": delay in cfg.train_delays,
        }

    return {
        "seed": seed,
        "params": {"gru": gru.param_count, "fixed": fixed.param_count},
        "train_seconds": {"gru": gru_seconds, "fixed": fixed_seconds},
        "final_loss": {"gru": gru_history["loss"][-1], "fixed": fixed_history["loss"][-1]},
        "evaluation": evaluations,
        "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
    }


def summarise(runs: list[dict], delays: tuple[int, ...]) -> dict:
    out = {}
    for delay in delays:
        key = str(delay)
        row = {"delay": delay, "trained": runs[0]["evaluation"][key]["trained"]}
        for arm in ("gru", "fixed"):
            for metric in ("token_accuracy", "full_recall_accuracy"):
                values = [r["evaluation"][key][arm][metric] for r in runs]
                row[f"{arm}_{metric}_mean"] = statistics.mean(values)
                row[f"{arm}_{metric}_std"] = (statistics.pstdev(values)
                                              if len(values) > 1 else 0.0)
        out[key] = row
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--dataset-size", type=int, default=4096)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--fixed-hidden", type=int, default=352)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x]

    cfg = DelayedCopyConfig()
    if args.quick:
        cfg = DelayedCopyConfig(symbols=6, cue_len=2, max_delay=8,
                                train_delays=(1, 2), eval_delays=(1, 2, 4, 8))
        seeds, args.epochs, args.dataset_size = [0], 2, 256

    checkpoint_dir = ROOT / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    runs = []
    for seed in seeds:
        print(f"[run] seed={seed} epochs={args.epochs}", flush=True)
        run = run_one(cfg, seed, args.epochs, args.dataset_size, args.hidden,
                      args.fixed_hidden, None if args.quick else checkpoint_dir)
        runs.append(run)
        line = "  " + " ".join(
            f"d{d}:gru={run['evaluation'][str(d)]['gru']['token_accuracy']:.3f}"
            f"/{run['evaluation'][str(d)]['gru']['full_recall_accuracy']:.3f} "
            f"fixed={run['evaluation'][str(d)]['fixed']['token_accuracy']:.3f}"
            f"/{run['evaluation'][str(d)]['fixed']['full_recall_accuracy']:.3f}"
            for d in cfg.eval_delays)
        print(line, flush=True)

    summary = summarise(runs, cfg.eval_delays)
    out = {
        "experiment": "BrainSim-B2 delayed recall: recurrent core vs fixed MLP",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hypotheses": {
            "H-B2": "the recurrent core solves trained-delay recall",
            "H-DELAY": "the GRU generalizes to longer delays better than a fixed MLP",
            "H-COST": "the comparison includes parameters, time and per-delay accuracy",
        },
        "environment": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": "cpu",
            "threads": torch.get_num_threads(),
            "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
        },
        "task": asdict(cfg),
        "training": {"seeds": seeds, "epochs": args.epochs,
                     "dataset_size": args.dataset_size, "hidden": args.hidden,
                     "fixed_hidden": args.fixed_hidden, "batch_size": 64},
        "runs": runs,
        "summary": summary,
        "quick": args.quick,
    }
    results_dir = ROOT / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / ("b2_delayed_copy_quick.json" if args.quick else "b2_delayed_copy.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\nsummary  delay  trained   gru_token  gru_full  fixed_token  fixed_full")
    for delay in cfg.eval_delays:
        row = summary[str(delay)]
        print(f"  {delay:>5}  {str(row['trained']):>7}   "
              f"{row['gru_token_accuracy_mean']:.3f}      "
              f"{row['gru_full_recall_accuracy_mean']:.3f}     "
              f"{row['fixed_token_accuracy_mean']:.3f}        "
              f"{row['fixed_full_recall_accuracy_mean']:.3f}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
