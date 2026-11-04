"""Tests for the B5 control environment, per-step resource encoding and training loop."""
import torch

from brainsim.core.encoder import encode
from brainsim.core.model import BrainSim, BrainSimConfig
from brainsim.environment.control_tasks import (ACTION_COSTS, ACTIONS, NEEDS, WAIT,
                                                 ControlConfig, baseline_action,
                                                 feasible_mask, make_episodes,
                                                 optimal_action, resolve_action,
                                                 utility_of)
from brainsim.learning.control_train import (ControlTrainConfig, evaluate_control,
                                             simulate_model, simulate_policy, train_control)


def test_encode_accepts_per_step_resource():
    tokens = torch.tensor([[0, 1, 2], [2, 1, 0]])
    resource = torch.tensor([[0.0, 0.5, 1.0], [1.0, 0.5, 0.0]])
    z = encode(tokens, vocab=3, resource=resource)
    assert z.shape == (2, 3, 7)
    assert torch.allclose(z[0, :, -1], resource[0])
    assert torch.allclose(z[1, :, -1], resource[1])
    one = encode(tokens, vocab=3, resource=torch.tensor([0.2, 0.8]))
    assert torch.allclose(one[0, :, -1], torch.full((3,), 0.2))
    try:
        encode(tokens, vocab=3, resource=torch.zeros(3, 2))
        assert False, "expected a shape error"
    except ValueError:
        pass


def test_finite_horizon_policy_waits_to_recover_budget():
    cfg = ControlConfig()
    # Need=retrieve, budget=1. The greedy action is predict (0.20), but waiting recovers one
    # budget point and allows the much better retrieve action later.
    assert optimal_action(1, 1, 0, cfg) == WAIT


def test_episodes_have_feasible_dp_targets():
    cfg = ControlConfig()
    batch = make_episodes(cfg, 64, seed=3)
    assert batch.tokens.shape == (64, cfg.episode_len)
    assert batch.resource.shape == batch.tokens.shape
    costs = torch.tensor(ACTION_COSTS, dtype=torch.long)
    assert bool((costs[batch.actions] <= batch.budgets).all())
    for t in range(cfg.episode_len):
        for i in range(len(batch)):
            assert int(batch.actions[i, t]) == optimal_action(
                int(batch.needs[i, t]), int(batch.budgets[i, t]), t, cfg)
    mask = feasible_mask(batch.budgets)
    assert mask.shape == (64, cfg.episode_len, len(ACTIONS))
    resolved, violation = resolve_action(torch.full((4,), 4), torch.tensor([0, 1, 4, 8]))
    assert resolved.tolist()[0] == WAIT and violation[0]
    assert not violation[2:].any()


def test_oracle_baseline_matches_episode_targets():
    cfg = ControlConfig()
    batch = make_episodes(cfg, 32, seed=4)
    for t in range(cfg.episode_len):
        predicted = baseline_action("oracle", batch.needs[:, t], batch.budgets[:, t],
                                    t=t, cfg=cfg)
        assert torch.equal(predicted, batch.actions[:, t])


def test_training_and_closed_loop_evaluation():
    cfg = ControlConfig()
    train_batch = make_episodes(cfg, 256, seed=10)
    eval_batch = make_episodes(cfg, 64, seed=11)
    torch.manual_seed(0)
    model = BrainSim(BrainSimConfig(vocab=len(NEEDS), hidden=32, layers=1,
                                    in_dim=2 * len(NEEDS) + 1,
                                    n_needs=len(NEEDS), n_actions=len(ACTIONS)))
    history, seconds = train_control(
        model, train_batch, ControlTrainConfig(epochs=5, batch_size=32, seed=0))
    assert len(history["loss"]) == 5 and seconds >= 0
    metrics = evaluate_control(model, eval_batch)
    assert 0.0 <= metrics["action_accuracy"] <= 1.0
    assert 0.0 <= metrics["need_accuracy"] <= 1.0
    assert 0.0 <= metrics["raw_infeasible_rate"] <= 1.0
    assert metrics["steps"] == len(eval_batch) * cfg.episode_len
    closed = simulate_model(model, eval_batch, cfg)
    assert 0.0 <= closed["action_accuracy"] <= 1.0
    assert "total_utility_per_episode" in closed
    oracle = simulate_policy(eval_batch, cfg, "oracle")
    wait = simulate_policy(eval_batch, cfg, "always_wait")
    assert oracle["total_utility_per_episode"] > wait["total_utility_per_episode"]
    assert oracle["infeasible_rate"] == 0.0


def test_utility_table_and_actions_are_consistent():
    assert len(NEEDS) == 4 and len(ACTIONS) == 6 and len(ACTION_COSTS) == 6
    needs = torch.tensor([0, 1, 2, 3])
    actions = torch.tensor([0, 1, 2, 3])
    assert torch.allclose(utility_of(needs, actions), torch.tensor([0.9, 0.9, 0.9, 0.9]))
