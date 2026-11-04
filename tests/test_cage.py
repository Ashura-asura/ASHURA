import json

from brain.controller import Controller
from brain.execution_trace import ExecutionTrace, TraceStep
from brain.need_field import Task
from foundation.language_model import EchoModel
from learning.ama import AMA
from learning.cage import CAGE
from memory.database import Database
from plasticity.fast_weights import FastWeights
from plasticity.gated_update import GatedUpdater
from plasticity.update_policy import UpdatePolicy


def trace(*steps: TraceStep) -> ExecutionTrace:
    t = ExecutionTrace(task="arithmetic")
    for s in steps:
        t.add(s)
    return t


def test_explicit_failure_blames_first_failing_component():
    t = trace(TraceStep("parser", "2+2", "2+2", 1.0),
              TraceStep("arithmetic", "2+2", "5", 2.0, ok=False, note="expected 4"),
              TraceStep("language", "5", "5", 3.0))
    a = CAGE().attribute(t, expected="4")
    assert a.module == "arithmetic" and a.confidence == 1.0
    assert a.eligible == ("arithmetic",)


def test_verifier_catches_bad_output_without_ok_flag():
    t = trace(TraceStep("parser", "2+3", "2+3", 1.0),
              TraceStep("arithmetic", "2+3", "6", 2.0),
              TraceStep("language", "6", "6", 3.0))
    a = CAGE().attribute(t, verifiers={"arithmetic": lambda out: out == "5"})
    assert a.module == "arithmetic" and a.confidence == 0.9


def test_final_mismatch_without_evidence_is_not_attributed():
    t = trace(TraceStep("language", "q", "wrong", 1.0))
    a = CAGE().attribute(t, expected="right")
    assert a.module is None and a.eligible == () and a.confidence < 0.8


def test_no_divergence_means_no_update():
    t = trace(TraceStep("parser", "q", "q", 1.0), TraceStep("arithmetic", "q", "4", 2.0))
    a = CAGE().attribute(t, expected="4")
    assert a.module is None and a.eligible == ()


def test_policy_rejects_unverified_or_low_confidence_signals():
    cage = CAGE(UpdatePolicy())
    t = trace(TraceStep("arithmetic", "2+2", "5", 1.0, ok=False))
    a = cage.attribute(t, expected="4")
    assert not cage.authorise(a, verified=False).allowed
    assert cage.authorise(a, verified=True).allowed


def test_cage_records_decisions(tmp_path):
    log = tmp_path / "cage.jsonl"
    cage = CAGE(log_path=log)
    t = trace(TraceStep("arithmetic", "2+2", "5", 1.0, ok=False))
    cage.authorise(cage.attribute(t, expected="4"), verified=True)
    row = json.loads(log.read_text().strip())
    assert row["attribution"]["module"] == "arithmetic" and row["update"]["allowed"]


def test_controller_attributes_arithmetic_failure_without_updating():
    cage = CAGE()
    c = Controller(EchoModel(), ama=AMA(Database()), cage=cage)
    r = c.handle(Task("calculate 1/0"))
    assert r.attribution is not None and "arithmetic" in r.attribution
    assert "update allowed=False" in r.attribution
    assert cage.decisions[-1]["verified"] is False        # an ordinary failure is not a learning signal


# ---- Phase 1 P07/P08: an authorisation is consumed, and only when verified ----
def test_gated_updater_consumes_a_verified_authorisation():
    cage = CAGE()
    t = trace(TraceStep("language", "q", "wrong", 1.0))
    attr = cage.attribute(t, expected="right", verifiers={"language": lambda out: out == "right"})
    decision = cage.authorise(attr, verified=True)
    proposal = cage.propose(attr, decision, verified=True, key="q", value="right", source="test")
    fast = FastWeights()
    outcome = GatedUpdater(fast).apply(decision, proposal)
    assert outcome.applied and fast.delta_norm > 0 and fast.writes_since_reset == 1


def test_gated_updater_rejects_unverified_or_unattributed_signals():
    cage = CAGE()
    t = trace(TraceStep("language", "q", "wrong", 1.0))
    attr = cage.attribute(t, expected="right")
    decision = cage.authorise(attr, verified=False)
    proposal = cage.propose(attr, decision, verified=True, key="q", value="right")
    fast = FastWeights()
    outcome = GatedUpdater(fast).apply(decision, proposal)
    assert proposal is None and not outcome.applied and fast.delta_norm == 0

    unattributed = cage.attribute(trace(TraceStep("language", "q", "wrong", 1.0)), expected="right")
    allowed = cage.authorise(unattributed, verified=True)
    assert cage.propose(unattributed, allowed, verified=True, key="q", value="right") is None
