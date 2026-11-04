import pytest

from evaluation.ngr import MetricSpec, NGRPolicy, evaluate

STABLE = {"arith": 0.90, "facts": 0.80, "new_skill": 0.30}


def test_promote_when_target_improves_and_nothing_regresses():
    r = evaluate(NGRPolicy("new_skill"), STABLE, {"arith": 0.90, "facts": 0.79, "new_skill": 0.60})
    assert r.promote


def test_reject_on_regression_beyond_epsilon():
    r = evaluate(NGRPolicy("new_skill"), STABLE, {"arith": 0.80, "facts": 0.80, "new_skill": 0.90})
    assert not r.promote and any("arith" in s for s in r.reasons)


def test_critical_capability_has_zero_tolerance():
    p = NGRPolicy("new_skill", critical=frozenset({"arith"}))
    assert not evaluate(p, STABLE, {"arith": 0.89, "facts": 0.80, "new_skill": 0.9}).promote


def test_reject_when_target_gain_not_meaningful():
    assert not evaluate(NGRPolicy("new_skill"), STABLE, {"arith": 0.9, "facts": 0.8, "new_skill": 0.31}).promote


def test_reject_when_capability_not_evaluated():
    assert not evaluate(NGRPolicy("new_skill"), STABLE, {"arith": 0.9, "new_skill": 0.9}).promote


def test_reject_on_latency_blowup():
    r = evaluate(NGRPolicy("new_skill"), STABLE, {"arith": 0.9, "facts": 0.8, "new_skill": 0.9},
                 {"p95_ms": 100, "peak_rss_mb": 500}, {"p95_ms": 200, "peak_rss_mb": 500})
    assert not r.promote


def test_policy_is_frozen():
    with pytest.raises(Exception):
        NGRPolicy("x").default_epsilon = 0.5


# ---- Phase 1 P09-P11: invalid and incomplete evidence must not promote ----
def test_nan_scores_are_rejected():
    r = evaluate(NGRPolicy("new_skill"), {**STABLE, "arith": float("nan")},
                 {"arith": 0.9, "facts": 0.8, "new_skill": 0.9})
    assert not r.promote and any("not a finite" in s for s in r.reasons)
    r = evaluate(NGRPolicy("new_skill"), STABLE,
                 {"arith": 0.9, "facts": 0.8, "new_skill": float("nan")})
    assert not r.promote and any("not a finite" in s for s in r.reasons)


def test_infinite_scores_are_rejected():
    r = evaluate(NGRPolicy("new_skill"), STABLE,
                 {"arith": 0.9, "facts": 0.8, "new_skill": float("inf")})
    assert not r.promote
    r = evaluate(NGRPolicy("new_skill"), STABLE,
                 {"arith": 0.9, "facts": 0.8, "new_skill": float("-inf")})
    assert not r.promote


def test_out_of_range_scores_are_rejected():
    r = evaluate(NGRPolicy("new_skill"), STABLE,
                 {"arith": 1.2, "facts": 0.8, "new_skill": 0.9})
    assert not r.promote and any("outside" in s for s in r.reasons)


def test_required_capability_must_be_measured():
    p = NGRPolicy("new_skill", required_capabilities=frozenset({"safety"}))
    r = evaluate(p, {**STABLE, "safety": 0.9},
                 {"arith": 0.9, "facts": 0.8, "new_skill": 0.9})
    assert not r.promote and any("safety" in s for s in r.reasons)
    r = evaluate(p, STABLE, {"arith": 0.9, "facts": 0.8, "new_skill": 0.9, "safety": 0.9})
    assert not r.promote and any("baseline" in s and "safety" in s for s in r.reasons)


def test_performance_is_required_when_the_policy_demands_it():
    p = NGRPolicy("new_skill", require_performance=True)
    scores = {"arith": 0.9, "facts": 0.8, "new_skill": 0.9}
    r = evaluate(p, STABLE, scores, {"p95_ms": 100}, {"p95_ms": 100})
    assert not r.promote and any("peak_rss_mb" in s for s in r.reasons)
    r = evaluate(p, STABLE, scores, {"p95_ms": 100, "peak_rss_mb": 500},
                 {"p95_ms": 100, "peak_rss_mb": 500})
    assert r.promote, r.reasons


def test_invalid_performance_values_are_rejected():
    r = evaluate(NGRPolicy("new_skill"), STABLE,
                 {"arith": 0.9, "facts": 0.8, "new_skill": 0.9},
                 {"p95_ms": 100, "peak_rss_mb": 500},
                 {"p95_ms": float("nan"), "peak_rss_mb": -1})
    assert not r.promote and any("invalid" in s for s in r.reasons)


def test_sample_counts_can_be_required_and_validated():
    p = NGRPolicy("new_skill", require_sample_counts=True,
                  metric_schema={"arith": MetricSpec(min_samples=10)})
    scores = {"arith": 0.9, "facts": 0.8, "new_skill": 0.9}
    r = evaluate(p, STABLE, scores,
                 stable_samples={"arith": 10, "facts": 10}, candidate_samples={"arith": 10, "facts": 10})
    assert not r.promote and any("new_skill" in s for s in r.reasons)
    r = evaluate(p, STABLE, scores,
                 stable_samples={"arith": 10, "facts": 10, "new_skill": 10},
                 candidate_samples={"arith": 9, "facts": 10, "new_skill": 10})
    assert not r.promote and any("arith" in s and "sample count" in s for s in r.reasons)


def test_lower_is_better_metric_direction():
    p = NGRPolicy("new_skill", metric_schema={
        "error": MetricSpec(minimum=0.0, maximum=100.0, direction="lower"),
    })
    r = evaluate(p, {"error": 10.0, "new_skill": 0.3},
                 {"error": 20.0, "new_skill": 0.9})
    assert not r.promote and any("error" in s for s in r.reasons)
