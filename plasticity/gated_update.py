"""Gated consumer for CAGE update authorisations (Phase 1, P07).

CAGE decides whether a verified learning signal may produce a bounded update. This module is the
consumer side: a temporary ``FastWeights`` association is only touched when the decision is
allowed and a proposal exists. It never promotes a persistent checkpoint; that remains NGR's job.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fast_weights import FastWeights
from .update_policy import UpdateDecision


@dataclass(frozen=True)
class UpdateProposal:
    module: str
    key: str
    value: str
    source: str
    delta_norm: float = 0.0


@dataclass(frozen=True)
class UpdateOutcome:
    applied: bool
    reason: str
    delta_norm_before: float = 0.0
    delta_norm_after: float = 0.0
    surprise: float | None = None


class GatedUpdater:
    """Apply a proposal to temporary fast state only when the update decision allows it."""

    def __init__(self, fast: FastWeights):
        self.fast = fast

    def apply(self, decision: UpdateDecision, proposal: UpdateProposal | None) -> UpdateOutcome:
        if proposal is None:
            return UpdateOutcome(False, "no verified update proposal")
        if not decision.allowed:
            return UpdateOutcome(False, "update policy rejected the proposal: " + "; ".join(decision.reasons))
        before = self.fast.delta_norm
        surprise = self.fast.learn(proposal.key, proposal.value)
        return UpdateOutcome(True, f"applied bounded update to {proposal.module}",
                             before, self.fast.delta_norm, surprise)
