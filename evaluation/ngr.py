"""NGR - Non-Regression Gate (spec 11). Mandatory, not experimental.

Promotion rule for every capability i:   score_candidate(i) >= score_stable(i) - eps_i
plus a meaningful gain on the intended target capability.
Tolerances are frozen in the policy object BEFORE evaluation and cannot be altered afterwards.
NGR guarantees only that the candidate passes the defined suite, not behaviour on unseen inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class NGRPolicy:
    target: str                                   # capability the candidate is meant to improve
    min_target_gain: float = 0.05
    default_epsilon: float = 0.02
    epsilons: "MappingProxyType[str, float]" = field(default_factory=lambda: MappingProxyType({}))
    critical: frozenset = frozenset()             # critical capabilities get epsilon = 0
    max_latency_ratio: float = 1.25               # candidate p95 latency may be at most 1.25x stable
    max_ram_ratio: float = 1.25

    def epsilon(self, capability: str) -> float:
        if capability in self.critical:
            return 0.0
        return self.epsilons.get(capability, self.default_epsilon)


@dataclass
class NGRResult:
    promote: bool
    reasons: list[str]
    deltas: dict[str, float]


def evaluate(policy: NGRPolicy, stable: dict[str, float], candidate: dict[str, float],
             stable_perf: dict[str, float] | None = None, candidate_perf: dict[str, float] | None = None) -> NGRResult:
    reasons: list[str] = []
    deltas = {k: candidate.get(k, float("-inf")) - v for k, v in stable.items()}

    missing = [k for k in stable if k not in candidate]
    if missing:
        reasons.append(f"candidate was not evaluated on: {missing}")
    if policy.target not in candidate or policy.target not in stable:
        reasons.append(f"target capability {policy.target!r} missing from scores")
    else:
        gain = candidate[policy.target] - stable[policy.target]
        if gain < policy.min_target_gain:
            reasons.append(f"target gain {gain:+.3f} < required {policy.min_target_gain:.3f}")

    for cap, base in stable.items():
        if cap == policy.target or cap not in candidate:
            continue
        if candidate[cap] < base - policy.epsilon(cap):
            reasons.append(f"regression on {cap}: {base:.3f} -> {candidate[cap]:.3f} (eps {policy.epsilon(cap)})")

    if stable_perf and candidate_perf:
        for key, ratio in (("p95_ms", policy.max_latency_ratio), ("peak_rss_mb", policy.max_ram_ratio)):
            if key in stable_perf and key in candidate_perf and stable_perf[key] > 0 \
                    and candidate_perf[key] > stable_perf[key] * ratio:
                reasons.append(f"{key} {stable_perf[key]:.1f} -> {candidate_perf[key]:.1f} exceeds x{ratio}")

    return NGRResult(promote=not reasons, reasons=reasons or ["all promotion conditions met"], deltas=deltas)
