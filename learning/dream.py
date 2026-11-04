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
    initialization: str = "fresh"  # "fresh" | "stable" (consolidation from the stable model)
    answer_vocabulary: tuple[str, ...] | None = None  # fixed before evaluation; default = training values
    cold_start_checkpoint: str | None = None           # independently evaluated baseline when no stable exists
    cold_start_min_target_accuracy: float = 0.5        # separate acceptance criterion for first promotion

    def __post_init__(self) -> None:
        if not 0.0 < self.new_ratio <= 1.0:
            raise ValueError("new_ratio must be in (0, 1]")
        if self.min_train < 1 or self.dim < 1:
            raise ValueError("min_train and dim must be positive")
        if self.initialization not in {"fresh", "stable"}:
            raise ValueError("initialization must be 'fresh' or 'stable'")
        if not 0.0 <= self.cold_start_min_target_accuracy <= 1.0:
            raise ValueError("cold_start_min_target_accuracy must be in [0, 1]")


@dataclass
class DreamResult:
    candidate: str
    promoted: bool
    scores: dict[str, float]
    stable_scores: dict[str, float]
    ngr: NGRResult
    train_n: int
    reasons: list[str]
    initialization: str = "fresh"
    cold_start: bool = False
    vocabulary: tuple[str, ...] = ()


class DREAM:
    def __init__(self, buffer: ReplayBuffer, store: CheckpointStore | None = None,
                 policy: NGRPolicy | None = None, cfg: DreamConfig | None = None):
        self.buffer = buffer
        self.store = store or CheckpointStore()
        self.cfg = cfg or DreamConfig()
        self.policy = policy or NGRPolicy(self.cfg.target)

    # ---- stages -----------------------------------------------------------------------------
    def answer_vocabulary(self) -> tuple[str, ...]:
        """Candidate answers fixed before evaluation (P13).

        By default the vocabulary is derived from the *training* split only; held-out answers can
        never expand the candidate's answer set. A task specification may pass an explicit list.
        """
        if self.cfg.answer_vocabulary is not None:
            vocab = tuple(self.cfg.answer_vocabulary)
        else:
            vocab = tuple(sorted({i.value for i in self.buffer.training_set()}))
        if not vocab:
            raise ValueError("no answer vocabulary: training set is empty")
        return vocab

    def _new_candidate_memory(self) -> AdaptiveMemory:
        cfg = AMemConfig(dim_k=self.cfg.dim, dim_v=self.cfg.dim, seed=self.cfg.seed)
        if self.cfg.initialization == "stable":
            current = self.store.current()
            if current is None:
                raise ValueError("initialization='stable' requires a current stable checkpoint")
            return AdaptiveMemory.load(str(self.store.load(current)), cfg)
        return AdaptiveMemory(cfg)

    def train_candidate(self, items: list[ReplayItem]) -> tuple[AdaptiveMemory, str]:
        mem = self._new_candidate_memory()
        for it in items:
            mem.write(it.key, it.value)
        name = f"candidate_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000}.npz"
        mem.save(str(self.store.root / "candidates" / name))
        return mem, name

    def score(self, mem: AdaptiveMemory, items: list[ReplayItem],
              vocabulary: tuple[str, ...] | None = None) -> dict[str, float]:
        if not items:
            return {}
        candidates = list(vocabulary if vocabulary is not None else self.answer_vocabulary())
        per: dict[str, list[bool]] = {}
        for it in items:
            prediction, _ = mem.recall(it.key, candidates)
            per.setdefault(it.category, []).append(prediction == it.value)
        return {c: sum(v) / len(v) for c, v in per.items()}

    def _baseline_scores(self, items: list[ReplayItem]) -> tuple[dict[str, float], bool]:
        """Return (scores, cold_start). A missing stable checkpoint is never replaced by zeros."""
        current = self.store.current()
        if current is None:
            if not self.cfg.cold_start_checkpoint:
                raise ValueError("no stable checkpoint and no independently evaluated cold-start baseline; "
                                 "refusing to promote against a fake zero baseline")
            baseline = AdaptiveMemory.load(
                self.cfg.cold_start_checkpoint,
                AMemConfig(dim_k=self.cfg.dim, dim_v=self.cfg.dim, seed=self.cfg.seed))
            return self.score(baseline, items), True
        mem = AdaptiveMemory.load(str(self.store.load(current)),
                                  AMemConfig(dim_k=self.cfg.dim, dim_v=self.cfg.dim, seed=self.cfg.seed))
        return self.score(mem, items), False

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

        vocabulary = self.answer_vocabulary()
        mem, name = self.train_candidate(train)
        scores = self.score(mem, heldout, vocabulary)
        stable, cold_start = self._baseline_scores(heldout)
        ngr = evaluate(self.policy, stable, scores)
        reasons = list(ngr.reasons)

        # First-time initialization has a separate, explicit acceptance criterion (P14). It is
        # evaluated against a real baseline artifact, never against fabricated zero scores.
        if cold_start:
            target_score = scores.get(self.cfg.target)
            if target_score is None or target_score < self.cfg.cold_start_min_target_accuracy:
                reasons.append(f"cold-start target {self.cfg.target!r} score "
                               f"{target_score!r} < required {self.cfg.cold_start_min_target_accuracy}")
                ngr = NGRResult(False, reasons, ngr.deltas)

        missing_answers = sorted({i.value for i in heldout} - set(vocabulary))
        if missing_answers:
            reasons.append(f"held-out answers outside the fixed vocabulary (cannot be predicted): {missing_answers}")

        promoted = ngr.promote
        if promoted:
            self.store.promote(name, ngr)
        else:
            reasons.append("candidate kept in checkpoints/candidates, stable version unchanged")
        result = DreamResult(name, promoted, scores, stable, ngr, len(train), reasons,
                             initialization=self.cfg.initialization, cold_start=cold_start,
                             vocabulary=vocabulary)
        log = self.store.root / "dream_log.jsonl"
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **result.__dict__,
                                "ngr": {"promote": ngr.promote, "reasons": ngr.reasons, "deltas": ngr.deltas}},
                               default=str) + "\n")
        return result
