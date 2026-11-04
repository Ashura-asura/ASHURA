"""EXP-006: DREAM consolidation arms (H-DREAM). EXPERIMENTAL / synthetic.

Four explicit arms, as required by Phase 1 P12:
  stable + new      candidate starts from the stable memory, trains only on the new capability
  stable + replay   candidate starts from stable, trains on new + historical examples
  fresh + new       candidate starts from scratch, trains only on the new capability
  fresh + replay    candidate starts from scratch, trains on new + historical examples

Every arm is evaluated on the same held-out set and passed through the same NGR policy. The answer
vocabulary comes from the training split only (P13), and every arm has a real, independently
evaluated stable baseline (P14).
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from evaluation.ngr import NGRPolicy, NGRResult
from learning.dream import DREAM, DreamConfig
from learning.replay import ReplayBuffer, ReplayItem
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from plasticity.slow_weights import CheckpointStore

N = 20
DIM = 256


def make_buffer() -> ReplayBuffer:
    b = ReplayBuffer()
    for i in range(N):
        b.add(ReplayItem(f"old-{i}", f"entity{i} old", f"old-{i}", category="old", verified=True))
        b.add(ReplayItem(f"old-h-{i}", f"old entity{i}", f"old-{i}", category="old", verified=True, split="heldout"))
        b.add(ReplayItem(f"new-{i}", f"entity{i} new", f"new-{i}", category="new", verified=True))
        b.add(ReplayItem(f"new-h-{i}", f"new entity{i}", f"new-{i}", category="new", verified=True, split="heldout"))
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


def run_arm(initialization: str, replay: bool) -> dict:
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix=f"dream_{initialization}_")))
    buffer = make_buffer()
    seed_stable(store, buffer)
    d = DREAM(buffer, store, NGRPolicy("new", min_target_gain=0.05),
              DreamConfig(target="new", dim=DIM, min_train=4, replay=replay,
                          initialization=initialization))
    t0 = time.perf_counter()
    r = d.run()
    return {
        "new": round(r.scores.get("new", 0), 3),
        "old_retention": round(r.scores.get("old", 0), 3),
        "stable_new": round(r.stable_scores.get("new", 0), 3),
        "stable_old": round(r.stable_scores.get("old", 0), 3),
        "promoted": r.promoted,
        "ngr": r.ngr.reasons,
        "train_n": r.train_n,
        "initialization": r.initialization,
        "vocabulary_size": len(r.vocabulary),
        "seconds": round(time.perf_counter() - t0, 3),
    }


def main() -> None:
    rows = {}
    for initialization in ("stable", "fresh"):
        for replay in (False, True):
            label = f"{initialization}_{'replay' if replay else 'new'}"
            rows[label] = run_arm(initialization, replay)
    out = {"experiment": "EXP-006", "hypothesis": "H-DREAM", "n_facts": N, "dim": DIM, "results": rows}
    print(json.dumps(out, indent=2))
    Path("experiments/dream").mkdir(exist_ok=True)
    Path("experiments/dream/results.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
