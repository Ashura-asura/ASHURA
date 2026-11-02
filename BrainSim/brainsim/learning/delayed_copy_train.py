"""Training and evaluation for the delayed-copy experiment (B2).

Two arms share the same data and recall objective:

* ``gru``   — the existing BrainSim recurrent core, teacher-forced next-token prediction,
              loss taken only on the recalled cue tokens.
* ``fixed`` — the parameter-matched non-recurrent MLP, which sees the cue/blank/GO window and
              predicts the whole recall block at once.

Only the B2 comparison lives here; B1 training stays in ``brainsim.learning.train``.
"""
from __future__ import annotations

import time

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from brainsim.core.encoder import encode
from brainsim.core.fixed_baseline import FixedWindowMLP
from brainsim.core.model import BrainSim
from brainsim.environment.delayed_copy import DelayedCopyConfig, make_batch


def _loader(tokens: torch.Tensor, cues: torch.Tensor, mask: torch.Tensor, batch: int,
            seed: int, shuffle: bool = True) -> DataLoader:
    ds = TensorDataset(tokens, cues, mask)
    return DataLoader(ds, batch_size=batch, shuffle=shuffle,
                      generator=torch.Generator().manual_seed(seed))


def train_gru(model: BrainSim, cfg: DelayedCopyConfig, tokens: torch.Tensor,
              cues: torch.Tensor, mask: torch.Tensor, *, epochs: int, batch: int = 64,
              lr: float = 3e-3, weight_decay: float = 1e-4, seed: int = 0,
              device: str = "cpu") -> tuple[BrainSim, dict, float]:
    device = torch.device(device)
    model.to(device).train()
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    loader = _loader(tokens, cues, mask, batch, seed)
    history = {"loss": []}
    started = time.perf_counter()
    for _ in range(epochs):
        total, n = 0.0, 0
        for xb, _, mb in loader:
            xb, mb = xb.to(device), mb.to(device)
            yb = xb[:, 1:]
            optimiser.zero_grad(set_to_none=True)
            logits = model(encode(xb[:, :-1], cfg.vocab)).logits
            loss = F.cross_entropy(logits[mb], yb[mb])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            total += float(loss.detach()) * int(mb.sum())
            n += int(mb.sum())
        history["loss"].append(total / max(n, 1))
    seconds = time.perf_counter() - started
    history["train_seconds"] = seconds
    model.eval()
    return model, history, seconds


def train_fixed(model: FixedWindowMLP, cfg: DelayedCopyConfig, tokens: torch.Tensor,
                cues: torch.Tensor, mask: torch.Tensor, *, epochs: int, batch: int = 64,
                lr: float = 3e-3, weight_decay: float = 1e-4, seed: int = 0,
                device: str = "cpu") -> tuple[FixedWindowMLP, dict, float]:
    device = torch.device(device)
    model.to(device).train()
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    loader = _loader(tokens, cues, mask, batch, seed)
    history = {"loss": []}
    started = time.perf_counter()
    for _ in range(epochs):
        total, n = 0.0, 0
        for xb, cb, _ in loader:
            xb, cb = xb.to(device), cb.to(device)
            optimiser.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = F.cross_entropy(logits.reshape(-1, cfg.symbols), cb.reshape(-1))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            total += float(loss.detach()) * xb.shape[0]
            n += xb.shape[0]
        history["loss"].append(total / max(n, 1))
    seconds = time.perf_counter() - started
    history["train_seconds"] = seconds
    model.eval()
    return model, history, seconds


def _metrics(preds: torch.Tensor, batch: dict) -> dict:
    cues = batch["cues"]
    return {
        "token_accuracy": float((preds == cues).float().mean()),
        "full_recall_accuracy": float((preds == cues).all(dim=1).float().mean()),
    }


@torch.no_grad()
def evaluate_gru(model: BrainSim, cfg: DelayedCopyConfig, batch: dict) -> dict:
    model.eval()
    tokens = batch["tokens"]
    mask = batch["recall_mask"]
    logits = model(encode(tokens[:, :-1], cfg.vocab)).logits
    # Every row has exactly cue_len masked positions, in recall order.
    preds = logits[mask].argmax(-1).view(tokens.shape[0], cfg.cue_len)
    return _metrics(preds, batch)


@torch.no_grad()
def evaluate_fixed(model: FixedWindowMLP, cfg: DelayedCopyConfig, batch: dict) -> dict:
    model.eval()
    return _metrics(model(batch["tokens"]).argmax(-1), batch)


def make_fixed_dataset(cfg: DelayedCopyConfig, size: int, seed: int) -> tuple[torch.Tensor, ...]:
    batch = make_batch(cfg, size, seed=seed)
    return batch["tokens"], batch["cues"], batch["recall_mask"]
