"""Delayed-copy environment: hold a short cue across a blank delay, then reproduce it (B2).

Each sequence starts with ``cue_len`` random symbols, followed by ``delay`` blank tokens, a
GO token, and then the same cue symbols again::

    [a, c, b, BLANK x delay, GO, a, c, b]

The total length is fixed at ``cue_len + max_delay + 1 + cue_len`` so batches are rectangular;
positions after the recall block are BLANK and are ignored by the loss. Sequences are generated
locally and deterministically; no language model is involved.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class DelayedCopyConfig:
    symbols: int = 8
    cue_len: int = 3
    max_delay: int = 20
    train_delays: tuple[int, ...] = (2, 4, 6, 8)
    eval_delays: tuple[int, ...] = (1, 2, 4, 6, 8, 12, 16, 20)

    def __post_init__(self) -> None:
        if self.symbols < 2 or self.cue_len < 1 or self.max_delay < 1:
            raise ValueError("symbols, cue_len and max_delay must be positive")
        if any(d < 0 or d > self.max_delay for d in self.train_delays + self.eval_delays):
            raise ValueError("delays must be within [0, max_delay]")

    @property
    def blank(self) -> int:
        return self.symbols

    @property
    def go(self) -> int:
        return self.symbols + 1

    @property
    def vocab(self) -> int:
        """Symbols + BLANK + GO. BLANK is also used for padding."""
        return self.symbols + 2

    @property
    def length(self) -> int:
        return self.cue_len + self.max_delay + 1 + self.cue_len

    @property
    def recall_span(self) -> int:
        return self.cue_len


def make_batch(cfg: DelayedCopyConfig, batch_size: int, delays: tuple[int, ...] | None = None,
               seed: int = 0) -> dict:
    """Generate a batch of delayed-copy sequences.

    Returns tokens ``(B, length)``, cues ``(B, cue_len)`` and a boolean loss mask
    ``(B, length - 1)`` marking the transitions that predict a recalled cue.
    """
    delays = delays or cfg.train_delays
    g = torch.Generator().manual_seed(seed)
    delay = torch.tensor(delays)[torch.randint(len(delays), (batch_size,), generator=g)]
    cues = torch.randint(0, cfg.symbols, (batch_size, cfg.cue_len), generator=g)
    tokens = torch.full((batch_size, cfg.length), cfg.blank, dtype=torch.long)
    tokens[:, :cfg.cue_len] = cues
    rows = torch.arange(batch_size)
    go_pos = cfg.cue_len + delay
    tokens[rows, go_pos] = cfg.go
    for i in range(cfg.cue_len):
        tokens[rows, go_pos + 1 + i] = cues[:, i]

    mask = torch.zeros(batch_size, cfg.length - 1, dtype=torch.bool)
    for i in range(cfg.cue_len):
        mask[rows, go_pos + i] = True          # logits at p predict token p + 1
    return {"tokens": tokens, "cues": cues, "delay": delay, "recall_mask": mask}


def fixed_window(tokens: torch.Tensor, cfg: DelayedCopyConfig) -> torch.Tensor:
    """Fixed-size prefix for a non-recurrent baseline.

    Keeps the cue block, the blanks, and the GO token, but replaces everything after GO with
    BLANK. The result is ``(B, cue_len + max_delay + 1)`` and never contains the answer.
    """
    width = cfg.cue_len + cfg.max_delay + 1
    prefix = tokens[:, :width].clone()
    go = (prefix == cfg.go).float().argmax(dim=1, keepdim=True)
    positions = torch.arange(width).unsqueeze(0)
    return torch.where(positions > go, torch.full_like(prefix, cfg.blank), prefix)
