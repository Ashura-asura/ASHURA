"""Tiny recurrent core with prediction, need, action and confidence heads (blueprint 3.3)."""
from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn


@dataclass(frozen=True)
class BrainSimConfig:
    vocab: int = 16
    hidden: int = 256
    layers: int = 2
    in_dim: int = 33            # current token + previous token + resource scalar
    n_needs: int = 6
    n_actions: int = 6
    dropout: float = 0.0


@dataclass
class BrainSimOutput:
    logits: torch.Tensor       # (B,T,vocab) next-token logits
    need: torch.Tensor         # (B,T,n_needs)
    action: torch.Tensor       # (B,T,n_actions)
    confidence: torch.Tensor   # (B,T,1) probability the prediction is correct
    hidden: torch.Tensor       # (B,T,hidden)
    state: torch.Tensor | None


class BrainSim(nn.Module):
    def __init__(self, cfg: BrainSimConfig | None = None):
        super().__init__()
        self.cfg = cfg or BrainSimConfig()
        c = self.cfg
        self.encoder = nn.Sequential(nn.Linear(c.in_dim, c.hidden), nn.LayerNorm(c.hidden), nn.GELU())
        self.core = nn.GRU(c.hidden, c.hidden, num_layers=c.layers, batch_first=True, dropout=c.dropout)
        self.prediction = nn.Linear(c.hidden, c.vocab)
        self.need = nn.Linear(c.hidden, c.n_needs)
        self.action = nn.Linear(c.hidden, c.n_actions)
        self.confidence = nn.Linear(c.hidden, 1)

    @property
    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, x: torch.Tensor, state: torch.Tensor | None = None) -> BrainSimOutput:
        z = self.encoder(x)
        out, state = self.core(z, state)
        return BrainSimOutput(self.prediction(out), self.need(out), self.action(out),
                              torch.sigmoid(self.confidence(out)), out, state)
