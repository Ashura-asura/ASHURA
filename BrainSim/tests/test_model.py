"""Tests for the BrainSim core, encoder and offline training loop."""
import torch

from brainsim.core.encoder import encode
from brainsim.core.model import BrainSim, BrainSimConfig
from brainsim.learning.train import (TrainConfig, build_model, load_checkpoint,
                                     sequence_accuracy, train_offline)


def test_forward_shapes():
    cfg = BrainSimConfig(vocab=10, hidden=32, layers=2, in_dim=21)
    model = BrainSim(cfg)
    x = torch.randn(4, 7, cfg.in_dim)
    out = model(x)
    assert out.logits.shape == (4, 7, 10)
    assert out.need.shape == (4, 7, cfg.n_needs)
    assert out.action.shape == (4, 7, cfg.n_actions)
    assert out.confidence.shape == (4, 7, 1)
    assert out.hidden.shape == (4, 7, 32)
    assert float(out.confidence.min()) >= 0.0 and float(out.confidence.max()) <= 1.0


def test_encoder_is_one_hot_with_previous_token_and_resource():
    tokens = torch.tensor([[0, 2, 1]])
    z = encode(tokens, vocab=4, resource=0.5)
    assert z.shape == (1, 3, 9)
    assert bool(z[0, 0, 0]) and z[0, 0, 4:8].sum() == 0     # no previous token at t=0
    assert bool(z[0, 1, 2]) and bool(z[0, 1, 4 + 0])        # token 2, previous 0
    assert torch.allclose(z[..., -1], torch.full((1, 3), 0.5))


def test_parameter_count_is_small_and_configurable():
    small = BrainSim(BrainSimConfig(vocab=16, hidden=64, in_dim=33))
    large = BrainSim(BrainSimConfig(vocab=16, hidden=128, in_dim=33))
    assert 0 < small.param_count < large.param_count


def test_build_model_is_seeded():
    a = build_model(8, TrainConfig(hidden=16, seed=3))
    b = build_model(8, TrainConfig(hidden=16, seed=3))
    assert all(torch.equal(x, y) for x, y in zip(a.parameters(), b.parameters()))


def test_training_runs_and_checkpoint_round_trips(tmp_path):
    torch.manual_seed(0)
    tokens = torch.tensor([[0, 1, 2, 3, 0, 1, 2, 3]] * 8)
    cfg = TrainConfig(hidden=16, layers=1, epochs=2, batch_size=4, seed=0,
                      checkpoint=tmp_path / "model.pt")
    model = build_model(4, cfg)
    history, seconds = train_offline(model, tokens, cfg, val_tokens=tokens)
    assert len(history["loss"]) == 2 and seconds >= 0
    assert 0.0 <= history["val_acc"][-1] <= 1.0
    loaded = load_checkpoint(tmp_path / "model.pt")
    assert sequence_accuracy(loaded, tokens) == sequence_accuracy(model, tokens)
