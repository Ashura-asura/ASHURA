"""Parameter-matched non-recurrent baseline for delayed recall (B6 "fixed network").

The model flattens the cue + delay + GO prefix and predicts all recalled symbols at once.
It has no recurrence: every output is a direct function of the flattened window. This is the
fixed-network arm the recurrent core is compared against.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from brainsim.environment.delayed_copy import DelayedCopyConfig, fixed_window


class FixedWindowMLP(nn.Module):
    def __init__(self, cfg: DelayedCopyConfig, hidden: int = 352):
        super().__init__()
        self.cfg = cfg
        self.hidden = hidden
        self.in_dim = (cfg.cue_len + cfg.max_delay + 1) * cfg.vocab
        self.out_dim = cfg.cue_len * cfg.symbols
        self.net = nn.Sequential(
            nn.Linear(self.in_dim, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
            nn.Linear(hidden, self.out_dim),
        )

    @property
    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        """tokens ``(B, length)`` -> cue logits ``(B, cue_len, symbols)``."""
        window = fixed_window(tokens, self.cfg)
        z = F.one_hot(window, self.cfg.vocab).float().flatten(1)
        out = self.net(z)
        return out.view(tokens.shape[0], self.cfg.cue_len, self.cfg.symbols)
