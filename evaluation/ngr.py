"""NGR - Non-Regression Gate (spec 11). Mandatory, not experimental.

Promotion rule for every capability i:   score_candidate(i) >= score_stable(i) - eps_i
plus a meaningful gain on the intended target capability.
Tolerances are frozen in the policy object BEFORE evaluation and cannot be altered afterwards.

Phase 1 hardening (P09-P11):
  * non-finite scores and performance values are rejected explicitly (NaN, +/-inf);
  * every score is checked against a metric schema (range, direction, minimum samples);
  * required capabilities must be present in both the baseline and the candidate;
  * a policy can require p95 latency and peak RAM measurements; missing measurements reject.
NGR guarantees only that the candidate passes the defined suite, not behaviour on unseen inputs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class MetricSpec:
    """Validation contract for one capability score."""
    minimum: float = 0.0
    maximum: float = 1.0
    direction: str = "higher"          # "higher" = larger is better, "lower" = smaller is better
    min_samples: int = 1
    epsilon: float | None = None        # overrides NGRPolicy epsilon for this capability

    def __post_init__(self) -> None:
        if self.direction not in {"higher", "lower"}:
            raise ValueError("direction must be 'higher' or 'lower'")
        if not (_finite(self.minimum) and _finite(self.maximum)) or self.minimum > self.maximum:
            raise ValueError("metric range must be finite and minimum <= maximum")
        if self.min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if self.epsilon is not None and (not _finite(self.epsilon) or self.epsilon < 0):
            raise ValueError("epsilon must be a finite non-negative number")


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


@dataclass(frozen=True)
class NGRPolicy:
    target: str                                   # capability the candidate is meant to improve
    min_target_gain: float = 0.05
    default_epsilon: float = 0.02
    epsilons: "MappingProxyType[str, float]" = field(default_factory=lambda: MappingProxyType({}))
    critical: frozenset = frozenset()             # critical capabilities get epsilon = 0
    max_latency_ratio: float = 1.25               # candidate p95 latency may be at most 1.25x stable
    max_ram_ratio: float = 1.25

    # Phase 1 validation policy. Defaults preserve the old call sites; a promotion-critical
    # caller should switch on the requirements it actually has.
    score_range: tuple[float, float] = (0.0, 1.0)
    metric_schema: "MappingProxyType[str, MetricSpec]" = field(default_factory=lambda: MappingProxyType({}))
    required_capabilities: frozenset = frozenset()
    require_performance: bool = False
    required_performance: tuple[str, ...] = ("p95_ms", "peak_rss_mb")
    require_sample_counts: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("target capability must be a non-empty string")
        for name, value in (("min_target_gain", self.min_target_gain),
                            ("default_epsilon", self.default_epsilon),
                            ("max_latency_ratio", self.max_latency_ratio),
                            ("max_ram_ratio", self.max_ram_ratio)):
            if not _finite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.max_latency_ratio <= 0 or self.max_ram_ratio <= 0:
            raise ValueError("performance ratios must be positive")
        for capability, value in self.epsilons.items():
            if not isinstance(capability, str) or not capability.strip():
                raise ValueError("epsilon capability names must be non-empty strings")
            if not _finite(value) or value < 0:
                raise ValueError(f"epsilon for {capability!r} must be finite and non-negative")
        lo, hi = self.score_range
        if not (_finite(lo) and _finite(hi)) or lo > hi:
            raise ValueError("score_range must be finite and minimum <= maximum")
        for key in self.required_performance:
            if key not in {"p95_ms", "peak_rss_mb"}:
                raise ValueError(f"unsupported required performance metric {key!r}")

    def spec(self, capability: str) -> MetricSpec:
        return self.metric_schema.get(capability,
                                      MetricSpec(minimum=self.score_range[0], maximum=self.score_range[1]))

    def epsilon(self, capability: str) -> float:
        if capability in self.critical:
            return 0.0
        spec = self.metric_schema.get(capability)
        if spec is not None and spec.epsilon is not None:
            return spec.epsilon
        return self.epsilons.get(capability, self.default_epsilon)


@dataclass
class NGRResult:
    promote: bool
    reasons: list[str]
    deltas: dict[str, float]


def _validate_scores(policy: NGRPolicy, scores: dict[str, float], label: str, reasons: list[str]) -> None:
    for cap, value in scores.items():
        if not _finite(value):
            reasons.append(f"{label} score for {cap!r} is not a finite number: {value!r}")
            continue
        spec = policy.spec(cap)
        if not spec.minimum <= value <= spec.maximum:
            reasons.append(f"{label} score for {cap!r} ({value!r}) is outside "
                           f"[{spec.minimum}, {spec.maximum}]")


def _validate_samples(policy: NGRPolicy, stable_samples: dict[str, int] | None,
                      candidate_samples: dict[str, int] | None, capabilities: set[str],
                      reasons: list[str]) -> None:
    for label, counts in (("stable", stable_samples), ("candidate", candidate_samples)):
        if counts is None:
            continue
        for cap, count in counts.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                reasons.append(f"{label} sample count for {cap!r} is invalid: {count!r}")
    if not policy.require_sample_counts:
        return
    for cap in sorted(capabilities):
        spec = policy.spec(cap)
        for label, counts in (("stable", stable_samples), ("candidate", candidate_samples)):
            if counts is None or cap not in counts:
                reasons.append(f"{label} sample count missing for capability {cap!r}")
            elif isinstance(counts[cap], int) and counts[cap] < spec.min_samples:
                reasons.append(f"{label} sample count for {cap!r} is {counts[cap]} "
                               f"< required {spec.min_samples}")


def _validate_performance(policy: NGRPolicy, stable_perf: dict[str, float] | None,
                          candidate_perf: dict[str, float] | None, reasons: list[str]) -> None:
    for label, perf in (("stable", stable_perf), ("candidate", candidate_perf)):
        if perf is None:
            continue
        for key, value in perf.items():
            if not _finite(value) or value < 0:
                reasons.append(f"{label} performance metric {key!r} is invalid: {value!r}")

    if policy.require_performance:
        for key in policy.required_performance:
            if stable_perf is None or key not in stable_perf:
                reasons.append(f"stable performance metric {key!r} is missing")
            if candidate_perf is None or key not in candidate_perf:
                reasons.append(f"candidate performance metric {key!r} is missing")


def evaluate(policy: NGRPolicy, stable: dict[str, float], candidate: dict[str, float],
             stable_perf: dict[str, float] | None = None,
             candidate_perf: dict[str, float] | None = None,
             stable_samples: dict[str, int] | None = None,
             candidate_samples: dict[str, int] | None = None) -> NGRResult:
    reasons: list[str] = []

    _validate_scores(policy, stable, "stable", reasons)
    _validate_scores(policy, candidate, "candidate", reasons)
    _validate_performance(policy, stable_perf, candidate_perf, reasons)

    required = set(stable) | set(policy.required_capabilities) | {policy.target}
    missing = sorted(required - set(candidate))
    if missing:
        reasons.append(f"candidate was not evaluated on: {missing}")
    missing_baseline = sorted(set(policy.required_capabilities) - set(stable))
    if missing_baseline:
        reasons.append(f"required capabilities missing from the stable baseline: {missing_baseline}")

    _validate_samples(policy, stable_samples, candidate_samples, set(stable) & set(candidate), reasons)

    # Deltas are diagnostic only; non-finite inputs are omitted rather than poisoning the report.
    deltas: dict[str, float] = {}
    for cap, base in stable.items():
        if cap in candidate and _finite(base) and _finite(candidate[cap]):
            deltas[cap] = candidate[cap] - base

    if policy.target not in candidate or policy.target not in stable:
        reasons.append(f"target capability {policy.target!r} missing from scores")
    else:
        base, cand = stable[policy.target], candidate[policy.target]
        if _finite(base) and _finite(cand):
            spec = policy.spec(policy.target)
            gain = (cand - base) if spec.direction == "higher" else (base - cand)
            if gain < policy.min_target_gain:
                reasons.append(f"target gain {gain:+.3f} < required {policy.min_target_gain:.3f}")

    for cap, base in stable.items():
        if cap == policy.target or cap not in candidate:
            continue
        cand = candidate[cap]
        if not (_finite(base) and _finite(cand)):
            continue
        spec = policy.spec(cap)
        eps = policy.epsilon(cap)
        if spec.direction == "higher" and cand < base - eps:
            reasons.append(f"regression on {cap}: {base:.3f} -> {cand:.3f} (eps {eps})")
        elif spec.direction == "lower" and cand > base + eps:
            reasons.append(f"regression on {cap}: {base:.3f} -> {cand:.3f} (eps {eps}, lower is better)")

    for key, ratio in (("p95_ms", policy.max_latency_ratio), ("peak_rss_mb", policy.max_ram_ratio)):
        if not (stable_perf and candidate_perf):
            continue
        if key not in stable_perf or key not in candidate_perf:
            continue
        base, cand = stable_perf[key], candidate_perf[key]
        if _finite(base) and _finite(cand) and base > 0 and cand > base * ratio:
            reasons.append(f"{key} {base:.1f} -> {cand:.1f} exceeds x{ratio}")

    return NGRResult(promote=not reasons, reasons=reasons or ["all promotion conditions met"], deltas=deltas)
