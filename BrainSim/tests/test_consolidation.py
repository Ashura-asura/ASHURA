"""Tests for B4 replay, persistent fine-tuning and checkpointed retention."""
import copy

import pytest
import torch

from brainsim.learning.finetune import finetune
from brainsim.learning.replay import ReplayBuffer, ReplayConfig
from brainsim.learning.train import (TrainConfig, build_model, load_checkpoint,
                                     sequence_accuracy, train_offline)
from experiments.b4_consolidation import rule_sequences, run_seed, summarise


def test_replay_buffer_bounds_and_is_deterministic():
    buf = ReplayBuffer(ReplayConfig(capacity=3))
    buf.add(torch.tensor([[0, 1], [2, 3]]))
    assert len(buf) == 2
    a = buf.sample(5, generator=torch.Generator().manual_seed(7))
    b = buf.sample(5, generator=torch.Generator().manual_seed(7))
    assert torch.equal(a, b)
    buf.add(torch.tensor([[4, 5], [6, 7], [8, 9]]))
    assert len(buf) == 3                     # oldest rows were evicted
    with pytest.raises(ValueError):
        ReplayBuffer(ReplayConfig(capacity=0))


def test_replay_buffer_rejects_non_2d_input_and_bad_sample_size():
    buf = ReplayBuffer(ReplayConfig(capacity=3))
    with pytest.raises(ValueError):
        buf.add(torch.tensor([1, 2, 3]))
    with pytest.raises(ValueError):
        buf.sample(1)                        # empty buffer
    buf.add(torch.tensor([[0, 1]]))
    with pytest.raises(ValueError):
        buf.sample(0)


def test_finetune_rejects_invalid_replay_ratio():
    model = build_model(4, TrainConfig(hidden=8, layers=1, seed=0))
    with pytest.raises(ValueError):
        finetune(model, torch.tensor([[0, 1, 2]]), TrainConfig(hidden=8, layers=1, seed=0),
                 epochs=1, replay_ratio=1.0)


def _small_pair():
    def walk(rule, start, length=12):
        out = [start]
        for _ in range(length - 1):
            out.append(rule[out[-1]])
        return out

    old_rule, new_rule = (1, 2, 3, 0), (2, 1, 3, 0)
    old = torch.tensor([walk(old_rule, i % 4) for i in range(32)])
    new = torch.tensor([walk(new_rule, i % 4) for i in range(32)])
    old_val = torch.tensor([walk(old_rule, (i + 2) % 4) for i in range(16)])
    new_val = torch.tensor([walk(new_rule, (i + 2) % 4) for i in range(16)])
    return old, new, old_val, new_val


def test_empty_replay_matches_no_replay_exactly():
    old, new, _, _ = _small_pair()
    cfg = TrainConfig(hidden=16, layers=1, epochs=2, batch_size=8, seed=0)
    base = build_model(4, cfg)
    train_offline(base, old, cfg)
    left, right = copy.deepcopy(base), copy.deepcopy(base)
    h1, _ = finetune(left, new, cfg, epochs=2, batch_size=8, seed=0)
    empty = ReplayBuffer(ReplayConfig(capacity=8))
    h2, _ = finetune(right, new, cfg, epochs=2, batch_size=8, replay=empty,
                     replay_ratio=0.5, seed=0)
    assert h1["loss"] == h2["loss"]
    assert all(torch.equal(a, b) for a, b in zip(left.parameters(), right.parameters()))


def test_replay_changes_optimisation_and_checkpoint_round_trips(tmp_path):
    old, new, old_val, new_val = _small_pair()
    cfg = TrainConfig(hidden=32, layers=1, epochs=16, batch_size=8, lr=5e-3, seed=0)
    base = build_model(4, cfg)
    train_offline(base, old, cfg)

    no_replay = copy.deepcopy(base)
    with_replay = copy.deepcopy(base)
    h1, _ = finetune(no_replay, new, cfg, epochs=16, batch_size=8, lr=5e-3, seed=0,
                     checkpoint=tmp_path / "new_only.pt")
    buffer = ReplayBuffer(ReplayConfig(capacity=64))
    buffer.add(old)
    h2, _ = finetune(with_replay, new, cfg, epochs=16, batch_size=8, lr=5e-3, seed=0,
                     replay=buffer, replay_ratio=0.5,
                     checkpoint=tmp_path / "replay.pt")

    assert h1["loss"] != h2["loss"]          # replay actually enters the updates
    assert sequence_accuracy(with_replay, old_val) >= sequence_accuracy(no_replay, old_val) - 0.02
    assert sequence_accuracy(with_replay, new_val) >= 0.8

    reloaded = load_checkpoint(tmp_path / "replay.pt")
    assert sequence_accuracy(reloaded, old_val) == sequence_accuracy(with_replay, old_val)
    assert sequence_accuracy(reloaded, new_val) == sequence_accuracy(with_replay, new_val)


def test_run_seed_reports_checkpointed_arms(tmp_path):
    run = run_seed(seed=0, base_epochs=1, finetune_epochs=1, checkpoint_dir=tmp_path)
    assert run["params"] > 0 and 0.0 <= run["base"]["old_accuracy"] <= 1.0
    for arm in ("new_only", "replay"):
        result = run["arms"][arm]
        assert result["checkpoint_roundtrip"]
        assert 0.0 <= result["old_accuracy"] <= 1.0
        assert 0.0 <= result["new_accuracy"] <= 1.0
        assert result["old_examples_seen"] == (0 if arm == "new_only" else 256)
    summary = summarise([run])
    assert summary["seeds"] == 1
    assert summary["new_only_checkpoint_roundtrip_count"] == 1
    assert summary["replay_checkpoint_roundtrip_count"] == 1


def test_rule_sequences_shape_and_disjoint_rules():
    from brainsim.environment.sequence_tasks import SequenceConfig, make_rules

    cfg = SequenceConfig(seed=0)
    rules = make_rules(cfg)
    old = rule_sequences(rules.train, 2, cfg.seq_len, seed=11)
    new = rule_sequences(rules.heldout, 2, cfg.seq_len, seed=12)
    assert old.shape == (2 * len(rules.train), cfg.seq_len)
    assert new.shape == (2 * len(rules.heldout), cfg.seq_len)
    assert set(rules.train) & set(rules.heldout) == set()
    # Every adjacent pair must be a transition of some rule in the selected set.
    allowed = {tuple(rule) for rule in rules.train}
    for row in old:
        assert any(all(int(row[t + 1]) == rule[int(row[t])]
                       for t in range(len(row) - 1)) for rule in allowed)
