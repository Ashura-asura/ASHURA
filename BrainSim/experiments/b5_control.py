"""B5 need and resource control: learned action selection under a budget.

Hypotheses
----------
H-B5:     a recurrent core trained on need/budget contexts selects higher-utility actions than
          always-max, need-matching without cost awareness, always-wait and random baselines.
H-CONF:   the confidence head is calibrated against whether the chosen action is optimal.
H-BUDGET: masking unaffordable actions keeps the policy within budget; the raw violation rate is
          reported rather than hidden.

This is supervised policy imitation of an oracle on a synthetic task, not reinforcement learning
and not evidence of general resource management.

Run from BrainSim/:
    python -m experiments.b5_control
    python -m experiments.b5_control --quick
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import psutil
import torch

from brainsim.core.model import BrainSim, BrainSimConfig
from brainsim.environment.control_tasks import (ACTION_COSTS, ACTIONS, NEEDS,
                                                 ControlBatch, ControlConfig,
                                                 baseline_action, make_episodes,
                                                 utility_of)
from brainsim.learning.control_train import (ControlTrainConfig, evaluate_control,
                                             simulate_model, simulate_policy, train_control)
from brainsim.learning.train import TrainConfig

ROOT = Path(__file__).resolve().parent.parent


def build_control_model(seed: int, hidden: int = 128, layers: int = 2) -> BrainSim:
    torch.manual_seed(seed)
    return BrainSim(BrainSimConfig(vocab=len(NEEDS), hidden=hidden, layers=layers,
                                   in_dim=2 * len(NEEDS) + 1,
                                   n_needs=len(NEEDS), n_actions=len(ACTIONS)))


def evaluate_baseline_open_loop(batch: ControlBatch, name: str,
                                cfg: ControlConfig) -> dict:
    costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
    actions = torch.empty_like(batch.needs)
    for t in range(batch.needs.shape[1]):
        actions[:, t] = baseline_action(name, batch.needs[:, t], batch.budgets[:, t],
                                        t=t, cfg=cfg)
    utility = utility_of(batch.needs, actions)
    cost = costs[actions].float()
    return {
        "action_accuracy": float((actions == batch.actions).float().mean()),
        "mean_utility": float(utility.mean()),
        "mean_cost": float(cost.mean()),
        "total_utility_per_episode": float(utility.sum(-1).mean()),
        "total_cost_per_episode": float(cost.sum(-1).mean()),
    }


def run_seed(seed: int, epochs: int, n_train: int, n_eval: int,
             checkpoint_dir: Path | None = None) -> dict:
    cfg = ControlConfig()
    train_batch = make_episodes(cfg, n_train, seed=seed + 1000)
    eval_batch = make_episodes(cfg, n_eval, seed=seed + 2000)
    model = build_control_model(seed)
    train_cfg = ControlTrainConfig(
        epochs=epochs, batch_size=64, seed=seed,
        checkpoint=str(checkpoint_dir / f"b5_control_s{seed}.pt") if checkpoint_dir else None)
    history, seconds = train_control(
        model, train_batch, train_cfg,
        TrainConfig(hidden=128, layers=2, epochs=epochs, seed=seed))

    open_loop = evaluate_control(model, eval_batch)
    closed_loop = simulate_model(model, eval_batch, cfg)
    torch.manual_seed(seed + 3000)
    baselines = {name: simulate_policy(eval_batch, cfg, name)
                 for name in ("oracle", "need_match", "always_max", "always_wait", "random")}
    open_baselines = {name: evaluate_baseline_open_loop(eval_batch, name, cfg)
                      for name in ("oracle", "need_match", "always_max", "always_wait")}
    return {
        "seed": seed,
        "params": model.param_count,
        "train_seconds": seconds,
        "final_loss": history["loss"][-1],
        "final_action_loss": history["action_loss"][-1],
        "final_need_loss": history["need_loss"][-1],
        "final_confidence_loss": history["confidence_loss"][-1],
        "open_loop": open_loop,
        "closed_loop": closed_loop,
        "baselines_closed_loop": baselines,
        "baselines_open_loop": open_baselines,
        "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
    }


def summarise(runs: list[dict]) -> dict:
    def mean(values):
        return statistics.mean(values)

    def std(values):
        return statistics.pstdev(values) if len(values) > 1 else 0.0

    out = {"seeds": len(runs)}
    for arm in ("open_loop", "closed_loop"):
        for metric in ("action_accuracy", "mean_utility", "mean_cost",
                       "total_utility_per_episode", "total_cost_per_episode",
                       "infeasible_rate", "confidence_brier", "confidence_ece",
                       "expected_cost_mae"):
            if metric in runs[0][arm]:
                values = [r[arm][metric] for r in runs]
                out[f"{arm}_{metric}_mean"] = mean(values)
                out[f"{arm}_{metric}_std"] = std(values)
    for name in ("oracle", "need_match", "always_max", "always_wait", "random"):
        for metric in ("action_accuracy", "mean_utility", "mean_cost",
                       "total_utility_per_episode", "total_cost_per_episode",
                       "infeasible_rate"):
            values = [r["baselines_closed_loop"][name][metric] for r in runs]
            out[f"{name}_{metric}_mean"] = mean(values)
            out[f"{name}_{metric}_std"] = std(values)
    out["model_beats_always_max_utility"] = bool(
        out["closed_loop_total_utility_per_episode_mean"]
        > out["always_max_total_utility_per_episode_mean"])
    out["model_beats_need_match_utility"] = bool(
        out["closed_loop_total_utility_per_episode_mean"]
        > out["need_match_total_utility_per_episode_mean"])
    out["model_beats_random_utility"] = bool(
        out["closed_loop_total_utility_per_episode_mean"]
        > out["random_total_utility_per_episode_mean"])
    out["model_not_above_oracle"] = bool(
        out["closed_loop_total_utility_per_episode_mean"]
        <= out["oracle_total_utility_per_episode_mean"] + 1e-9)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--train-episodes", type=int, default=4096)
    parser.add_argument("--eval-episodes", type=int, default=512)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    epochs, n_train, n_eval = args.epochs, args.train_episodes, args.eval_episodes
    if args.quick:
        seeds, epochs, n_train, n_eval = seeds[:1], 2, 512, 128

    checkpoint_dir = ROOT / "checkpoints" / "b5"
    if not args.quick:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    runs = [run_seed(s, epochs, n_train, n_eval,
                     None if args.quick else checkpoint_dir) for s in seeds]
    summary = summarise(runs)
    out = {
        "experiment": "B5 need and resource control",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "quick": args.quick,
        "warning": "smoke run only; not a result" if args.quick else None,
        "hypotheses": {
            "H-B5": "learned action selection beats always-max, need-match, wait and random",
            "H-CONF": "confidence tracks whether the selected action is optimal",
            "H-BUDGET": "unaffordable actions are masked and the raw violation rate is reported",
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": "cpu",
            "threads": torch.get_num_threads(),
            "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
        },
        "task": {
            "needs": list(NEEDS),
            "actions": list(ACTIONS),
            "action_costs": list(ACTION_COSTS),
            "episode_len": ControlConfig().episode_len,
            "max_budget": ControlConfig().max_budget,
            "initial_budgets": list(ControlConfig().initial_budgets),
            "recovery": ControlConfig().recovery,
            "oracle": "highest-utility action whose cost fits the current budget",
        },
        "training": {"seeds": seeds, "epochs": epochs, "train_episodes": n_train,
                     "eval_episodes": n_eval, "hidden": 128, "layers": 2,
                     "batch_size": 64,
                     "train_seconds_mean": statistics.mean(r["train_seconds"] for r in runs),
                     "train_seconds_total": sum(r["train_seconds"] for r in runs)},
        "runs": runs,
        "summary": summary,
        "limits": [
            "synthetic supervised imitation of a known oracle, not reinforcement learning",
            "the need and budget are observed, so this does not test latent need inference",
            "cost prediction is derived from action probabilities, not a dedicated cost head",
            "three seeds; CPU timing is noisy",
        ],
        "elapsed_seconds": time.perf_counter() - started,
    }
    results_dir = ROOT / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / ("b5_control_quick.json" if args.quick else "b5_control.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
