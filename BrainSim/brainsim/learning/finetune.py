"""Persistent fine-tuning with optional replay (B4).

B1/B2 keep the base model frozen during fast-memory adaptation. B4 deliberately changes model
parameters on a candidate and measures old-task retention. Replay is the only variable in the main
comparison: both arms see exactly the same new-task data and optimiser schedule.
"""
from __future__ import annotations

import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from brainsim.core.encoder import encode
from brainsim.core.model import BrainSim
from brainsim.environment.sequence_tasks import to_xy
from brainsim.learning.replay import ReplayBuffer
from brainsim.learning.train import TrainConfig, save_checkpoint


def finetune(model: BrainSim, tokens: torch.Tensor, cfg: TrainConfig, *,
             epochs: int, replay: ReplayBuffer | None = None, replay_ratio: float = 0.5,
             batch_size: int = 32, lr: float = 1e-3, seed: int = 0,
             device: str = "cpu", checkpoint: str | Path | None = None) -> tuple[dict, float]:
    """Fine-tune on ``tokens`` and optionally mix replayed old sequences.

    ``replay_ratio`` is the desired fraction of each batch that comes from replay. It is ignored
    when ``replay`` is empty or None.
    """
    if not 0.0 <= replay_ratio < 1.0:
        raise ValueError("replay_ratio must be in [0, 1)")
    device = torch.device(device)
    model.to(device).train()
    x, y = to_xy(tokens)
    loader = DataLoader(TensorDataset(x, y), batch_size=batch_size, shuffle=True,
                        generator=torch.Generator().manual_seed(seed))
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    generator = torch.Generator().manual_seed(seed)
    n_old = max(1, int(round(batch_size * replay_ratio / (1.0 - replay_ratio)))) \
        if replay is not None and len(replay) and replay_ratio > 0 else 0

    history = {"loss": []}
    started = time.perf_counter()
    for _ in range(epochs):
        total, n = 0.0, 0
        for xb, yb in loader:
            if n_old:
                old = replay.sample(n_old, generator=generator)
                ox, oy = to_xy(old)
                xb = torch.cat([xb, ox], dim=0)
                yb = torch.cat([yb, oy], dim=0)
            xb, yb = xb.to(device), yb.to(device)
            optimiser.zero_grad(set_to_none=True)
            logits = model(encode(xb, model.cfg.vocab)).logits
            loss = F.cross_entropy(logits.reshape(-1, model.cfg.vocab), yb.reshape(-1))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            total += float(loss.detach()) * xb.shape[0]
            n += xb.shape[0]
        history["loss"].append(total / max(n, 1))
    seconds = time.perf_counter() - started
    history["train_seconds"] = seconds
    model.eval()
    if checkpoint is not None:
        save_checkpoint(model, checkpoint, history, cfg)
    return history, seconds
