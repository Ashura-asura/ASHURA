"""DPF fast plasticity (spec 8.1). EXPERIMENTAL.

A temporary associative state that can learn during a task and be reset without touching any
persistent artifact. The base component is never passed in or modified here; this object only owns
its own delta. The first implementation reuses the bounded linear adaptive memory from Phase 4
rather than inventing a second learning rule.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from memory.adaptive_memory import AMemConfig, AdaptiveMemory


@dataclass(frozen=True)
class FastConfig:
    lr: float = 0.6
    max_delta_norm: float = 10.0   # bound on ||delta||; NOT calibrated (see research/failures.md)


class FastWeights:
    """Resettable temporary state: W_effective = W_base + delta. Only delta lives here."""

    def __init__(self, cfg: FastConfig | None = None, mem: AdaptiveMemory | None = None):
        self.cfg = cfg or FastConfig()
        self._mem = mem or AdaptiveMemory(AMemConfig(lr=self.cfg.lr))
        self._writes_since_reset = 0

    @property
    def delta_norm(self) -> float:
        return float(np.linalg.norm(self._mem.M))

    @property
    def writes_since_reset(self) -> int:
        return self._writes_since_reset

    def learn(self, key: str, value: str, passes: int = 1) -> float:
        """One temporary update. Returns surprise. Growth is bounded, never rejected silently."""
        surprise = self._mem.write(key, value, passes)
        self._writes_since_reset += 1
        norm = self.delta_norm
        if norm > self.cfg.max_delta_norm:
            scale = self.cfg.max_delta_norm / norm
            self._mem.M *= scale
            self._mem.S *= scale
        return surprise

    def recall(self, key: str, candidates: list[str], cand_vecs=None) -> tuple[str, float]:
        return self._mem.recall(key, candidates, cand_vecs)

    def candidate_matrix(self, candidates: list[str]):
        return self._mem.candidate_matrix(candidates)

    def reset(self) -> None:
        """Drop every temporary association. Persistent checkpoints are untouched by design."""
        self._mem.reset()
        self._writes_since_reset = 0

    def save(self, path: str) -> None:
        self._mem.save(path)

    @classmethod
    def load(cls, path: str, cfg: FastConfig | None = None) -> "FastWeights":
        c = cfg or FastConfig()
        return cls(c, AdaptiveMemory.load(path, AMemConfig(lr=c.lr)))
