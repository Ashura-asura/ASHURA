"""Training/evaluation helpers for the B6 fixed in-context baseline.

The fixed baseline sees a study walk and a test prefix in one flattened window. It has no
recurrence and no fast memory, so any held-out-rule accuracy it reaches comes from in-context
mapping rather than adaptation.
"""
from __future__ import annotations

import time

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from brainsim.core.fixed_baseline import FixedEpisodeMLP
from brainsim.environment.sequence_tasks import walk


def make_episode_pairs(rules, per_rule: int, study_len: int, test_len: int,
                       seed: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Study/test walks from each rule: (len(rules)*per_rule, S/T)."""
    rng = np.random.default_rng(seed)
    study, test = [], []
    for rule in rules:
        for _ in range(per_rule):
            study.append(walk(int(rng.integers(len(rule))), rule, study_len))
            test.append(walk(int(rng.integers(len(rule))), rule, test_len))
    return torch.tensor(study, dtype=torch.long), torch.tensor(test, dtype=torch.long)


def train_fixed_episode(model: FixedEpisodeMLP, study: torch.Tensor, test: torch.Tensor,
                        *, epochs: int, batch: int = 32, lr: float = 3e-3,
                        weight_decay: float = 1e-4, seed: int = 0,
                        device: str = "cpu") -> tuple[dict, float]:
    device = torch.device(device)
    model.to(device).train()
    loader = DataLoader(TensorDataset(study, test), batch_size=batch, shuffle=True,
                        generator=torch.Generator().manual_seed(seed))
    optimiser = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    history = {"loss": []}
    started = time.perf_counter()
    for _ in range(epochs):
        total, n = 0.0, 0
        for sb, tb in loader:
            sb, tb = sb.to(device), tb.to(device)
            logits = model(sb, tb)
            loss = F.cross_entropy(logits.reshape(-1, model.vocab), tb[:, 1:].reshape(-1))
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            total += float(loss.detach()) * sb.shape[0]
            n += sb.shape[0]
        history["loss"].append(total / max(n, 1))
    seconds = time.perf_counter() - started
    history["train_seconds"] = seconds
    model.eval()
    return history, seconds


@torch.no_grad()
def evaluate_fixed_episode(model: FixedEpisodeMLP, study: torch.Tensor,
                           test: torch.Tensor) -> dict:
    model.eval()
    preds = model(study, test).argmax(-1)
    targets = test[:, 1:]
    return {
        "token_accuracy": float((preds == targets).float().mean()),
        "full_recall_accuracy": float((preds == targets).all(dim=1).float().mean()),
    }
