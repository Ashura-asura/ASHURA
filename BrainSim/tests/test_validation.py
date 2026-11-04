"""Tests for B6: fixed in-context baseline, episode training and gated-memory revisit."""
import torch

from brainsim.core.fixed_baseline import FixedEpisodeMLP
from brainsim.environment.sequence_tasks import SequenceConfig, make_rules
from brainsim.learning.episode_train import (evaluate_fixed_episode, make_episode_pairs,
                                             train_fixed_episode)
from brainsim.memory.gated_memory import GatedMemoryConfig, TaskScopedMemory
from experiments.b6_validation import run_seed


def test_fixed_episode_model_shape_and_parameter_count():
    model = FixedEpisodeMLP(vocab=16, study_len=12, test_len=16, hidden=220)
    assert model.param_count == 207_496
    study = torch.zeros(4, 13, dtype=torch.long)
    test = torch.zeros(4, 17, dtype=torch.long)
    logits = model(study, test)
    assert logits.shape == (4, 16, 16)
    manual = ((13 + 16) * 16 * 220 + 220) + (220 * 220 + 220) + (220 * 16 * 16 + 16 * 16)
    assert model.param_count == manual


def test_make_episode_pairs_uses_disjoint_rules():
    cfg = SequenceConfig(seed=0)
    rules = make_rules(cfg)
    study, test = make_episode_pairs(rules.heldout, 3, cfg.study_len, cfg.test_len, seed=5)
    assert study.shape == (3 * len(rules.heldout), cfg.study_len + 1)
    assert test.shape == (3 * len(rules.heldout), cfg.test_len + 1)
    allowed = {tuple(rule) for rule in rules.heldout}
    for row in list(study) + list(test):
        assert any(all(int(row[t + 1]) == rule[int(row[t])]
                       for t in range(len(row) - 1)) for rule in allowed)


def test_fixed_training_reduces_loss_and_evaluates():
    # One deterministic 4-cycle: easy enough for a tiny CPU-only smoke test.
    rule = (1, 2, 3, 0)
    study = torch.tensor([[0, 1, 2, 3, 0, 1]] * 16)
    test = torch.tensor([[0, 1, 2, 3, 0, 1, 2, 3]] * 16)
    torch.manual_seed(0)
    model = FixedEpisodeMLP(vocab=4, study_len=5, test_len=7, hidden=32)
    history, seconds = train_fixed_episode(model, study, test, epochs=20, batch=8, seed=0)
    assert len(history["loss"]) == 20 and seconds >= 0
    assert history["loss"][-1] < history["loss"][0]
    metrics = evaluate_fixed_episode(model, study, test)
    assert 0.0 <= metrics["token_accuracy"] <= 1.0
    assert 0.0 <= metrics["full_recall_accuracy"] <= 1.0
    assert metrics["token_accuracy"] > 0.9       # one visible cycle is trivially learnable


def test_task_scoped_memory_blend_and_size():
    model_logits = torch.zeros(1, 4)
    keys = torch.tensor([2])
    memory = TaskScopedMemory(GatedMemoryConfig(vocab=4, key_mode="token", max_tasks=4))
    unknown = memory.blend("rule0", model_logits, keys)
    assert torch.allclose(unknown, torch.full((1, 4), 0.25))
    assert memory.size_bytes == 0

    result = memory.update("rule0", 2, 3, verified=True)
    assert result["admitted"]
    assert memory.size_bytes > 0
    blended = memory.blend("rule0", model_logits, keys)
    assert blended.shape == model_logits.shape
    assert float(blended[0, 3]) > 0.25
    # The memory is task-scoped: another task cannot see it.
    other = memory.blend("rule1", model_logits, keys)
    assert torch.allclose(other, unknown)


def test_run_seed_arms_and_revisit_consistency():
    run = run_seed(seed=0, epochs=1, fixed_epochs=1, episodes_per_rule=1)
    assert run["params"]["gru"] > 0 and run["params"]["fixed"] == 207_496
    for arm in ("fixed", "recurrent"):
        assert 0.0 <= run["arms"][arm]["token_accuracy"] <= 1.0
        assert 0.0 <= run["arms"][arm]["full_recall_accuracy"] <= 1.0
    for arm in ("fast_memory", "gated_memory"):
        for phase in ("test", "revisit"):
            assert 0.0 <= run["arms"][arm][phase]["token_accuracy"] <= 1.0
    gated = run["arms"]["gated_memory"]
    assert abs(gated["retention_gap"]) < 1e-9     # no new study, same task memory
    assert gated["tasks"] == 8
    assert run["arms"]["fast_memory"]["memory_rows"] == 16
