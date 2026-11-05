"""Production-hardening regressions for BrainSim persistence and input validation."""
from __future__ import annotations

import pytest
import torch

from brainsim.core.model import BrainSim, BrainSimConfig
from brainsim.learning.train import TrainConfig, load_checkpoint, save_checkpoint, train_offline
from brainsim.memory.fast_memory import FastAssociativeMemory, FastMemoryConfig


@pytest.mark.parametrize("kwargs", [
    {"decay": 1.01}, {"decay": float("nan")}, {"eta": 1.01},
    {"eta": 0.0}, {"blend": float("inf")}, {"surprise_threshold": -0.1},
])
def test_fast_memory_rejects_unstable_or_nonfinite_config(kwargs):
    with pytest.raises(ValueError):
        FastMemoryConfig(vocab=8, **kwargs)


@pytest.mark.parametrize("tokens", [
    torch.tensor([1.5, 2.0]), torch.tensor([float("nan"), 2.0]),
    torch.tensor([True, False]), torch.tensor([-1, 2]), torch.tensor([0, 8]),
])
def test_fast_memory_rejects_noninteger_or_out_of_range_tokens(tokens):
    mem = FastAssociativeMemory(FastMemoryConfig(vocab=8))
    with pytest.raises(ValueError):
        mem.update(tokens, torch.tensor([1, 2]))


def test_fast_memory_checkpoint_requires_matching_config(tmp_path):
    mem = FastAssociativeMemory(FastMemoryConfig(vocab=8, key_mode="pair"))
    path = mem.save(tmp_path / "memory.pt")
    with pytest.raises(ValueError, match="config"):
        FastAssociativeMemory.load(path, FastMemoryConfig(vocab=8, key_mode="token"))


def test_fast_memory_checkpoint_rejects_nonfinite_state(tmp_path):
    mem = FastAssociativeMemory(FastMemoryConfig(vocab=8))
    path = mem.save(tmp_path / "memory.pt")
    data = torch.load(path, map_location="cpu", weights_only=True)
    data["M"][0, 0] = float("nan")
    torch.save(data, path)
    with pytest.raises(ValueError, match="non-finite"):
        FastAssociativeMemory.load(path)


@pytest.mark.parametrize("kwargs", [
    {"epochs": 0}, {"batch_size": 0}, {"lr": float("nan")},
    {"weight_decay": -1.0}, {"grad_clip": float("inf")}, {"hidden": 0},
])
def test_train_config_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        TrainConfig(**kwargs)


@pytest.mark.parametrize("tokens", [
    torch.tensor([[0, 1, 2.5]]), torch.tensor([[0, 1, float("nan")]]),
    torch.tensor([[0, 1, 8]]), torch.tensor([[-1, 1, 2]]),
    torch.tensor([[1]]), torch.empty((0, 3), dtype=torch.long),
])
def test_training_rejects_invalid_sequences_before_mutating_model(tokens):
    model = BrainSim(BrainSimConfig(vocab=8, hidden=8, layers=1, in_dim=17))
    with pytest.raises(ValueError):
        train_offline(model, tokens, TrainConfig(hidden=8, layers=1, epochs=1, batch_size=2))


def test_training_checkpoint_is_roundtrip_loadable(tmp_path):
    model = BrainSim(BrainSimConfig(vocab=8, hidden=8, layers=1, in_dim=17))
    path = save_checkpoint(model, tmp_path / "model.pt", cfg=TrainConfig(hidden=8, layers=1))
    loaded = load_checkpoint(path)
    assert loaded.cfg == model.cfg
    assert all(torch.equal(a, b) for a, b in zip(model.state_dict().values(),
                                                 loaded.state_dict().values()))
