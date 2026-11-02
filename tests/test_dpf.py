import hashlib
from pathlib import Path

import pytest

from evaluation.ngr import NGRResult
from plasticity.fast_weights import FastConfig, FastWeights
from plasticity.slow_weights import CheckpointStore

PASS = NGRResult(True, ["all promotion conditions met"], {})
FAIL = NGRResult(False, ["target gain too small"], {})


def _artifact(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fast_state_learns_and_resets_without_touching_base(tmp_path):
    base = _artifact(tmp_path / "base.npz", "frozen-base")
    before = _sha(base)
    fast = FastWeights(FastConfig(max_delta_norm=100.0))
    surprise = fast.learn("capital of France", "Paris")
    assert surprise > 0
    assert fast.delta_norm > 0 and fast.writes_since_reset == 1
    fast.reset()
    assert fast.delta_norm == 0 and fast.writes_since_reset == 0
    assert _sha(base) == before


def test_fast_state_is_bounded():
    fast = FastWeights(FastConfig(max_delta_norm=0.01))
    fast.learn("a b c", "d e f")
    assert fast.delta_norm <= 0.01 + 1e-6


def test_promote_requires_passing_ngr(tmp_path):
    store = CheckpointStore(tmp_path)
    art = _artifact(tmp_path / "candidate.npz", "weights")
    store.stage(art, "candidate.npz")
    with pytest.raises(PermissionError):
        store.promote("candidate.npz", FAIL)
    assert store.current() is None


def test_promote_and_rollback_restore_previous_stable(tmp_path):
    store = CheckpointStore(tmp_path)
    a = _artifact(tmp_path / "a.npz", "version-a")
    b = _artifact(tmp_path / "b.npz", "version-b")
    store.stage(a, "a.npz")
    store.promote("a.npz", PASS)
    first = store.current()
    assert first.name == "a.npz"
    a_before = _sha(store.load())

    store.stage(b, "b.npz")
    store.promote("b.npz", PASS)
    assert store.current().name == "b.npz"
    assert _sha(store.root / "stable" / "a.npz") == a_before    # previous stable kept

    restored = store.rollback()
    assert restored.name == "a.npz"
    assert store.current().name == "a.npz"
    assert store.load().read_text() == "version-a"
