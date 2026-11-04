"""Phase 1 trust tests (P01-P08): provenance, reliability-aware retrieval, tri-state
verification and correction handling."""
from __future__ import annotations

import pytest

from brain.controller import Controller, default_registry
from brain.need_field import NeedField, Task
from brain.verification import Verification
from foundation.language_model import EchoModel
from learning.ama import AMA, AMAConfig
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index
from skills.arithmetic import exact


class RecordingModel(EchoModel):
    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, prompt: str, max_tokens: int = 128) -> str:
        self.prompts.append(prompt)
        return super().generate(prompt, max_tokens)


def ctl(model=None, ama=None):
    model = model or RecordingModel()
    ama = ama or AMA(Database())
    nfd = NeedField(default_registry(), cpu_fn=lambda: 5.0, ram_fn=lambda: 16000.0)
    c = Controller(model, ama=ama, nfd=nfd)
    return c, model


# ---- P01/P02: reliability-aware retrieval and provenance ----
def test_unverified_memory_is_not_retrieved_or_prompted():
    c, model = ctl()
    c.ama.admit(Experience("what did i tell you about project p9 code", "code is 1111",
                           verification_status="unverified"))
    q = "what did i tell you about project p9 code?"
    assert c.ama.retrieve(q) == []
    assert c.ama.retrieve(q, include_unverified=True)[0].experience.output == "code is 1111"

    r = c.handle(q)
    assert "1111" not in model.prompts[-1]
    assert r.trace.step("exact_retrieval").output == "0 hits"


def test_verified_memory_is_retrieved_with_a_provenance_label():
    c, model = ctl()
    c.ama.admit(Experience("what did i tell you about project p9 code", "code is 4821",
                           verification_status="verified"))
    q = "what did i tell you about project p9 code?"
    items = c.ama.retrieve(q)
    assert len(items) == 1 and items[0].label == "verified fact"
    assert items[0].provenance["verification_method"] == "independent verification"
    assert items[0].provenance["conflict"] is False

    c.handle(q)
    assert "verified fact" in model.prompts[-1] and "4821" in model.prompts[-1]


def test_user_provided_memory_is_retrieved_but_explicitly_not_verified():
    c, model = ctl()
    c.handle("remember that project p12 code is 4821")
    q = "what did I tell you about project p12 code?"
    items = c.ama.retrieve(q)
    assert items and items[0].label == "user-provided, not independently verified"
    c.handle(q)
    assert "user-provided, not independently verified" in model.prompts[-1]
    assert "4821" in model.prompts[-1]


def test_reliability_is_provenance_specific_and_provenance_is_stored():
    db = Database()
    e = Experience("remember that the code is 4821", "", source="user",
                   verification_status="user_provided")
    assert e.reliability == 0.6
    assert "user assertion" in e.verification_method
    EpisodicMemory(db).add(e)
    stored = EpisodicMemory(db).get(e.id)
    assert stored.verification_method == e.verification_method and stored.reliability == 0.6


def test_only_verified_records_enter_semantic_memory():
    db = Database()
    ama = AMA(db)
    d = ama.admit(Experience("a trusted fact", "value", verification_status="trusted_material"))
    assert "semantic" not in d.destinations
    d = ama.admit(Experience("a verified fact", "value2", verification_status="verified"))
    assert "semantic" in d.destinations


# ---- P03/P04: tri-state verification ----
def test_verified_arithmetic_marks_the_response_verified():
    c, _ = ctl()
    r = c.handle("what is 12*7?")
    assert r.text == "84" and r.verified is True
    assert r.verification is Verification.VERIFIED
    assert r.trace.step("verification").verification == "verified"
    assert r.trace.step("verification").ok is True


def test_unavailable_verification_is_not_success():
    c, _ = ctl()
    r = c.handle("what is 5 > 3?")                 # comparisons have no independent cross-check
    assert r.text == "True"
    assert r.verified is None and r.verification is Verification.UNAVAILABLE
    step = r.trace.step("verification")
    assert step.ok is True and step.verification == "unavailable"   # operational success, not factual
    e = c.ama.episodic.find_by_input("what is 5 > 3?")[0]
    assert e.verification_status == "unverified" and e.reliability == 0.2
    assert c.ama.db.conn.execute("SELECT COUNT(*) FROM dream_queue").fetchone()[0] == 0


def test_failed_verification_is_not_success(monkeypatch):
    monkeypatch.setattr(exact, "verify", lambda expr, value: (False, "forced disagreement"))
    c, _ = ctl()
    r = c.handle("what is 2+2?")
    assert r.verified is False and r.verification is Verification.FAILED
    step = r.trace.step("verification")
    assert step.ok is False and step.verification == "failed"
    e = c.ama.episodic.find_by_input("what is 2+2?")[0]
    assert e.verification_status == "unverified"
    assert c.ama.db.conn.execute("SELECT COUNT(*) FROM dream_queue").fetchone()[0] == 0


def test_a_language_generated_response_cannot_borrow_arithmetic_verification():
    c, model = ctl()
    q = "I have 3 boxes with 12*7 items each, can you tell me a story about them"
    r = c.handle(q)
    assert r.trace.step("verification").verification == "verified"   # the computation was checked
    assert r.verified is None                                        # the written response was not
    e = c.ama.episodic.find_by_input(q)[0]
    assert e.verification_status == "unverified"


# ---- P05/P06: user corrections are separate from assistant responses ----
def test_user_correction_is_stored_as_a_separate_user_provided_record():
    c, _ = ctl()
    text = "that's wrong, the code is 4821"
    r = c.handle(Task(text, user_correction=True))
    assert r.text                                                     # still answers
    rows = c.ama.episodic.find_by_input(text)
    assert len(rows) == 1
    e = rows[0]
    assert e.verification_status == "user_provided" and e.reliability == 0.6
    assert e.source == "user" and e.output == ""
    assert "factual truth not independently verified" in e.verification_method
    assert c.ama.episodic.count() == 1                                # the generated reply was not relabelled
    assert c.ama.db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
    assert c.ama.db.conn.execute("SELECT COUNT(*) FROM dream_queue").fetchone()[0] == 0


def test_user_assertion_is_a_user_record_not_a_verified_model_answer():
    c, _ = ctl()
    c.handle("remember that project p12 code is 4821")
    rows = c.ama.episodic.find_by_input("remember that project p12 code is 4821")
    assert len(rows) == 1 and rows[0].verification_status == "user_provided"
    assert rows[0].output == "" and rows[0].reliability == 0.6
    assert c.ama.episodic.count() == 1


def test_generated_answer_after_a_correction_is_never_labelled_user_corrected():
    c, _ = ctl()
    c.handle("remember that project p12 code is 4821")
    c.handle(Task("actually, the project p12 code is 9999", user_correction=True))
    statuses = {e.verification_status for e in c.ama.episodic.filter(limit=10)}
    assert "user_corrected" not in statuses
    assert statuses == {"user_provided"}
