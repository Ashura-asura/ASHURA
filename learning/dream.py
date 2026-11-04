"""DREAM - Deferred Replay, Evaluation, Adaptation and Memory (spec 10). EXPERIMENTAL.

The first implementation trains the small NumPy adaptive memory, not Qwen. A candidate is a file;
it reaches `checkpoints/stable/` only through NGR. A rejected candidate stays in `candidates/`.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from evaluation.ngr import NGRPolicy, NGRResult, evaluate
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from plasticity.slow_weights import CheckpointStore

from .replay import ReplayBuffer, ReplayItem


@dataclass(frozen=True)
class DreamConfig:
    target: str = "new"
    dim: int = 128
    min_train: int = 4
    new_ratio: float = 0.5       # target share of the replay set; NOT calibrated
    seed: int = 0
    replay: bool = True          # False = new-only training (baseline for H-DREAM)

    def __post_init__(self) -> None:
        if not 0.0 < self.new_ratio <= 1.0:
            raise ValueError("new_ratio must be in (0, 1]")
        if self.min_train < 1 or self.dim < 1:
            raise ValueError("min_train and dim must be positive")


@dataclass
class DreamResult:
    candidate: str
    promoted: bool
    scores: dict[str, float]
    stable_scores: dict[str, float]
    ngr: NGRResult
    train_n: int
    reasons: list[str]


class DREAM:
    def __init__(self, buffer: ReplayBuffer, store: CheckpointStore | None = None,
                 policy: NGRPolicy | None = None, cfg: DreamConfig | None = None):
        self.buffer = buffer
        self.store = store or CheckpointStore()
        self.cfg = cfg or DreamConfig()
        self.policy = policy or NGRPolicy(self.cfg.target)

    # ---- stages -----------------------------------------------------------------------------
    def train_candidate(self, items: list[ReplayItem]) -> tuple[AdaptiveMemory, str]:
        mem = AdaptiveMemory(AMemConfig(dim_k=self.cfg.dim, dim_v=self.cfg.dim, seed=self.cfg.seed))
        for it in items:
            mem.write(it.key, it.value)
        name = f"candidate_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000}.npz"
        mem.save(str(self.store.root / "candidates" / name))
        return mem, name

    def score(self, mem: AdaptiveMemory, items: list[ReplayItem]) -> dict[str, float]:
        if not items:
            return {}
        candidates = sorted({i.value for i in items})
        per: dict[str, list[bool]] = {}
        for it in items:
            prediction, _ = mem.recall(it.key, candidates)
            per.setdefault(it.category, []).append(prediction == it.value)
        return {c: sum(v) / len(v) for c, v in per.items()}

    def _stable_scores(self, items: list[ReplayItem]) -> dict[str, float]:
        current = self.store.current()
        if current is None:
            return {c: 0.0 for c in {i.category for i in items}}
        mem = AdaptiveMemory.load(str(self.store.load(current)),
                                  AMemConfig(dim_k=self.cfg.dim, dim_v=self.cfg.dim, seed=self.cfg.seed))
        return self.score(mem, items)

    # ---- orchestration ----------------------------------------------------------------------
    def run(self) -> DreamResult:
        if self.cfg.replay:
            train = self.buffer.replay_set(self.cfg.target, self.cfg.new_ratio, self.cfg.seed)
        else:
            train = [i for i in self.buffer.training_set() if i.category == self.cfg.target]
        if len(train) < self.cfg.min_train:
            raise ValueError(f"not enough verified training items: {len(train)} < {self.cfg.min_train}")
        heldout = self.buffer.heldout()
        if not heldout:
            raise ValueError("no held-out items: DREAM refuses to promote without an evaluation set")

        mem, name = self.train_candidate(train)
        scores = self.score(mem, heldout)
        stable = self._stable_scores(heldout)
        ngr = evaluate(self.policy, stable, scores)
        promoted = ngr.promote
        reasons = list(ngr.reasons)
        if promoted:
            self.store.promote(name, ngr)
        else:
            reasons.append("candidate kept in checkpoints/candidates, stable version unchanged")
        result = DreamResult(name, promoted, scores, stable, ngr, len(train), reasons)
        log = self.store.root / "dream_log.jsonl"
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **result.__dict__,
                                "ngr": {"promote": ngr.promote, "reasons": ngr.reasons, "deltas": ngr.deltas}},
                               default=str) + "\n")
        return result
