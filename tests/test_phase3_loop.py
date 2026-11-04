"""Phase 3 tests (P05/P06/P07/P75): verified corrections and the end-to-end loop."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from brain.controller import Controller, default_registry
from brain.execution_trace import ExecutionTrace, TraceStep
from brain.need_field import NeedField, Task
from brain.verification import Verification
from evaluation.ngr import NGRPolicy
from foundation.language_model import EchoModel
from learning.ama import AMA
from learning.cage import CAGE
from learning.corrections import parse_correction
from learning.dream import DreamConfig
from learning.loop import run_verified_correction
from learning.replay import ReplayBuffer, ReplayItem
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from plasticity.fast_weights import FastWeights
from plasticity.gated_update import GatedUpdater
from plasticity.slow_weights import CheckpointStore

DIM = 64


def ctl():
    ama = AMA(Database())
    nfd = NeedField(default_registry(), cpu_fn=lambda: 5.0, ram_fn=lambda: 16000.0)
    return Controller(EchoModel(), ama=ama, nfd=nfd, cage=CAGE())


# ---- correction parsing / independent verification ----
@pytest.mark.parametrize("text,state,value", [
    ("actually, 6*7 = 42", "verified", "42"),
    ("no, 2+2 is 4", "verified", "4"),
    ("actually, 10/4 = 2.5", "verified", "5/2"),
    ("that's wrong, 3.5 + 1.5 = 5", "verified", "5"),
])
def test_true_arithmetic_corrections_are_independently_verified(text, state, value):
    c = parse_correction(text)
    assert c.kind == "arithmetic" and c.state == state and c.value == value
    assert c.expected == value and c.to_experience() is not None


def test_false_arithmetic_correction_is_rejected_not_relabelled():
    c = parse_correction("no, 6*7 = 43")
    assert c.state == "failed" and c.value == "43" and c.expected == "42"
    assert c.to_experience() is None


@pytest.mark.parametrize("text,value", [
    ("actually, 2^10 = 1024", "1024"),
    ("actually, 10%3 = 1", "1"),
    ("actually, sqrt(144) = 12", "12"),
])
def test_power_modulo_and_root_corrections_are_independently_verified(text, value):
    c = parse_correction(text)
    assert c.kind == "arithmetic" and c.state == "verified" and c.value == value
    assert c.to_experience() is not None


def test_unchecked_arithmetic_is_unavailable_not_verified():
    # Irrational roots and non-integer powers have no exact value, so they stay unchecked.
    for text in ("actually, sqrt(2) = 1.41421356", "actually, 2 ** 0.5 = 1.41421356"):
        c = parse_correction(text)
        assert c.kind == "arithmetic" and c.state == "unavailable"
        assert c.to_experience() is None


def test_fact_correction_stays_a_user_assertion():
    c = parse_correction("actually, the project p12 code is 9999")
    assert c.kind == "fact" and c.state == "unavailable" and c.value == "9999"
    assert c.to_experience() is None


# ---- controller: P05/P06 still hold, verified arithmetic adds a checked record ----
def test_verified_arithmetic_correction_is_stored_separately_from_the_reply():
    c = ctl()
    text = "actually, 6*7 = 42"
    r = c.handle(Task(text, user_correction=True))
    assert r.correction["state"] == "verified" and r.correction["verified_record"] is True
    raw = c.ama.episodic.find_by_input(text)
    assert len(raw) == 1 and raw[0].verification_status == "user_provided"
    checked = c.ama.episodic.find_by_input("6*7")
    assert len(checked) == 1
    assert checked[0].verification_status == "verified" and checked[0].output == "42"
    assert checked[0].source == "user_correction_verified"
    assert c.ama.db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 1
    assert "user_corrected" not in {e.verification_status for e in c.ama.episodic.filter(limit=10)}


def test_false_or_unverifiable_correction_never_becomes_verified():
    c = ctl()
    for text in ("actually, 6*7 = 43", "actually, the project p12 code is 9999"):
        r = c.handle(Task(text, user_correction=True))
        assert r.correction["state"] in {"failed", "unavailable"}
        assert r.correction["verified_record"] is False
    assert c.ama.db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
    assert {e.verification_status for e in c.ama.episodic.filter(limit=10)} == {"user_provided"}


# ---- loop building blocks ----
def _trace() -> ExecutionTrace:
    t = ExecutionTrace(task="what is 6*7")
    t.add(TraceStep("arithmetic", "6*7", "42", 0.5))
    t.add(TraceStep("language", "6*7", "43", 10.0))
    return t


def _buffer() -> ReplayBuffer:
    b = ReplayBuffer()
    for i in range(8):
        b.add(ReplayItem(f"old-{i}", f"entity{i} old", f"old-{i}", category="old", verified=True))
        b.add(ReplayItem(f"old-h-{i}", f"old entity{i}", f"old-{i}", category="old", verified=True,
                         split="heldout"))
    b.add(ReplayItem("new-h-0", "what is 6*7", "42", category="corrected", verified=True,
                     split="heldout"))
    b.add(ReplayItem("new-h-1", "please compute 6*7", "42", category="corrected", verified=True,
                     split="heldout"))
    return b


def _store() -> CheckpointStore:
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix="loop_test_")))
    b = _buffer()
    from memory.adaptive_memory import AMemConfig, AdaptiveMemory
    mem = AdaptiveMemory(AMemConfig(dim_k=DIM, dim_v=DIM))
    for it in b.training_set():
        if it.category == "old":
            mem.write(it.key, it.value)
    tmp = Path(tempfile.mkdtemp()) / "old.npz"
    mem.save(str(tmp))
    store.stage(tmp, "old.npz")
    from evaluation.ngr import NGRResult
    store.promote("old.npz", NGRResult(True, ["fixture"], {}))
    return store


def _run(text: str, *, trace=True, replay=True, initialization="stable"):
    store, buffer, fast = _store(), _buffer(), FastWeights()
    cfg = DreamConfig(target="corrected", dim=DIM, min_train=1, replay=replay,
                      initialization=initialization)
    return run_verified_correction(
        parse_correction(text), _trace() if trace else None,
        cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer, store=store,
        policy=NGRPolicy("corrected", min_target_gain=0.5), cfg=cfg), store, fast


def test_unverified_or_untraced_correction_creates_no_candidate_and_no_fast_update():
    for kwargs in ({"text": "actually, the project p12 code is 9999", "trace": False},
                   {"text": "actually, 6*7 = 43"},
                   {"text": "actually, 6*7 = 42", "trace": False}):
        result, store, fast = _run(**kwargs)
        assert not result.promoted and result.stage.startswith("refused")
        assert fast.delta_norm == 0.0                       # no temporary update either
        assert store.current().name == "old.npz"            # stable pointer unchanged


def test_verified_correction_promotes_through_cage_candidate_and_ngr():
    result, store, fast = _run("actually, 6*7 = 42")
    assert result.stage == "promoted" and result.promoted
    assert result.attribution["module"] == "language"
    assert result.decision["allowed"] is True
    assert result.proposal["key"] == "6*7" and result.proposal["value"] == "42"
    assert result.update["applied"] is True and fast.delta_norm > 0
    assert result.dream["scores"]["corrected"] == 1.0
    assert result.dream["scores"]["old"] == 1.0
    assert store.current().name == result.dream["candidate"]


def test_ngr_rejects_a_candidate_that_loses_old_capability():
    result, store, fast = _run("actually, 6*7 = 42", replay=False, initialization="fresh")
    assert result.stage == "candidate_rejected" and not result.promoted
    assert any("regression on old" in r for r in result.dream["ngr"])
    assert store.current().name == "old.npz"                # rollback = unchanged stable pointer
    assert fast.delta_norm > 0                              # temporary state is separate


# ---- controller integration: F-041 trace retention and optional loop hook ----
class WrongArithmeticModel(EchoModel):
    def generate(self, prompt: str, max_tokens: int = 128) -> str:
        return "43" if "6*7" in prompt else "I do not know"


def test_controller_invokes_the_loop_on_the_previous_trace_after_a_correction():
    store, buffer, fast = _store(), _buffer(), FastWeights()
    c = ctl()
    c.model = WrongArithmeticModel()
    c.correction_loop = lambda correction, trace: run_verified_correction(
        correction, trace, cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer, store=store,
        policy=NGRPolicy("corrected", min_target_gain=0.5),
        cfg=DreamConfig(target="corrected", dim=DIM, min_train=1, replay=True,
                        initialization="stable"))

    first = c.handle("If a rectangle is 6*7, what is its area?")
    assert first.text == "43" and c._last_trace is first.trace   # wrong reply, trace retained
    r = c.handle(Task("actually, 6*7 = 42", user_correction=True))
    assert r.correction["state"] == "verified"
    assert r.correction["loop"]["stage"] == "promoted" and r.correction["loop"]["promoted"] is True
    assert store.current().name != "old.npz"


def test_controller_does_not_invoke_the_loop_without_a_previous_trace():
    calls = []
    c = ctl()
    c.correction_loop = lambda correction, trace: calls.append(trace)
    r = c.handle(Task("actually, 6*7 = 42", user_correction=True))
    assert calls == [] and r.correction["loop"]["stage"] == "not_run"


def test_controller_does_not_invoke_the_loop_for_an_unverified_correction():
    calls = []
    c = ctl()
    c.correction_loop = lambda correction, trace: calls.append(trace)
    c.handle("what is 6*7")
    r = c.handle(Task("actually, the project p12 code is 9999", user_correction=True))
    assert calls == [] and r.correction["state"] == "unavailable" and "loop" not in r.correction


def test_loop_hook_failure_never_breaks_the_reply():
    def broken(correction, trace):
        raise RuntimeError("candidate store offline")

    c = ctl()
    c.correction_loop = broken
    c.handle("what is 6*7")
    r = c.handle(Task("actually, 6*7 = 42", user_correction=True))
    assert r.correction["loop"]["stage"] == "error"
    assert "candidate store offline" in r.correction["loop"]["error"]


# ---- F-039: small reviewer workflow for the conflict index ----
def _conflict_db(tmp_path):
    path = tmp_path / "review.db"
    db = Database(str(path))
    ama = AMA(db)
    ama.admit(Experience("code for project p1", "code is 9999", verification_status="unverified"))
    ama.admit(Experience("code for project p1", "code is 4821", verification_status="user_provided"))
    db.close()
    return path


def test_review_workflow_lists_and_dismisses_a_conflict(tmp_path):
    from learning import review

    path = _conflict_db(tmp_path)
    rows = review.list_conflicts(path)
    assert len(rows) == 1 and rows[0]["status"] == "open"
    out = review.resolve_conflict(path, rows[0]["id"], "reviewed: user assertion only")
    assert out["resolved"] is True and out["status"] == "dismissed"
    assert review.list_conflicts(path) == []
    assert review.list_conflicts(path, open_only=False)[0]["status"] == "dismissed"


def test_review_cli_accepts_the_documented_argument_order(tmp_path, capsys):
    from learning import review

    path = _conflict_db(tmp_path)
    assert review.main(["list", "--db", str(path)]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1 and rows[0]["status"] == "open"


def test_review_workflow_requires_a_verified_experience_to_supersede(tmp_path):
    from learning import review

    path = _conflict_db(tmp_path)
    conflict_id = review.list_conflicts(path)[0]["id"]
    with pytest.raises(ValueError):
        review.resolve_conflict(path, conflict_id, "looks right", verified_exp="missing")
    assert review.list_conflicts(path)[0]["status"] == "open"


def test_cage_does_not_authorise_an_unattributed_failure():
    trace = ExecutionTrace(task="what is 6*7")
    trace.add(TraceStep("language", "6*7", "maybe", 5.0))
    cage = CAGE()
    attr = cage.attribute(trace, expected="42", verifiers={"arithmetic": lambda x: x == "42"})
    decision = cage.authorise(attr, verified=True)
    assert attr.module is None and not decision.allowed
    assert cage.propose(attr, decision, verified=True, key="6*7", value="42") is None
