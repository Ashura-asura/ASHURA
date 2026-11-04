"""Bounded replay buffer for B4 slow consolidation (blueprint B4).

The buffer stores only token sequences, never gradients. A caller decides what is admitted;
this module only bounds memory and samples deterministically for a given seed.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class ReplayConfig:
    capacity: int = 512
    seed: int = 0

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be >= 1")


class ReplayBuffer:
    def __init__(self, cfg: ReplayConfig | None = None):
        self.cfg = cfg or ReplayConfig()
        self._rows: list[torch.Tensor] = []

    def __len__(self) -> int:
        return len(self._rows)

    def add(self, tokens: torch.Tensor) -> None:
        """Append sequences; oldest rows are evicted when capacity is exceeded."""
        tokens = torch.as_tensor(tokens, dtype=torch.long)
        if tokens.ndim != 2:
            raise ValueError("tokens must be (N, L)")
        for row in tokens:
            self._rows.append(row.clone())
        if len(self._rows) > self.cfg.capacity:
            self._rows = self._rows[-self.cfg.capacity:]

    def sample(self, n: int, generator: torch.Generator | None = None) -> torch.Tensor:
        if not self._rows:
            raise ValueError("cannot sample from an empty replay buffer")
        if n < 1:
            raise ValueError("n must be >= 1")
        idx = torch.randint(len(self._rows), (n,), generator=generator)
        return torch.stack([self._rows[i] for i in idx.tolist()])

    def clear(self) -> None:
        self._rows.clear()
