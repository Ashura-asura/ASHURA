import pytest

from evaluation.ngr import NGRPolicy, NGRResult
from learning.dream import DREAM, DreamConfig
from learning.replay import ReplayBuffer, ReplayItem
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from plasticity.slow_weights import CheckpointStore


def build_buffer():
    b = ReplayBuffer()
    for i, (name, value) in enumerate([("alpha", "red"), ("bravo", "blue"), ("charlie", "green")]):
        b.add(ReplayItem(f"new-{i}", f"{name} one", value, category="new", verified=True))
        b.add(ReplayItem(f"new-h-{i}", f"one {name}", value, category="new", verified=True, split="heldout"))
        b.add(ReplayItem(f"old-{i}", f"{name} old", f"old-{value}", category="old", verified=True))
        b.add(ReplayItem(f"old-h-{i}", f"old {name}", f"old-{value}", category="old", verified=True, split="heldout"))
    return b


def cold_baseline(tmp_path, dim=128):
    """An independently evaluated (untrained) reference artifact, not a fabricated zero dict."""
    path = tmp_path / "cold_baseline.npz"
    AdaptiveMemory(AMemConfig(dim_k=dim, dim_v=dim, seed=0)).save(str(path))
    return str(path)


def seed_stable(store, buffer, tmp_path, dim=128):
    mem = AdaptiveMemory(AMemConfig(dim_k=dim, dim_v=dim, seed=0))
    for it in buffer.training_set():
        if it.category == "old":
            mem.write(it.key, it.value)
    path = tmp_path / "old_memory.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    mem.save(str(path))
    store.stage(path, "old_memory.npz")
    store.promote("old_memory.npz", NGRResult(True, ["fixture: stable old-capability memory"], {}))


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
    d = DREAM(build_buffer(), store, NGRPolicy("new"),
              DreamConfig(target="new", dim=128, min_train=4,
                          cold_start_checkpoint=cold_baseline(tmp_path)))
    first = d.run()
    assert first.promoted, first.reasons
    assert first.cold_start
    assert store.current().name == first.candidate
    with pytest.raises(RuntimeError):
        store.rollback()          # first stable has no parent; rollback is tested in test_dpf.py


def test_dream_rejects_candidate_that_forgets_old_capability(tmp_path):
    store = CheckpointStore(tmp_path)
    d = DREAM(build_buffer(), store, NGRPolicy("new"),
              DreamConfig(target="new", dim=128, min_train=4,
                          cold_start_checkpoint=cold_baseline(tmp_path)))
    good = d.run()
    assert good.promoted

    class Forgetful(DREAM):
        def score(self, mem, items, vocabulary=None):
            return {"new": 1.0, "old": 0.0}

    bad = Forgetful(build_buffer(), store, NGRPolicy("new"),
                    DreamConfig(target="new", dim=128, min_train=4)).run()
    assert not bad.promoted
    assert store.current().name == good.candidate


# ---- Phase 1 P12-P14 ----------------------------------------------------------------
def test_dream_refuses_a_fake_zero_baseline(tmp_path):
    store = CheckpointStore(tmp_path)
    d = DREAM(build_buffer(), store, NGRPolicy("new"),
              DreamConfig(target="new", dim=128, min_train=4, initialization="fresh"))
    with pytest.raises(ValueError, match="cold-start baseline"):
        d.run()


def test_stable_initialization_retains_old_capability_where_fresh_does_not(tmp_path):
    buffer = build_buffer()
    fresh_store = CheckpointStore(tmp_path / "fresh")
    seed_stable(fresh_store, buffer, tmp_path / "fresh_seed")
    fresh = DREAM(build_buffer(), fresh_store, NGRPolicy("new"),
                  DreamConfig(target="new", dim=128, min_train=3, replay=False,
                              initialization="fresh")).run()
    assert fresh.scores["new"] == 1.0
    assert fresh.scores["old"] == 0.0
    assert not fresh.promoted

    stable_store = CheckpointStore(tmp_path / "stable")
    seed_stable(stable_store, buffer, tmp_path / "stable_seed")
    stable = DREAM(build_buffer(), stable_store, NGRPolicy("new"),
                   DreamConfig(target="new", dim=128, min_train=3, replay=False,
                               initialization="stable")).run()
    assert stable.scores["new"] == 1.0
    assert stable.scores["old"] == 1.0          # the stable model's old associations survived
    assert stable.promoted


def test_answer_vocabulary_comes_from_training_not_heldout(tmp_path):
    b = build_buffer()
    b.add(ReplayItem("new-h-extra", "extra key", "magenta", category="new",
                     verified=True, split="heldout"))
    d = DREAM(b, CheckpointStore(tmp_path), NGRPolicy("new"), DreamConfig(target="new", dim=128))
    vocab = d.answer_vocabulary()
    assert "magenta" not in vocab
    assert set(vocab) == {"red", "blue", "green", "old-red", "old-blue", "old-green"}


def test_explicit_answer_vocabulary_is_fixed_before_evaluation(tmp_path):
    b = build_buffer()
    d = DREAM(b, CheckpointStore(tmp_path), NGRPolicy("new"),
              DreamConfig(target="new", dim=128, answer_vocabulary=("red", "blue", "green")))
    assert d.answer_vocabulary() == ("red", "blue", "green")


def test_stable_initialization_without_a_stable_checkpoint_is_an_error(tmp_path):
    d = DREAM(build_buffer(), CheckpointStore(tmp_path), NGRPolicy("new"),
              DreamConfig(target="new", dim=128, min_train=4, initialization="stable"))
    with pytest.raises(ValueError, match="stable checkpoint"):
        d.run()
