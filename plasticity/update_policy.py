"""Bounded update policy for fast plasticity (spec 8, 9.2). EXPERIMENTAL."""
from __future__ import annotations

from dataclasses import dataclass

from .eligibility import Attribution


@dataclass(frozen=True)
class UpdatePolicy:
    min_confidence: float = 0.8
    require_verified_signal: bool = True
    max_delta_norm: float = 10.0


@dataclass(frozen=True)
class UpdateDecision:
    allowed: bool
    reasons: tuple[str, ...]


def authorise(attr: Attribution, verified: bool, delta_norm: float, policy: UpdatePolicy | None = None) -> UpdateDecision:
    p = policy or UpdatePolicy()
    reasons = []
    if attr.module is None or not attr.eligible:
        reasons.append("no responsible component was identified")
    if attr.confidence < p.min_confidence:
        reasons.append(f"attribution confidence {attr.confidence:.2f} < {p.min_confidence:.2f}")
    if p.require_verified_signal and not verified:
        reasons.append("no verified learning signal")
    if delta_norm > p.max_delta_norm:
        reasons.append(f"temporary delta {delta_norm:.2f} exceeds bound {p.max_delta_norm:.2f}")
    return UpdateDecision(not reasons, tuple(reasons) or ("eligible for a bounded fast update",))
