"""Structured input encoder. One-hot current/previous tokens plus a resource scalar (blueprint 3.4A)."""
from __future__ import annotations

import torch
import torch.nn.functional as F


def encode(tokens: torch.Tensor, vocab: int, resource: float | torch.Tensor = 1.0) -> torch.Tensor:
    """tokens: (B,T) int64 -> (B,T,2*vocab+1) float32.

    ``resource`` is either one scalar for the whole batch or a tensor with shape (B,) or
    (B,T). The control task uses the per-step form to expose a changing budget.
    """
    if tokens.dtype != torch.long:
        tokens = tokens.long()
    cur = F.one_hot(tokens, vocab).float()
    prev = torch.zeros_like(cur)
    prev[:, 1:] = cur[:, :-1]
    if isinstance(resource, torch.Tensor):
        r = resource.float()
        if r.ndim == 1:
            r = r[:, None]
        if r.ndim != 2 or r.shape[0] != tokens.shape[0] or r.shape[1] not in (1, tokens.shape[1]):
            raise ValueError("resource must be a scalar or have shape (B,) or (B,T)")
        if r.shape[1] == 1:
            r = r.expand(-1, tokens.shape[1])
        res = r.unsqueeze(-1)
    else:
        res = torch.full((*tokens.shape, 1), float(resource), dtype=torch.float32)
    return torch.cat([cur, prev, res], dim=-1)
