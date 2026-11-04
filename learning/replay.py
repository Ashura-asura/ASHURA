"""DREAM replay buffer (spec 10.1-10.3). EXPERIMENTAL.

Only verified examples enter a training set. Held-out examples are tracked separately and are
never returned for training; adding the same example to both splits is rejected as leakage.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

_TOK = re.compile(r"\w+", re.UNICODE)


def _norm(s: str) -> str:
    return " ".join(_TOK.findall(s.lower()))


@dataclass(frozen=True)
class ReplayItem:
    id: str
    key: str
    value: str
    category: str = "general"
    verified: bool = False
    split: str = "train"          # "train" | "heldout"
    source: str = ""
    difficulty: float = 0.0

    def fingerprint(self) -> tuple[str, str]:
        return _norm(self.key), _norm(self.value)


@dataclass
class ReplayStats:
    added: int = 0
    duplicates: int = 0
    rejected: int = 0


class ReplayBuffer:
    def __init__(self):
        self.items: list[ReplayItem] = []
        self._seen: dict[tuple[str, str], str] = {}
        self.stats = ReplayStats()

    def add(self, item: ReplayItem) -> bool:
        fp = item.fingerprint()
        if fp in self._seen:
            if self._seen[fp] != item.split:
                raise ValueError(f"leakage: {item.id!r} appears in both train and heldout")
            self.stats.duplicates += 1
            return False
        if item.verified is False and item.split == "train":
            self.stats.rejected += 1
            return False
        self._seen[fp] = item.split
        self.items.append(item)
        self.stats.added += 1
        return True

    def training_set(self) -> list[ReplayItem]:
        return [i for i in self.items if i.split == "train" and i.verified]

    def heldout(self, category: str | None = None) -> list[ReplayItem]:
        return [i for i in self.items if i.split == "heldout" and (category is None or i.category == category)]

    def categories(self) -> list[str]:
        return sorted({i.category for i in self.items})

    def replay_set(self, target: str, new_ratio: float = 0.5, seed: int = 0,
                   policy: str = "random") -> list[ReplayItem]:
        """Target examples plus historical examples. Proportions are NOT calibrated (P28)."""
        if not 0.0 < new_ratio <= 1.0:
            raise ValueError("new_ratio must be in (0, 1]")
        if policy not in {"random", "recent"}:
            raise ValueError("policy must be 'random' or 'recent'")
        train = self.training_set()
        new = [i for i in train if i.category == target]
        old = [i for i in train if i.category != target]
        rng = random.Random(seed)
        rng.shuffle(new)
        if policy == "random":
            rng.shuffle(old)
        else:
            old = list(reversed(old))       # most recently added first
        if not new:
            return old
        n_old = 0 if new_ratio >= 1.0 else round(len(new) * (1.0 - new_ratio) / new_ratio)
        return new + old[:n_old]
