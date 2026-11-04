"""P28: replay ratio and sampling-policy sweep (EXP-006 follow-up).

Same synthetic buffer and NGR policy as EXP-006. Each arm starts from the stable old-capability
memory so acquisition and retention are measured separately. Single seed; report is descriptive.

    python -m experiments.dream.replay_sweep
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from evaluation.ngr import NGRPolicy
from experiments.dream.run import DIM, make_buffer, seed_stable
from learning.dream import DREAM, DreamConfig
from plasticity.slow_weights import CheckpointStore

RATIOS = (0.25, 0.5, 0.75, 1.0)
POLICIES = ("random", "recent")


def run(new_ratio: float, policy: str) -> dict:
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix=f"replay_{policy}_")))
    buffer = make_buffer()
    seed_stable(store, buffer)
    d = DREAM(buffer, store, NGRPolicy("new", min_target_gain=0.05),
              DreamConfig(target="new", dim=DIM, min_train=4, replay=True,
                          new_ratio=new_ratio, replay_policy=policy, initialization="stable"))
    t0 = time.perf_counter()
    r = d.run()
    return {"new_ratio": new_ratio, "policy": policy, "train_n": r.train_n,
            "new": round(r.scores.get("new", 0), 3),
            "old_retention": round(r.scores.get("old", 0), 3),
            "promoted": r.promoted, "seconds": round(time.perf_counter() - t0, 3)}


if __name__ == "__main__":
    rows = [run(ratio, policy) for policy in POLICIES for ratio in RATIOS]
    out = {"experiment": "P28", "hypothesis": "H-DREAM", "n_facts": 20, "dim": DIM, "results": rows}
    print(json.dumps(out, indent=2))
    Path("experiments/dream/replay_sweep.json").write_text(json.dumps(out, indent=2))
