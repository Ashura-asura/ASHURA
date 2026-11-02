import pytest

from evaluation.ngr import NGRPolicy, evaluate

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
