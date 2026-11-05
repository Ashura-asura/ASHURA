"""NGR policy itself is trusted input to the promotion gate and must be validated."""
import pytest

from evaluation.ngr import NGRPolicy, evaluate


@pytest.mark.parametrize("kwargs", [
    {"min_target_gain": float("nan")},
    {"min_target_gain": float("inf")},
    {"default_epsilon": float("nan")},
    {"epsilons": {"old_skill": float("nan")}},
    {"epsilons": {"old_skill": -0.1}},
    {"max_latency_ratio": float("nan")},
    {"max_ram_ratio": float("inf")},
    {"max_latency_ratio": 0.0},
    {"target": ""},
])
def test_ngr_rejects_invalid_policy_thresholds(kwargs):
    target = kwargs.get("target", "target")
    options = {key: value for key, value in kwargs.items() if key != "target"}
    with pytest.raises(ValueError):
        NGRPolicy(target, **options)


def test_nan_epsilon_cannot_disable_non_regression():
    stable = {"old": 0.9, "target": 0.2}
    candidate = {"old": 0.1, "target": 0.9}
    # NaN is rejected at policy construction, rather than making the comparison silently false.
    with pytest.raises(ValueError):
        NGRPolicy("target", epsilons={"old": float("nan")})
    assert not evaluate(NGRPolicy("target"), stable, candidate).promote
