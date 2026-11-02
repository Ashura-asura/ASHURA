"""B1 + first BrainSim fast-memory experiment (blueprint 3, 4.2 and section 24).

Hypotheses
----------
H-B1: the recurrent core learns the hidden permutation rules it is trained on and predicts
      held-out starts from those rules.
H-FM: after observing a study sequence from an *unseen* rule, an isolated fast associative
      memory improves next-token prediction on a later sequence with the same rule.
H-KEY: context keys (previous, current) reduce interference with previously learned rules
      compared with token-only keys.

Arms
----
frozen : no online adaptation.
token  : fast memory keyed by the current token only.
pair   : fast memory keyed by (previous token, current token).

The model weights are never updated online. Every memory is reset per episode (task-scoped
adaptation) and is also saved/reloaded to test persistence. Retention is reported twice:
while the new-rule memory is still active (interference) and after reset (restoration).

Run from BrainSim/:
    python -m experiments.b1_sequence
    python -m experiments.b1_sequence --quick
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import psutil
import torch

from brainsim.core.encoder import encode
from brainsim.environment.sequence_tasks import (SequenceConfig, adaptation_episodes,
                                                 make_rules, training_sequences,
                                                 validation_sequences)
from brainsim.learning.train import (TrainConfig, build_model, position_accuracy,
                                     sequence_accuracy, sequence_logits, train_offline)
from brainsim.memory.fast_memory import FastAssociativeMemory, FastMemoryConfig

ROOT = Path(__file__).resolve().parent.parent
RETENTION_TOLERANCE = 0.02          # same "no meaningful regression" idea as ASHURA's NGR


def _pair_view(seq: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Transitions (keys, previous keys, values) for a 1-D token sequence."""
    keys = seq[:-1]
    prev = torch.cat([keys[:1], keys[:-1]])
    return keys, prev, seq[1:]


def _pair_view_batch(seq: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    keys = seq[:, :-1]
    prev = torch.cat([keys[:, :1], keys[:, :-1]], dim=1)
    return keys, prev, seq[:, 1:]


def _median_ms(fn, repeats: int = 20, warmup: int = 3) -> float:
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        times.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(times)


@torch.no_grad()
def _state_carry_accuracy(model, episodes) -> float:
    """Control: carry the recurrent state from study into test, with no memory update."""
    model.eval()
    study = torch.stack([e.study[:-1] for e in episodes])
    test = torch.stack([e.test[:-1] for e in episodes])
    values = torch.stack([e.test[1:] for e in episodes])
    out = model(encode(study, model.cfg.vocab))
    carried = model(encode(test, model.cfg.vocab), out.state)
    return float((carried.logits.argmax(-1) == values).float().mean())


def _memory_arm(mode: str, episodes, test_logits: torch.Tensor, vocab: int,
                tmpdir: Path) -> dict:
    """Adapt on each study sequence, evaluate the related test sequence, save/load."""
    cfg = FastMemoryConfig(vocab=vocab, key_mode=mode)
    memory = FastAssociativeMemory(cfg)
    adapted, persisted, seen_fractions = [], [], []

    for i, episode in enumerate(episodes):
        memory.reset()
        keys, prev, values = _pair_view(episode.study)
        memory.update(keys, values, prev=prev if mode == "pair" else None)

        keys, prev, values = _pair_view(episode.test)
        kwargs = {"prev": prev} if mode == "pair" else {}
        probs = memory.blend(test_logits[i], keys, **kwargs)
        adapted.append(float((probs.argmax(-1) == values).float().mean()))
        seen_fractions.append(float(memory.seen(keys, **kwargs).float().mean()))

        path = tmpdir / f"{mode}_{i}.pt"
        memory.save(path)
        loaded = FastAssociativeMemory.load(path)
        probs = loaded.blend(test_logits[i], keys, **kwargs)
        persisted.append(float((probs.argmax(-1) == values).float().mean()))

    # Retention: keep the memory from the first held-out episode for the caller.
    memory.reset()
    episode = episodes[0]
    keys, prev, values = _pair_view(episode.study)
    memory.update(keys, values, prev=prev if mode == "pair" else None)

    return {
        "adapted_accuracy": statistics.mean(adapted),
        "persisted_accuracy": statistics.mean(persisted),
        "seen_fraction": statistics.mean(seen_fractions),
        "adapted_by_episode": adapted,
        "persisted_by_episode": persisted,
        "memory_bytes": memory.size_bytes,
        "memory_rows": cfg.n_rows,
        "memory": memory,             # returned for the retention/latency steps
    }


def _retention(memory: FastAssociativeMemory, mode: str, val_tokens: torch.Tensor,
               old_logits: torch.Tensor, vocab: int) -> dict:
    keys, prev, values = _pair_view_batch(val_tokens)
    kwargs = {"prev": prev} if mode == "pair" else {}
    probs = memory.blend(old_logits.reshape(-1, vocab), keys.reshape(-1), **kwargs)
    active = float((probs.argmax(-1) == values.reshape(-1)).float().mean())
    memory.reset()
    reset = float((old_logits.reshape(-1, vocab).argmax(-1) == values.reshape(-1)).float().mean())
    return {"old_active_accuracy": active, "old_reset_accuracy": reset,
            "retention_drop": reset - active}


def run_one(size: int, seed: int, epochs: int, checkpoint_dir: Path) -> dict:
    seq_cfg = SequenceConfig(seed=seed)
    rules = make_rules(seq_cfg)
    train_tokens = training_sequences(seq_cfg, rules)
    val_tokens = validation_sequences(seq_cfg, rules)
    episodes = adaptation_episodes(seq_cfg, rules)

    train_cfg = TrainConfig(hidden=size, epochs=epochs, batch_size=32, seed=seed,
                            checkpoint=str(checkpoint_dir / f"b1_h{size}_s{seed}.pt"))
    model = build_model(seq_cfg.vocab, train_cfg)
    history, train_seconds = train_offline(model, train_tokens, train_cfg,
                                           val_tokens=val_tokens)
    train_rule_accuracy = sequence_accuracy(model, val_tokens)
    positions = position_accuracy(model, val_tokens)

    test_tokens = torch.stack([e.test for e in episodes])
    test_logits = sequence_logits(model, test_tokens)
    test_values = test_tokens[:, 1:]
    frozen = float((test_logits.argmax(-1) == test_values).float().mean())
    state_carry = _state_carry_accuracy(model, episodes)

    old_logits = sequence_logits(model, val_tokens)
    old_values = val_tokens[:, 1:]
    old_baseline = float((old_logits.argmax(-1) == old_values).float().mean())

    arms = {}
    with tempfile.TemporaryDirectory(prefix="brainsim_b1_") as tmp:
        tmpdir = Path(tmp)
        for mode in ("token", "pair"):
            arm = _memory_arm(mode, episodes, test_logits, seq_cfg.vocab, tmpdir)
            memory = arm.pop("memory")
            arm.update(_retention(memory, mode, val_tokens, old_logits, seq_cfg.vocab))
            arm["tolerance"] = RETENTION_TOLERANCE
            arm["within_tolerance"] = bool(arm["retention_drop"] <= RETENTION_TOLERANCE)

            # Latency: one related test sequence, memory re-adapted to that episode.
            episode = episodes[0]
            keys, prev, _ = _pair_view(episode.test)
            kwargs = {"prev": prev} if mode == "pair" else {}
            single_logits = sequence_logits(model, episode.test.unsqueeze(0))[0]
            memory.reset()
            k, p, v = _pair_view(episode.study)
            memory.update(k, v, prev=p if mode == "pair" else None)

            def infer():
                probs = memory.blend(single_logits, keys, **kwargs)
                return probs.argmax(-1)

            fresh = FastAssociativeMemory(FastMemoryConfig(vocab=seq_cfg.vocab, key_mode=mode))

            def adapt():
                fresh.reset()
                k, p, v = _pair_view(episode.study)
                fresh.update(k, v, prev=p if mode == "pair" else None)

            arm["inference_p50_ms"] = _median_ms(infer)
            arm["adaptation_p50_ms"] = _median_ms(adapt)
            arms[mode] = arm

    return {
        "hidden": size,
        "seed": seed,
        "epochs": epochs,
        "params": model.param_count,
        "train_rule_accuracy": train_rule_accuracy,
        "position_accuracy_train_rules": positions,
        "heldout_frozen_accuracy": frozen,
        "heldout_state_carry_accuracy": state_carry,
        "heldout_frozen_by_position": [float(v) for v in
                                      (test_logits.argmax(-1) == test_values).float().mean(0)],
        "old_rule_accuracy": old_baseline,
        "final_loss": history["loss"][-1],
        "train_seconds": train_seconds,
        "rss_mb": psutil.Process().memory_info().rss / (1024 * 1024),
        "arms": arms,
    }


def summarise(runs: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for run in runs:
        groups.setdefault(run["hidden"], []).append(run)
    out = []
    for size, group in sorted(groups.items()):
        def mean(fn):
            return statistics.mean(fn(r) for r in group)

        def spread(fn):
            return statistics.pstdev(fn(r) for r in group) if len(group) > 1 else 0.0

        row = {
            "hidden": size,
            "seeds": len(group),
            "params": group[0]["params"],
            "train_rule_accuracy_mean": mean(lambda r: r["train_rule_accuracy"]),
            "train_rule_accuracy_std": spread(lambda r: r["train_rule_accuracy"]),
            "frozen_accuracy_mean": mean(lambda r: r["heldout_frozen_accuracy"]),
            "frozen_accuracy_std": spread(lambda r: r["heldout_frozen_accuracy"]),
            "state_carry_accuracy_mean": mean(lambda r: r["heldout_state_carry_accuracy"]),
            "state_carry_accuracy_std": spread(lambda r: r["heldout_state_carry_accuracy"]),
            "train_seconds_mean": mean(lambda r: r["train_seconds"]),
            "train_seconds_median": statistics.median(r["train_seconds"] for r in group),
            "rss_mb_mean": mean(lambda r: r["rss_mb"]),
            "rss_mb_median": statistics.median(r["rss_mb"] for r in group),
        }
        for mode in ("token", "pair"):
            row[f"{mode}_adapted_mean"] = mean(lambda r: r["arms"][mode]["adapted_accuracy"])
            row[f"{mode}_adapted_std"] = spread(lambda r: r["arms"][mode]["adapted_accuracy"])
            row[f"{mode}_persisted_mean"] = mean(lambda r: r["arms"][mode]["persisted_accuracy"])
            row[f"{mode}_old_active_mean"] = mean(lambda r: r["arms"][mode]["old_active_accuracy"])
            row[f"{mode}_retention_drop_mean"] = mean(lambda r: r["arms"][mode]["retention_drop"])
            row[f"{mode}_within_tolerance_mean"] = mean(
                lambda r: 1.0 if r["arms"][mode]["within_tolerance"] else 0.0)
            row[f"{mode}_inference_p50_ms_mean"] = mean(
                lambda r: r["arms"][mode]["inference_p50_ms"])
        out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="128,384", help="comma-separated hidden sizes")
    ap.add_argument("--seeds", default="0,1,2", help="comma-separated seeds")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--quick", action="store_true", help="tiny smoke run (not a result)")
    args = ap.parse_args()
    sizes = [int(x) for x in args.sizes.split(",") if x]
    seeds = [int(x) for x in args.seeds.split(",") if x]
    if args.quick:
        sizes, seeds, args.epochs = [32], [0], 2

    checkpoint_dir = ROOT / "checkpoints"
    checkpoint_dir.mkdir(exist_ok=True)
    runs = []
    for size in sizes:
        for seed in seeds:
            print(f"[run] hidden={size} seed={seed} epochs={args.epochs}", flush=True)
            run = run_one(size, seed, args.epochs, checkpoint_dir)
            runs.append(run)
            print(f"  train_rules={run['train_rule_accuracy']:.3f} "
                  f"frozen={run['heldout_frozen_accuracy']:.3f} "
                  f"carry={run['heldout_state_carry_accuracy']:.3f} "
                  f"token={run['arms']['token']['adapted_accuracy']:.3f} "
                  f"pair={run['arms']['pair']['adapted_accuracy']:.3f} "
                  f"token_old={run['arms']['token']['old_active_accuracy']:.3f} "
                  f"pair_old={run['arms']['pair']['old_active_accuracy']:.3f} "
                  f"train_s={run['train_seconds']:.1f}", flush=True)

    summary = summarise(runs)
    out = {
        "experiment": "BrainSim-B1 + first fast-memory experiment",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hypotheses": {
            "H-B1": "the recurrent core learns training rules and predicts held-out starts",
            "H-FM": "fast memory improves prediction on a later sequence from an unseen rule",
            "H-KEY": "context keys reduce interference with old rules vs token-only keys",
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
        "task": asdict(SequenceConfig()),
        "training": {"sizes": sizes, "seeds": seeds, "epochs": args.epochs,
                     "retention_tolerance": RETENTION_TOLERANCE},
        "runs": runs,
        "summary": summary,
        "quick": args.quick,
    }
    results_dir = ROOT / "experiments" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / ("b1_sequence_quick.json" if args.quick else "b1_sequence.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\nsummary")
    for row in summary:
        print(f"  hidden={row['hidden']} params={row['params']:,} "
              f"train_rules={row['train_rule_accuracy_mean']:.3f} "
              f"frozen={row['frozen_accuracy_mean']:.3f} "
              f"carry={row['state_carry_accuracy_mean']:.3f} "
              f"token={row['token_adapted_mean']:.3f} "
              f"pair={row['pair_adapted_mean']:.3f} "
              f"token_old={row['token_old_active_mean']:.3f} "
              f"pair_old={row['pair_old_active_mean']:.3f} "
              f"pair_drop={row['pair_retention_drop_mean']:.3f}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
