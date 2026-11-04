"""Training and evaluation for the B5 budgeted need-response task.

The recurrent core's action head is trained with a supervised action target, the need head with
the observed need, and the confidence head with whether the action head's current choice is
correct. The confidence target is detached, so it tracks the policy rather than leaking the
answer into the action loss. Cost prediction is derived from the action distribution and the
fixed action-cost table; no extra head is introduced.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from brainsim.core.encoder import encode
from brainsim.core.model import BrainSim
from brainsim.environment.control_tasks import (ACTION_COSTS, ControlBatch,
                                                 ControlConfig, baseline_action,
                                                 expected_cost, feasible_mask,
                                                 resolve_action, utility_of)
from brainsim.learning.train import TrainConfig, save_checkpoint


@dataclass(frozen=True)
class ControlTrainConfig:
    epochs: int = 20
    batch_size: int = 64
    lr: float = 3e-3
    weight_decay: float = 1e-4
    grad_clip: float = 1.0
    seed: int = 0
    device: str = "cpu"
    need_weight: float = 0.2
    confidence_weight: float = 0.1
    checkpoint: str | None = None


def _loader(batch: ControlBatch, batch_size: int, seed: int) -> DataLoader:
    ds = TensorDataset(batch.tokens, batch.resource, batch.needs, batch.actions)
    return DataLoader(ds, batch_size=batch_size, shuffle=True,
                      generator=torch.Generator().manual_seed(seed))


def train_control(model: BrainSim, batch: ControlBatch, cfg: ControlTrainConfig,
                  train_config: TrainConfig | None = None) -> tuple[dict, float]:
    device = torch.device(cfg.device)
    model.to(device).train()
    loader = _loader(batch, cfg.batch_size, cfg.seed)
    optimiser = torch.optim.AdamW(model.parameters(), lr=cfg.lr,
                                  weight_decay=cfg.weight_decay)
    history = {"loss": [], "action_loss": [], "need_loss": [], "confidence_loss": []}
    started = time.perf_counter()
    for _ in range(cfg.epochs):
        total = {"loss": 0.0, "action": 0.0, "need": 0.0, "confidence": 0.0}
        n = 0
        for xb, rb, nb, ab in loader:
            xb, rb, nb, ab = xb.to(device), rb.to(device), nb.to(device), ab.to(device)
            out = model(encode(xb, model.cfg.vocab, rb))
            action_loss = F.cross_entropy(out.action.reshape(-1, model.cfg.n_actions),
                                          ab.reshape(-1))
            need_loss = F.cross_entropy(out.need.reshape(-1, model.cfg.n_needs),
                                        nb.reshape(-1))
            correct = (out.action.argmax(-1).detach() == ab).float()
            confidence_loss = F.binary_cross_entropy(
                out.confidence.squeeze(-1).clamp(1e-6, 1 - 1e-6), correct)
            loss = (action_loss + cfg.need_weight * need_loss
                    + cfg.confidence_weight * confidence_loss)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            if cfg.grad_clip > 0:
                nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            optimiser.step()
            total["loss"] += float(loss.detach()) * xb.shape[0]
            total["action"] += float(action_loss.detach()) * xb.shape[0]
            total["need"] += float(need_loss.detach()) * xb.shape[0]
            total["confidence"] += float(confidence_loss.detach()) * xb.shape[0]
            n += xb.shape[0]
        history["loss"].append(total["loss"] / max(n, 1))
        history["action_loss"].append(total["action"] / max(n, 1))
        history["need_loss"].append(total["need"] / max(n, 1))
        history["confidence_loss"].append(total["confidence"] / max(n, 1))
    seconds = time.perf_counter() - started
    history["train_seconds"] = seconds
    model.eval()
    path = cfg.checkpoint
    if path:
        save_checkpoint(model, path, history, train_config)
    return history, seconds


def _ece(confidence: torch.Tensor, correct: torch.Tensor, bins: int = 10) -> float:
    """Expected calibration error for binary confidence."""
    total = 0.0
    for lo in range(bins):
        hi = lo + 1
        low, high = lo / bins, hi / bins
        mask = (confidence >= low) & (confidence < high if hi < bins else confidence <= high)
        if bool(mask.any()):
            total += (float(mask.float().mean())
                      * abs(float(confidence[mask].mean()) - float(correct[mask].float().mean())))
    return total


@torch.no_grad()
def evaluate_control(model: BrainSim, batch: ControlBatch,
                     mask_infeasible: bool = True) -> dict:
    """Teacher-forced evaluation on the oracle budget path."""
    model.eval()
    out = model(encode(batch.tokens, model.cfg.vocab, batch.resource))
    raw = out.action.argmax(-1)
    mask = feasible_mask(batch.budgets)
    chosen = out.action.masked_fill(~mask, float("-inf")).argmax(-1) if mask_infeasible else raw
    resolved, _ = resolve_action(chosen, batch.budgets)
    target = batch.actions
    correct = resolved == target
    confidence = out.confidence.squeeze(-1)
    costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
    raw_violation = costs[raw] > batch.budgets
    probs = torch.softmax(out.action.masked_fill(~mask, float("-inf")), dim=-1)
    expected = expected_cost(probs)
    realised = costs[resolved].float()
    need_correct = out.need.argmax(-1) == batch.needs

    return {
        "action_accuracy": float(correct.float().mean()),
        "raw_action_accuracy": float((raw == target).float().mean()),
        "need_accuracy": float(need_correct.float().mean()),
        "mean_utility": float(utility_of(batch.needs, resolved).mean()),
        "mean_cost": float(realised.mean()),
        "total_utility_per_episode": float(utility_of(batch.needs, resolved).sum(-1).mean()),
        "total_cost_per_episode": float(realised.sum(-1).mean()),
        "raw_infeasible_rate": float(raw_violation.float().mean()),
        "confidence_brier": float((confidence - correct.float()).pow(2).mean()),
        "confidence_ece": _ece(confidence.flatten(), correct.flatten()),
        "mean_confidence": float(confidence.mean()),
        "mean_confidence_correct": float(confidence[correct].mean()) if bool(correct.any()) else None,
        "mean_confidence_incorrect": (float(confidence[~correct].mean())
                                      if bool((~correct).any()) else None),
        "expected_cost_mae": float((expected - realised).abs().mean()),
        "steps": int(correct.numel()),
    }


@torch.no_grad()
def simulate_policy(batch: ControlBatch, cfg: ControlConfig, name: str) -> dict:
    """Closed-loop rollout of a simple baseline policy."""
    budgets = batch.init_budget.clone()
    total_utility = torch.zeros(len(batch))
    total_cost = torch.zeros(len(batch))
    correct = []
    infeasible = []
    for t in range(cfg.episode_len):
        needs = batch.needs[:, t]
        actions = baseline_action(name, needs, budgets, t=t, cfg=cfg)
        target = baseline_action("oracle", needs, budgets, t=t, cfg=cfg)
        resolved, violation = resolve_action(actions, budgets)
        total_utility += utility_of(needs, resolved)
        costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
        cost = costs[resolved].float()
        total_cost += cost
        correct.append(resolved == target)
        infeasible.append(violation)
        budgets = torch.clamp(budgets - cost.long() + cfg.recovery, 0, cfg.max_budget)
    accuracy = torch.cat(correct).float().mean()
    return {
        "action_accuracy": float(accuracy),
        "mean_utility": float(total_utility.mean() / cfg.episode_len),
        "mean_cost": float(total_cost.mean() / cfg.episode_len),
        "total_utility_per_episode": float(total_utility.mean()),
        "total_cost_per_episode": float(total_cost.mean()),
        "infeasible_rate": float(torch.cat(infeasible).float().mean()),
    }


@torch.no_grad()
def simulate_model(model: BrainSim, batch: ControlBatch, cfg: ControlConfig) -> dict:
    """Closed-loop rollout of the model's masked action policy, one step at a time."""
    model.eval()
    budgets = batch.init_budget.clone()
    total_utility = torch.zeros(len(batch))
    total_cost = torch.zeros(len(batch))
    correct, infeasible, confidence, expected_mae = [], [], [], []
    need_hist, resource_hist = [], []
    costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
    for t in range(cfg.episode_len):
        needs = batch.needs[:, t]
        need_hist.append(needs)
        resource_hist.append(budgets.float() / cfg.max_budget)
        out = model(encode(torch.stack(need_hist, dim=1), model.cfg.vocab,
                           torch.stack(resource_hist, dim=1)))
        raw = out.action[:, -1].argmax(-1)
        mask = feasible_mask(budgets)
        chosen = out.action[:, -1].masked_fill(~mask, float("-inf")).argmax(-1)
        resolved, _ = resolve_action(chosen, budgets)
        target = baseline_action("oracle", needs, budgets, t=t, cfg=cfg)
        total_utility += utility_of(needs, resolved)
        cost = costs[resolved].float()
        total_cost += cost
        correct.append(resolved == target)
        infeasible.append(costs[raw] > budgets)
        confidence.append(out.confidence[:, -1, 0])
        probs = torch.softmax(out.action[:, -1].masked_fill(~mask, float("-inf")), dim=-1)
        expected_mae.append((expected_cost(probs) - cost).abs())
        budgets = torch.clamp(budgets - cost.long() + cfg.recovery, 0, cfg.max_budget)
    accurate = torch.cat(correct)
    confidence = torch.cat(confidence)
    return {
        "action_accuracy": float(accurate.float().mean()),
        "mean_utility": float(total_utility.mean() / cfg.episode_len),
        "mean_cost": float(total_cost.mean() / cfg.episode_len),
        "total_utility_per_episode": float(total_utility.mean()),
        "total_cost_per_episode": float(total_cost.mean()),
        "infeasible_rate": float(torch.cat(infeasible).float().mean()),
        "confidence_brier": float((confidence - accurate.float()).pow(2).mean()),
        "confidence_ece": _ece(confidence, accurate),
        "mean_confidence": float(confidence.mean()),
        "expected_cost_mae": float(torch.cat(expected_mae).mean()),
    }
