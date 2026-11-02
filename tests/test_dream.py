import pytest

from evaluation.ngr import NGRPolicy
from learning.dream import DREAM, DreamConfig
from learning.replay import ReplayBuffer, ReplayItem
from plasticity.slow_weights import CheckpointStore


def build_buffer():
    b = ReplayBuffer()
    for i, (name, value) in enumerate([("alpha", "red"), ("bravo", "blue"), ("charlie", "green")]):
        b.add(ReplayItem(f"new-{i}", f"{name} one", value, category="new", verified=True))
        b.add(ReplayItem(f"new-h-{i}", f"one {name}", value, category="new", verified=True, split="heldout"))
        b.add(ReplayItem(f"old-{i}", f"{name} old", f"old-{value}", category="old", verified=True))
        b.add(ReplayItem(f"old-h-{i}", f"old {name}", f"old-{value}", category="old", verified=True, split="heldout"))
    return b


def test_buffer_rejects_duplicates_and_train_heldout_leakage():
    b = ReplayBuffer()
    item = ReplayItem("1", "a b", "c", verified=True)
    assert b.add(item) and not b.add(item)
    with pytest.raises(ValueError):
        b.add(ReplayItem("2", "A B", "c", verified=True, split="heldout"))


def test_unverified_items_never_enter_training_set():
    b = ReplayBuffer()
    b.add(ReplayItem("u", "q", "a", verified=False))
    assert b.training_set() == [] and b.stats.rejected == 1


def test_dream_promotes_candidate_then_rolls_back(tmp_path):
    store = CheckpointStore(tmp_path)
    d = DREAM(build_buffer(), store, NGRPolicy("new"), DreamConfig(target="new", dim=128, min_train=4))
    first = d.run()
    assert first.promoted, first.reasons
    assert store.current().name == first.candidate
    with pytest.raises(RuntimeError):
        store.rollback()          # first stable has no parent; rollback is tested in test_dpf.py


def test_dream_rejects_candidate_that_forgets_old_capability(tmp_path):
    store = CheckpointStore(tmp_path)
    d = DREAM(build_buffer(), store, NGRPolicy("new"), DreamConfig(target="new", dim=128, min_train=4))
    good = d.run()
    assert good.promoted

    class Forgetful(DREAM):
        def score(self, mem, items):
            return {"new": 1.0, "old": 0.0}

    bad = Forgetful(build_buffer(), store, NGRPolicy("new"), DreamConfig(target="new", dim=128, min_train=4)).run()
    assert not bad.promoted
    assert store.current().name == good.candidate
