"""Structured input encoder. One-hot current/previous tokens plus a resource scalar (blueprint 3.4A)."""
from __future__ import annotations

import torch
import torch.nn.functional as F


def encode(tokens: torch.Tensor, vocab: int, resource: float = 1.0) -> torch.Tensor:
    """tokens: (B,T) int64 -> (B,T,2*vocab+1) float32."""
    if tokens.dtype != torch.long:
        tokens = tokens.long()
    cur = F.one_hot(tokens, vocab).float()
    prev = torch.zeros_like(cur)
    prev[:, 1:] = cur[:, :-1]
    res = torch.full((*tokens.shape, 1), resource, dtype=torch.float32)
    return torch.cat([cur, prev, res], dim=-1)
