"""CAGE - Causal Attribution and Gradient Eligibility (spec 9). EXPERIMENTAL.

This module is the recording/decision layer around `plasticity.eligibility`. It never applies an
update itself; callers must check `authorise()` before touching a component.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from brain.execution_trace import ExecutionTrace
from plasticity.eligibility import Attribution, Verifiers, attribute
from plasticity.gated_update import UpdateProposal
from plasticity.update_policy import UpdateDecision, UpdatePolicy, authorise


class CAGE:
    def __init__(self, policy: UpdatePolicy | None = None, log_path: str | Path | None = None):
        self.policy = policy or UpdatePolicy()
        self.log_path = Path(log_path) if log_path else None
        self.decisions: list[dict] = []

    def attribute(self, trace: ExecutionTrace, expected=None, verifiers: Verifiers | None = None) -> Attribution:
        return attribute(trace, expected, verifiers)

    def authorise(self, attr: Attribution, verified: bool, delta_norm: float = 0.0) -> UpdateDecision:
        d = authorise(attr, verified, delta_norm, self.policy)
        self._record(attr, d, verified, delta_norm)
        return d

    def propose(self, attr: Attribution, decision: UpdateDecision, *, verified: bool,
                key: str, value: str, source: str = "") -> UpdateProposal | None:
        """Turn an allowed, independently verified decision into a bounded update proposal.

        A rejected decision, an unattributed failure, or an unverified signal produces no
        proposal, so no downstream consumer can turn an ordinary model error into a label.
        """
        if not verified or not decision.allowed or attr.module is None:
            return None
        return UpdateProposal(module=attr.module, key=key, value=value, source=source)

    def _record(self, attr: Attribution, decision: UpdateDecision, verified: bool, delta_norm: float) -> None:
        row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "attribution": asdict(attr),
               "verified": verified, "delta_norm": delta_norm, "update": asdict(decision)}
        self.decisions.append(row)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, default=str) + "\n")
