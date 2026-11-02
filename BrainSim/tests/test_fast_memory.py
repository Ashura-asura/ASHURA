"""Tests for the isolated fast associative memory."""
import pytest
import torch

from brainsim.memory.fast_memory import FastAssociativeMemory, FastMemoryConfig


def memory(**kw) -> FastAssociativeMemory:
    return FastAssociativeMemory(FastMemoryConfig(vocab=8, **kw))


def test_single_observation_is_stored_and_recalled():
    mem = memory()
    surprises = mem.update(torch.tensor([2]), torch.tensor([5]))
    assert surprises[0] > 0 and mem.seen_keys == 1
    assert bool(mem.seen(torch.tensor([2])))
    assert int(mem.scores(torch.tensor([2])).argmax()) == 5
    assert not bool(mem.seen(torch.tensor([3])))


def test_blend_only_changes_seen_keys():
    mem = memory(blend=1.0)
    mem.update(torch.tensor([1]), torch.tensor([4]))
    model_logits = torch.zeros(3, 8)
    probs = mem.blend(model_logits, torch.tensor([1, 2, 3]))
    assert int(probs[0].argmax()) == 4          # memory row overrides the model
    assert torch.allclose(probs[1], torch.softmax(model_logits[1], dim=-1))
    assert torch.allclose(probs[2], torch.softmax(model_logits[2], dim=-1))


def test_apply_mask_scopes_memory_to_the_current_task():
    mem = memory(blend=1.0)
    mem.update(torch.tensor([1]), torch.tensor([4]))
    model_logits = torch.zeros(1, 8)
    probs = mem.blend(model_logits, torch.tensor([1]), apply_mask=torch.tensor([False]))
    assert torch.allclose(probs[0], torch.softmax(model_logits[0], dim=-1))


def test_surprise_threshold_skips_known_transitions():
    mem = memory(surprise_threshold=0.5)
    assert mem.update(torch.tensor([3]), torch.tensor([6]))[0] > 0
    assert mem.update(torch.tensor([3]), torch.tensor([6]))[0] < 1e-6
    assert mem.counts[3] == 1                  # the known transition was not written again


def test_decay_and_eta_are_bounded_updates():
    mem = memory(decay=0.5, eta=0.5)
    mem.update(torch.tensor([0]), torch.tensor([7]))
    row = mem.scores(torch.tensor([0]))[0]
    assert 0.0 < float(row[7]) < 1.0           # partial update, not a hard one-hot


def test_reset_clears_everything():
    mem = memory()
    mem.update(torch.tensor([0, 1]), torch.tensor([2, 3]))
    mem.reset()
    assert mem.seen_keys == 0 and float(mem.M.abs().sum()) == 0.0


def test_save_load_round_trip(tmp_path):
    mem = memory()
    mem.update(torch.tensor([2, 4]), torch.tensor([5, 1]))
    path = mem.save(tmp_path / "fast.pt")
    loaded = FastAssociativeMemory.load(path)
    assert torch.equal(mem.M, loaded.M)
    assert torch.equal(mem.counts, loaded.counts)
    assert int(loaded.scores(torch.tensor([2])).argmax()) == 5


def test_invalid_tokens_are_rejected():
    mem = memory()
    with pytest.raises(ValueError):
        mem.update(torch.tensor([8]), torch.tensor([0]))
    with pytest.raises(ValueError):
        mem.blend(torch.zeros(1, 8), torch.tensor([-1]))


def test_pair_keys_separate_the_same_token_in_different_contexts():
    mem = FastAssociativeMemory(FastMemoryConfig(vocab=8, key_mode="pair"))
    mem.update(torch.tensor([2]), torch.tensor([5]), prev=torch.tensor([1]))
    assert bool(mem.seen(torch.tensor([2]), prev=torch.tensor([1])))
    assert not bool(mem.seen(torch.tensor([2]), prev=torch.tensor([3])))
    assert int(mem.scores(torch.tensor([2]), prev=torch.tensor([1])).argmax()) == 5
    assert torch.allclose(mem.scores(torch.tensor([2]), prev=torch.tensor([3])),
                          torch.zeros(1, 8))
    with pytest.raises(ValueError):
        mem.update(torch.tensor([2]), torch.tensor([5]))    # prev is required


def test_config_validation():
    with pytest.raises(ValueError):
        FastMemoryConfig(vocab=1)
    with pytest.raises(ValueError):
        FastMemoryConfig(vocab=4, blend=1.5)
    with pytest.raises(ValueError):
        FastMemoryConfig(vocab=4, key_mode="hidden")
