"""Synthetic permutation-sequence environments (blueprint 4.1 and the first experiment).

Each episode hides a single rule: a permutation of the vocabulary with exactly one cycle.
The environment emits a walk ``x_{t+1} = rule[x_t]``. Training rules are visible during
offline training; held-out rules are never trained on. A held-out episode has two related
parts: a short study sequence (the fast-memory experience) and a later test sequence with
the same hidden rule.

Nothing here calls a language model. Everything is generated locally and deterministically
from a seed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch


@dataclass(frozen=True)
class SequenceConfig:
    vocab: int = 16
    train_rules: int = 8
    heldout_rules: int = 8
    starts_per_rule: int = 32          # offline training sequences per rule
    val_starts_per_rule: int = 16      # held-out sequences from *training* rules
    episodes_per_rule: int = 4         # adaptation episodes per held-out rule
    seq_len: int = 24                  # tokens per offline-training sequence
    study_len: int = 12                # observed transitions before the adaptation test
    test_len: int = 16                 # transitions predicted on the related sequence
    seed: int = 0

    def __post_init__(self) -> None:
        if self.vocab < 2:
            raise ValueError("vocab must be >= 2")
        if self.train_rules < 1 or self.heldout_rules < 1:
            raise ValueError("need at least one training and one held-out rule")
        if self.study_len < 1 or self.test_len < 1 or self.seq_len < 2:
            raise ValueError("sequence lengths must be positive")


@dataclass(frozen=True)
class RuleSet:
    train: tuple[tuple[int, ...], ...]
    heldout: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        if set(self.train) & set(self.heldout):
            raise ValueError("a rule cannot be both trained and held out")


@dataclass(frozen=True)
class Episode:
    rule_id: int
    study: torch.Tensor        # (study_len + 1,) tokens
    test: torch.Tensor         # (test_len + 1,) tokens
    split: str = "heldout"


def single_cycle_permutation(vocab: int, rng: np.random.Generator) -> tuple[int, ...]:
    """Return a permutation of 0..vocab-1 with one cycle.

    A random shuffle is interpreted as the cycle order. Using one cycle means a walk of
    ``vocab`` transitions visits every token, so a study prefix exercises a known set of
    transitions rather than an arbitrary subset of a multi-cycle permutation.
    """
    order = rng.permutation(vocab)
    perm = np.empty(vocab, dtype=np.int64)
    perm[order] = np.roll(order, -1)
    return tuple(int(x) for x in perm)


def make_rules(cfg: SequenceConfig) -> RuleSet:
    """Sample disjoint training and held-out rules deterministically from ``cfg.seed``."""
    rng = np.random.default_rng(cfg.seed)
    train: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    while len(train) < cfg.train_rules:
        rule = single_cycle_permutation(cfg.vocab, rng)
        if rule not in seen:
            seen.add(rule)
            train.append(rule)
    heldout: list[tuple[int, ...]] = []
    while len(heldout) < cfg.heldout_rules:
        rule = single_cycle_permutation(cfg.vocab, rng)
        if rule not in seen:
            seen.add(rule)
            heldout.append(rule)
    return RuleSet(tuple(train), tuple(heldout))


def walk(start: int, rule: tuple[int, ...], transitions: int) -> list[int]:
    """Follow a rule for ``transitions`` steps; the result has ``transitions + 1`` tokens."""
    tokens = [int(start)]
    for _ in range(transitions):
        tokens.append(int(rule[tokens[-1]]))
    return tokens


def training_sequences(cfg: SequenceConfig, rules: RuleSet) -> torch.Tensor:
    """Offline training walks from training rules only: (N, seq_len)."""
    rng = np.random.default_rng(cfg.seed + 1)
    rows = []
    for rule in rules.train:
        for _ in range(cfg.starts_per_rule):
            rows.append(walk(int(rng.integers(cfg.vocab)), rule, cfg.seq_len - 1))
    return torch.tensor(rows, dtype=torch.long)


def validation_sequences(cfg: SequenceConfig, rules: RuleSet) -> torch.Tensor:
    """Unseen starts from training rules: (N, seq_len). Used for retention tests."""
    rng = np.random.default_rng(cfg.seed + 2)
    rows = []
    for rule in rules.train:
        for _ in range(cfg.val_starts_per_rule):
            rows.append(walk(int(rng.integers(cfg.vocab)), rule, cfg.seq_len - 1))
    return torch.tensor(rows, dtype=torch.long)


def adaptation_episodes(cfg: SequenceConfig, rules: RuleSet) -> list[Episode]:
    """Held-out-rule episodes: a study walk followed by a related test walk."""
    rng = np.random.default_rng(cfg.seed + 3)
    episodes = []
    for rule_id, rule in enumerate(rules.heldout):
        for _ in range(cfg.episodes_per_rule):
            study = walk(int(rng.integers(cfg.vocab)), rule, cfg.study_len)
            test = walk(int(rng.integers(cfg.vocab)), rule, cfg.test_len)
            episodes.append(Episode(rule_id, torch.tensor(study, dtype=torch.long),
                                    torch.tensor(test, dtype=torch.long)))
    return episodes


def to_xy(tokens: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """(N, L) token sequences -> inputs/targets of shape (N, L-1)."""
    if tokens.ndim != 2 or tokens.shape[1] < 2:
        raise ValueError("tokens must be (N, L>=2)")
    return tokens[:, :-1], tokens[:, 1:]
