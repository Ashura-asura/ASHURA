"""B6 independent validation: fixed, recurrent, fast-memory and gated-memory arms.

All arms are trained only on the eight old permutation rules and evaluated on eight disjoint
held-out rules. The task is the B1 study/test walk: a study walk exposes most transitions of a
held-out rule, then a separate test walk from the same rule measures transfer.

Arms
----
fixed           non-recurrent in-context MLP over the study + test prefix; no adaptation.
recurrent       GRU trained on old rules, frozen for held-out rules.
fast_memory     GRU + one token-keyed fast memory, reset before every held-out episode.
gated_memory    GRU + per-rule TaskScopedMemory, kept across task switches.

The fast-memory arm is the B1 operating mode (reset at task boundaries). The gated arm is the
B3 mechanism (external task ID). The revisit phase evaluates each held-out test walk again
without a new study walk: task-scoped reset cannot help, while per-rule memory can.

Run from BrainSim/:
    python -m experiments.b6_validation
    python -m experiments.b6_validation --quick
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

from brainsim.core.fixed_baseline import FixedEpisodeMLP
from brainsim.environment.sequence_tasks import (SequenceConfig, adaptation_episodes,
                                                 make_rules, training_sequences,
                                                 validation_sequences)
from brainsim.learning.episode_train import (evaluate_fixed_episode, make_episode_pairs,
                                             train_fixed_episode)
from brainsim.learning.train import (TrainConfig, build_model, sequence_accuracy,
                                     sequence_logits, train_offline)
from brainsim.memory.fast_memory import FastAssociativeMemory, FastMemoryConfig
from brainsim.memory.gated_memory import GatedMemoryConfig, TaskScopedMemory

ROOT = Path(__file__).resolve().parent.parent


def _accuracy(probabilities: torch.Tensor, tests: torch.Tensor) -> dict:
    """probabilities/logits: (N, T, vocab); tests: (N, T+1) -> token and full recall."""
    targets = tests[:, 1:]
    preds = probabilities.argmax(-1)
    return {
        "token_accuracy": float((preds == targets).float().mean()),
        "full_recall_accuracy": float((preds == targets).all(dim=1).float().mean()),
    }


def _transitions(sequence: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    keys = sequence[:-1]
    return keys, sequence[1:]


def _fast_memory_arm(model, episodes, test_logits: torch.Tensor) -> dict:
    memory = FastAssociativeMemory(FastMemoryConfig(vocab=model.cfg.vocab, key_mode="token"))
    adapted = []
    for i, episode in enumerate(episodes):
        memory.reset()
        keys, values = _transitions(episode.study)
        memory.update(keys, values)
        keys, _ = _transitions(episode.test)
        adapted.append(_accuracy(memory.blend(test_logits[i], keys), episode.test.unsqueeze(0)))
    # The safe B1 mode resets at a task boundary; a revisit therefore has no task memory.
    memory.reset()
    revisit = [_accuracy(test_logits[i], episode.test.unsqueeze(0))
               for i, episode in enumerate(episodes)]
    return {
        "test": {k: statistics.mean(r[k] for r in adapted) for k in adapted[0]},
        "revisit": {k: statistics.mean(r[k] for r in revisit) for k in revisit[0]},
        "memory_bytes": memory.size_bytes,
        "memory_rows": memory.cfg.n_rows,
    }


def _gated_memory_arm(model, episodes, test_logits: torch.Tensor) -> dict:
    memory = TaskScopedMemory(GatedMemoryConfig(
        vocab=model.cfg.vocab, key_mode="token", max_tasks=32, blend=0.9))
    for episode in episodes:
        keys, values = _transitions(episode.study)
        task = f"rule{episode.rule_id}"
        for key, value in zip(keys.tolist(), values.tolist()):
            memory.update(task, key, value, verified=True)
    adapted, revisit = [], []
    for i, episode in enumerate(episodes):
        keys, _ = _transitions(episode.test)
        task = f"rule{episode.rule_id}"
        adapted.append(_accuracy(memory.blend(task, test_logits[i], keys),
                                 episode.test.unsqueeze(0)))
    # No new study walks: a correct per-rule memory should reproduce the adapted accuracy.
    for i, episode in enumerate(episodes):
        keys, _ = _transitions(episode.test)
        task = f"rule{episode.rule_id}"
        revisit.append(_accuracy(memory.blend(task, test_logits[i], keys),
                                 episode.test.unsqueeze(0)))
    return {
        "test": {k: statistics.mean(r[k] for r in adapted) for k in adapted[0]},
        "revisit": {k: statistics.mean(r[k] for r in revisit) for k in revisit[0]},
        "retention_gap": (statistics.mean(r["token_accuracy"] for r in adapted)
                          - statistics.mean(r["token_accuracy"] for r in revisit)),
        "memory_bytes": memory.size_bytes,
        "tasks": memory.task_count,
    }


def run_seed(seed: int, epochs: int, fixed_epochs: int, episodes_per_rule: int) -> dict:
    cfg = SequenceConfig(seed=seed, episodes_per_rule=episodes_per_rule)
    rules = make_rules(cfg)
    old_train = training_sequences(cfg, rules)
    old_val = validation_sequences(cfg, rules)
    train_cfg = TrainConfig(hidden=128, epochs=epochs, batch_size=32, seed=seed)
    gru = build_model(cfg.vocab, train_cfg)
    gru_history, gru_seconds = train_offline(gru, old_train, train_cfg, val_tokens=old_val)

    train_study, train_test = make_episode_pairs(
        rules.train, 32, cfg.study_len, cfg.test_len, seed + 10)
    torch.manual_seed(seed)
    fixed = FixedEpisodeMLP(cfg.vocab, cfg.study_len, cfg.test_len, hidden=220)
    fixed_history, fixed_seconds = train_fixed_episode(
        fixed, train_study, train_test, epochs=fixed_epochs, seed=seed)

    episodes = adaptation_episodes(cfg, rules)
    study_tokens = torch.stack([e.study for e in episodes])
    test_tokens = torch.stack([e.test for e in episodes])
    test_logits = sequence_logits(gru, test_tokens)

    fixed_metrics = evaluate_fixed_episode(fixed, study_tokens, test_tokens)
    recurrent_metrics = _accuracy(test_logits, test_tokens)
    fast = _fast_memory_arm(gru, episodes, test_logits)
    gated = _gated_memory_arm(gru, episodes, test_logits)

    return {
        "seed": seed,
        "params": {"gru": gru.param_count, "fixed": fixed.param_count},
        "train_seconds": {"gru": gru_seconds, "fixed": fixed_seconds},
        "final_loss": {"gru": gru_history["loss"][-1],
                       "fixed": fixed_history["loss"][-1]},
        "train_rule_accuracy": sequence_accuracy(gru, old_val),
        "arms": {
            "fixed": fixed_metrics,
            "recurrent": recurrent_metrics,
            "fast_memory": fast,
            "gated_memory": gated,
        },
        "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
    }


def summarise(runs: list[dict]) -> dict:
    def mean(values):
        return statistics.mean(values)

    def std(values):
        return statistics.pstdev(values) if len(values) > 1 else 0.0

    out = {"seeds": len(runs)}
    for arm in ("fixed", "recurrent"):
        for metric in ("token_accuracy", "full_recall_accuracy"):
            values = [r["arms"][arm][metric] for r in runs]
            out[f"{arm}_{metric}_mean"] = mean(values)
            out[f"{arm}_{metric}_std"] = std(values)
    for arm in ("fast_memory", "gated_memory"):
        for phase in ("test", "revisit"):
            for metric in ("token_accuracy", "full_recall_accuracy"):
                values = [r["arms"][arm][phase][metric] for r in runs]
                out[f"{arm}_{phase}_{metric}_mean"] = mean(values)
                out[f"{arm}_{phase}_{metric}_std"] = std(values)
    out["gated_retention_gap_mean"] = mean(r["arms"]["gated_memory"]["retention_gap"]
                                           for r in runs)
    for key in ("gru", "fixed"):
        out[f"params_{key}"] = runs[0]["params"][key]
        out[f"train_seconds_{key}_mean"] = mean(r["train_seconds"][key] for r in runs)
    out["memory_bytes_fast_mean"] = mean(r["arms"]["fast_memory"]["memory_bytes"] for r in runs)
    out["memory_bytes_gated_mean"] = mean(r["arms"]["gated_memory"]["memory_bytes"] for r in runs)
    out["gated_beats_recurrent_revisit"] = bool(
        out["gated_memory_revisit_token_accuracy_mean"]
        > out["recurrent_token_accuracy_mean"] + 0.10)
    out["gated_beats_fast_revisit"] = bool(
        out["gated_memory_revisit_token_accuracy_mean"]
        > out["fast_memory_revisit_token_accuracy_mean"] + 0.10)
    out["fixed_beats_frozen_recurrent"] = bool(
        out["fixed_token_accuracy_mean"] > out["recurrent_token_accuracy_mean"] + 0.05)
    out["gated_beats_fixed"] = bool(
        out["gated_memory_test_token_accuracy_mean"] > out["fixed_token_accuracy_mean"] + 0.05)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--fixed-epochs", type=int, default=30)
    parser.add_argument("--episodes-per-rule", type=int, default=8)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    epochs, fixed_epochs, episodes_per_rule = (args.epochs, args.fixed_epochs,
                                               args.episodes_per_rule)
    if args.quick:
        seeds = seeds[:1]
        epochs, fixed_epochs, episodes_per_rule = 2, 2, 2

    started = time.perf_counter()
    runs = [run_seed(s, epochs, fixed_epochs, episodes_per_rule) for s in seeds]
    summary = summarise(runs)
    out = {
        "experiment": "B6 independent held-out validation",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "quick": args.quick,
        "warning": "smoke run only; not a result" if args.quick else None,
        "hypothesis": (
            "On disjoint held-out permutation rules, a fixed in-context baseline and a frozen "
            "GRU are weaker than fast memory; task-scoped memory retains across task switches."
        ),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": "cpu",
            "threads": torch.get_num_threads(),
            "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
        },
        "task": {
            "vocab": 16,
            "train_rules": 8,
            "heldout_rules": 8,
            "study_len": 12,
            "test_len": 16,
            "episodes_per_rule": episodes_per_rule,
            "fixed_window": "study walk + test prefix, no recurrence or memory",
        },
        "training": {"seeds": seeds, "epochs": epochs, "fixed_epochs": fixed_epochs,
                     "gru_hidden": 128, "fixed_hidden": 220, "batch_size": 32},
        "runs": runs,
        "summary": summary,
        "limits": [
            "synthetic permutation task with a study/test structure designed by the authors",
            "the gated arm receives the correct rule ID; this is not learned task segmentation",
            "the fixed baseline is a strong in-context baseline but not a language model",
            "three seeds; CPU timing is noisy",
        ],
        "elapsed_seconds": time.perf_counter() - started,
    }
    results_dir = ROOT / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / ("b6_validation_quick.json" if args.quick else "b6_validation.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
