"""Synthetic budgeted need-response task for B5 (blueprint B5).

The task is deliberately small and deterministic. Each step exposes a need type and the
current computational budget. The system chooses one of six actions with a known cost and a
need-dependent utility. A correct policy spends more when the need is important and the budget
allows it, and falls back to a cheaper action when it does not.

Nothing here calls a language model or an external service.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import torch

NEEDS = ("predict", "retrieve", "verify", "adapt")
ACTIONS = ("predict", "retrieve", "verify", "adapt", "store", "wait")
ACTION_COSTS = (1, 2, 3, 4, 2, 0)
WAIT = ACTIONS.index("wait")

# Rows: needs, columns: actions. Values are expected utility, not success probability alone.
UTILITY = (
    (0.90, 0.30, 0.20, 0.10, 0.25, 0.05),
    (0.20, 0.90, 0.35, 0.10, 0.25, 0.05),
    (0.15, 0.30, 0.90, 0.20, 0.25, 0.05),
    (0.10, 0.20, 0.30, 0.90, 0.45, 0.05),
)


@dataclass(frozen=True)
class ControlConfig:
    n_needs: int = len(NEEDS)
    n_actions: int = len(ACTIONS)
    episode_len: int = 8
    max_budget: int = 12
    initial_budgets: tuple[int, ...] = (2, 5, 9, 12)
    recovery: int = 1

    def __post_init__(self) -> None:
        if self.n_needs != len(NEEDS) or self.n_actions != len(ACTIONS):
            raise ValueError("need/action counts must match the fixed utility table")
        if self.episode_len < 1:
            raise ValueError("episode_len must be >= 1")
        if self.max_budget < 1:
            raise ValueError("max_budget must be >= 1")
        if any(b < 0 or b > self.max_budget for b in self.initial_budgets):
            raise ValueError("initial budgets must be in [0, max_budget]")
        if self.recovery < 0:
            raise ValueError("recovery must be >= 0")


@dataclass
class ControlBatch:
    tokens: torch.Tensor       # (N,T) need ids, the model input
    resource: torch.Tensor     # (N,T) budget / max_budget before each action
    needs: torch.Tensor        # (N,T) need ids, the need-head target
    actions: torch.Tensor      # (N,T) optimal action under the oracle budget path
    costs: torch.Tensor        # (N,T) cost of the optimal action
    budgets: torch.Tensor      # (N,T) budget before each action
    init_budget: torch.Tensor  # (N,) starting budget for closed-loop evaluation
    utilities: torch.Tensor    # (N,T) utility of the optimal action

    def __len__(self) -> int:
        return self.tokens.shape[0]


def optimal_action(need: int, budget: int, t: int, cfg: ControlConfig) -> int:
    """Finite-horizon optimal action for a known need and budget at step ``t``.

    The need is observed before the action, but spending now changes future budgets. The value
    table therefore includes the expected value of later steps, not only this step's utility.
    Ties prefer the cheaper action.
    """
    if not 0 <= t < cfg.episode_len:
        raise ValueError("t outside the episode")
    if budget < 0 or budget > cfg.max_budget:
        raise ValueError("budget outside [0, max_budget]")
    values = _value_table(cfg)[t + 1]
    row = UTILITY[int(need)]
    feasible = [a for a in range(len(ACTIONS)) if ACTION_COSTS[a] <= budget]
    if not feasible:
        return WAIT
    def score(a: int) -> tuple[float, int]:
        next_budget = min(cfg.max_budget, budget - ACTION_COSTS[a] + cfg.recovery)
        return (row[a] + values[next_budget], -ACTION_COSTS[a])
    return max(feasible, key=score)


@lru_cache(maxsize=None)
def _value_table(cfg: ControlConfig) -> tuple[tuple[float, ...], ...]:
    """V[t][b] = expected utility from step t onward with budget b, before observing the need."""
    table = [[0.0] * (cfg.max_budget + 1) for _ in range(cfg.episode_len + 1)]
    for t in range(cfg.episode_len - 1, -1, -1):
        for b in range(cfg.max_budget + 1):
            total = 0.0
            for need in range(cfg.n_needs):
                row = UTILITY[need]
                feasible = [a for a in range(len(ACTIONS)) if ACTION_COSTS[a] <= b]
                best = max(
                    row[a] + table[t + 1][min(cfg.max_budget,
                                             b - ACTION_COSTS[a] + cfg.recovery)]
                    for a in feasible)
                total += best
            table[t][b] = total / cfg.n_needs
    return tuple(tuple(row) for row in table)


def feasible_mask(budgets: torch.Tensor) -> torch.Tensor:
    """(...,) budgets -> (..., n_actions) bool mask of actions the budget can pay for."""
    costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
    budgets = torch.as_tensor(budgets, dtype=torch.long)
    return budgets.unsqueeze(-1) >= costs


def resolve_action(action: torch.Tensor, budgets: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Replace unaffordable actions with WAIT; return (resolved actions, violation mask)."""
    costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
    action = torch.as_tensor(action, dtype=torch.long)
    violation = costs[action] > torch.as_tensor(budgets, dtype=torch.long)
    resolved = torch.where(violation, torch.full_like(action, WAIT), action)
    return resolved, violation


def expected_cost(probabilities: torch.Tensor) -> torch.Tensor:
    """Expected action cost from a (N, n_actions) probability tensor."""
    costs = torch.tensor(ACTION_COSTS, dtype=probabilities.dtype)
    return probabilities @ costs


def make_episodes(cfg: ControlConfig, n: int, seed: int = 0) -> ControlBatch:
    """Generate oracle-budget episodes for training or open-loop evaluation."""
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = np.random.default_rng(seed)
    needs = rng.integers(cfg.n_needs, size=(n, cfg.episode_len), dtype=np.int64)
    init_budget = rng.choice(cfg.initial_budgets, size=n).astype(np.int64)
    budgets = np.empty_like(needs)
    actions = np.empty_like(needs)
    costs = np.empty_like(needs)
    utilities = np.empty_like(needs, dtype=np.float32)

    for i in range(n):
        budget = int(init_budget[i])
        for t in range(cfg.episode_len):
            need = int(needs[i, t])
            action = optimal_action(need, budget, t, cfg)
            cost = ACTION_COSTS[action]
            budgets[i, t] = budget
            actions[i, t] = action
            costs[i, t] = cost
            utilities[i, t] = UTILITY[need][action]
            budget = min(cfg.max_budget, budget - cost + cfg.recovery)

    return ControlBatch(
        tokens=torch.tensor(needs, dtype=torch.long),
        resource=torch.tensor(budgets / cfg.max_budget, dtype=torch.float32),
        needs=torch.tensor(needs, dtype=torch.long),
        actions=torch.tensor(actions, dtype=torch.long),
        costs=torch.tensor(costs, dtype=torch.long),
        budgets=torch.tensor(budgets, dtype=torch.long),
        init_budget=torch.tensor(init_budget, dtype=torch.long),
        utilities=torch.tensor(utilities, dtype=torch.float32),
    )


def baseline_action(name: str, needs: torch.Tensor, budgets: torch.Tensor,
                    t: int | None = None, cfg: ControlConfig | None = None) -> torch.Tensor:
    """Vectorised simple policies used as controls.

    oracle      : finite-horizon optimal action for the current need and budget (needs t, cfg).
    need_match  : the action that matches the need, regardless of cost (masked if infeasible).
    always_max  : the single action with the highest average utility across needs.
    always_wait : never spend.
    random      : uniform choice among feasible actions.
    """
    needs = torch.as_tensor(needs, dtype=torch.long)
    budgets = torch.as_tensor(budgets, dtype=torch.long)
    mask = feasible_mask(budgets)
    if name == "oracle":
        if t is None or cfg is None:
            raise ValueError("oracle needs t and cfg")
        return torch.tensor([
            optimal_action(int(n), int(b), t, cfg)
            for n, b in zip(needs.flatten().tolist(), budgets.flatten().tolist())
        ], dtype=torch.long).view_as(needs)
    if name == "need_match":
        return torch.where(mask[torch.arange(needs.shape[0]), needs], needs,
                           torch.full_like(needs, WAIT))
    if name == "always_max":
        mean_utility = torch.tensor(UTILITY, dtype=torch.float32).mean(0)
        choice = int(mean_utility.argmax())
        return torch.where(mask[:, choice], torch.full_like(needs, choice),
                           torch.full_like(needs, WAIT))
    if name == "always_wait":
        return torch.full_like(needs, WAIT)
    if name == "random":
        logits = torch.rand(needs.shape[0], len(ACTIONS))
        logits = logits.masked_fill(~mask, float("-inf"))
        return logits.argmax(-1)
    raise ValueError(f"unknown baseline: {name}")


def utility_of(needs: torch.Tensor, actions: torch.Tensor) -> torch.Tensor:
    table = torch.tensor(UTILITY, dtype=torch.float32)
    return table[torch.as_tensor(needs, dtype=torch.long),
                 torch.as_tensor(actions, dtype=torch.long)]
