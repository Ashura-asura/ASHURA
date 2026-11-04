"""Phase 2 (P15-P29) memory reliability tests."""
from __future__ import annotations

import time

import pytest

from learning.ama import AMA, AMAConfig, FEEDBACK_WEIGHTS
from learning.compare import answer_similarity, answers_agree, extract_values, negation_scope, surprise_from_prior
from learning.dream import DreamConfig
from learning.replay import ReplayBuffer, ReplayItem
from memory.adaptive_memory import AdaptiveMemory, AMemConfig, drain_neural_queue
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index
from memory.retention import RetentionPolicy, apply, plan
from memory.semantic import SemanticMemory


def mk(cfg: AMAConfig | None = None):
    db = Database()
    return db, AMA(db, cfg)


# ---- P19: structured values / units / dates ----
@pytest.mark.parametrize("q,a,b", [
    ("how far", "1.5 km", "1500 m"),
    ("how heavy", "2 kg", "2000 grams"),
    ("how long", "2 hours", "120 minutes"),
    ("when", "May 6, 2024", "2024-05-06"),
    ("when", "6 May 2024", "2024-05-06"),
    ("how many", "twenty three", "23"),
    ("which", "project P7", "project p7"),
])
def test_equivalent_values_are_merged_not_conflicts(q, a, b):
    assert answers_agree(q, a, b) and answers_agree(q, b, a)


@pytest.mark.parametrize("q,a,b", [
    ("how far", "1.5 km", "1.5 miles"),
    ("when", "2024-05-06", "2024-05-07"),
    ("how many", "twenty three", "twenty four"),
    ("which", "project P7", "project P8"),
])
def test_different_values_still_conflict(q, a, b):
    assert not answers_agree(q, a, b)


def test_values_record_units_and_dates_canonically():
    assert "val:1500length" in extract_values("1.5 km")
    assert "date:2024-05-06" in extract_values("May 6, 2024")
    assert "num:23" in extract_values("twenty three")


# ---- P20: negation applies to its clause, not token parity ----
def test_negation_scope_detects_clause_negation():
    q = "which project has the code"
    assert not answers_agree(q, "code is 4821", "code is not 4821")
    assert not answers_agree("capital", "Paris", "Paris is not the capital")
    assert negation_scope("The code is not 4821") == frozenset({"code", "num:4821"})


# ---- P26: continuous surprise ----
def test_surprise_is_continuous_for_related_mismatch():
    q = "when is the meeting"
    same = surprise_from_prior(q, "Monday", "The meeting is on Monday")
    related = surprise_from_prior(q, "Monday", "The meeting is on Friday")
    assert same == 0.0
    assert 0.0 < related <= 1.0
    assert surprise_from_prior(q, "4812", "the code is 4821") == 1.0
    assert answer_similarity(q, "Monday", "Friday") < 0.2


# ---- P21: conflict index and explicit resolution ----
def test_conflict_index_keeps_both_records_and_is_queryable():
    db, ama = mk()
    old = ama.admit(Experience("code for project p1", "code is 9999", verification_status="unverified"))
    new = ama.admit(Experience("code for project p1", "code is 4821", verification_status="user_corrected"))
    rows = ama.conflicts()
    assert len(rows) == 1 and rows[0]["status"] == "open"
    assert {rows[0]["new_exp_id"], rows[0]["old_exp_id"]} == {new.exp_id, old.exp_id}
    assert EpisodicMemory(db).get(old.exp_id) is not None
    assert EpisodicMemory(db).get(new.exp_id) is not None


def test_verified_claim_supersedes_weaker_claim_under_explicit_policy():
    db, ama = mk()
    old = ama.admit(Experience("code for project p1", "code is 9999", verification_status="unverified"))
    new = ama.admit(Experience("code for project p1", "code is 4821", verification_status="verified"))
    ids = [i for i, _ in FTS5Index(db).search("code project p1")]
    assert old.exp_id not in ids and new.exp_id in ids
    assert EpisodicMemory(db).get(old.exp_id) is not None          # history retained
    row = ama.conflicts(open_only=False)[0]
    assert row["status"] == "superseded" and row["policy"]


def test_two_verified_claims_stay_in_review_not_auto_resolved():
    db, ama = mk()
    ama.admit(Experience("code for project p1", "code is 9999", verification_status="verified"))
    d = ama.admit(Experience("code for project p1", "code is 4821", verification_status="verified"))
    assert d.decision == "REVIEW_REQUIRED"
    assert ama.conflicts()[0]["status"] == "open"


def test_conflict_resolution_requires_a_verified_experience():
    db, ama = mk()
    ama.admit(Experience("code for project p1", "code is 9999", verification_status="unverified"))
    ama.admit(Experience("code for project p1", "code is 4821", verification_status="user_provided"))
    cid = ama.conflicts()[0]["id"]
    with pytest.raises(ValueError):
        ama.resolve_conflict(cid, "looks right", verified_exp_id="missing")
    assert ama.resolve_conflict(cid, "dismissed by reviewer")
    assert ama.conflicts(open_only=False)[0]["status"] == "dismissed"


# ---- P29: semantic facts need explicit provenance ----
def test_semantic_memory_rejects_unverified_source():
    db = Database()
    ep = EpisodicMemory(db)
    e = Experience("2+2", "4", verification_status="unverified")
    ep.add(e)
    with pytest.raises(ValueError, match="not independently verified"):
        SemanticMemory(db).add_fact(e.text, e.id, 1.0)


def test_semantic_fact_preserves_provenance_and_is_deleted_with_source():
    db = Database()
    ep, sem = EpisodicMemory(db), SemanticMemory(db)
    e = Experience("2+2", "4", verification_status="verified")
    ep.add(e)
    fid = sem.add_fact(e.text, e.id, 1.0, derivation="exact arithmetic")
    fact = sem.get(fid)
    assert fact["provenance"]["source_exp_id"] == e.id
    assert fact["provenance"]["verification"] == "verified"
    assert "exact arithmetic" in fact["derivation"]
    ep.delete(e.id)
    assert sem.count() == 0


# ---- P18: utility is separate from truth ----
def test_feedback_changes_utility_but_not_reliability():
    db, ama = mk()
    d = ama.admit(Experience("what is 7*8", "56", verification_status="verified"))
    before = EpisodicMemory(db).get(d.exp_id)
    assert ama.utility_from_feedback(d.exp_id) is None
    ama.record_feedback(d.exp_id, "user_rejected")
    rejected = ama.utility_from_feedback(d.exp_id)
    ama.record_feedback(d.exp_id, "user_accepted")
    accepted = ama.utility_from_feedback(d.exp_id)
    after = EpisodicMemory(db).get(d.exp_id)
    assert accepted > rejected
    assert after.reliability == before.reliability == 1.0
    assert after.verification_status == "verified"
    assert set(FEEDBACK_WEIGHTS) >= {"user_rejected", "user_accepted"}


def test_unknown_feedback_event_is_rejected():
    db, ama = mk()
    d = ama.admit(Experience("q", "a", verification_status="verified"))
    with pytest.raises(ValueError):
        ama.record_feedback(d.exp_id, "made_up")


# ---- P27: retention respects use and verification ----
def test_retention_protects_used_and_verified_records():
    db = Database()
    ep = EpisodicMemory(db)
    now = time.time()
    used = Experience("used q", "used a", verification_status="unverified", ts=now - 40 * 86400)
    unused = Experience("unused q", "unused a", verification_status="unverified", ts=now - 40 * 86400)
    verified = Experience("verified q", "verified a", verification_status="verified", ts=now - 40 * 86400)
    for e in (used, unused, verified):
        ep.add(e)
    db.conn.execute("INSERT INTO memory_feedback(ts, exp_id, event, value, source, note) "
                    "VALUES (?,?,?,?,?,?)", (now - 86400, used.id, "retrieval_hit", 1.0, "test", ""))
    db.conn.commit()
    planned = {i for i, _ in plan(db, RetentionPolicy(max_age_days=30, protect_recent_days=7))}
    assert unused.id in planned
    assert used.id not in planned and verified.id not in planned
    forgotten = apply(db, RetentionPolicy(max_age_days=30, protect_recent_days=7))
    assert forgotten == [unused.id]


# ---- P23: neural-memory queue gate ----
def test_neural_queue_rejects_unverified_and_logs_it():
    db = Database()
    ep = EpisodicMemory(db)
    e = Experience("what is 7*8", "56", verification_status="unverified")
    ep.add(e)
    db.conn.execute("INSERT INTO dream_queue(exp_id, queue, ts) VALUES (?,?,?)",
                    (e.id, "neural_memory", time.time()))
    db.conn.commit()
    mem = AdaptiveMemory(AMemConfig(lr=1.0, idf=False))
    assert drain_neural_queue(db, mem) == 0
    assert db.conn.execute("SELECT 1 FROM dream_queue").fetchone() is None
    assert db.conn.execute("SELECT decision FROM admission_log").fetchone()["decision"] == "NEURAL_UPDATE_REJECTED"


def test_neural_queue_conflict_is_not_written():
    db = Database()
    ep = EpisodicMemory(db)
    trusted = Experience("code p1", "code is 4821", verification_status="trusted_material")
    conflicting = Experience("code p1", "code is 9999", verification_status="verified")
    ep.add(trusted); ep.add(conflicting)
    db.conn.execute("INSERT INTO dream_queue(exp_id, queue, ts) VALUES (?,?,?)",
                    (conflicting.id, "neural_memory", time.time()))
    db.conn.commit()
    mem = AdaptiveMemory(AMemConfig(lr=1.0, idf=False))
    assert drain_neural_queue(db, mem) == 0


def test_adaptive_memory_snapshot_keeps_old_values_recoverable():
    mem = AdaptiveMemory(AMemConfig(lr=1.0, idf=False))
    mem.write("code p1", "4821")
    snap = mem.snapshot()
    mem.write("code p1", "9999")
    assert mem.recall("code p1", ["4821", "9999"])[0] == "9999"
    mem.restore(snap)
    assert mem.recall("code p1", ["4821", "9999"])[0] == "4821"


# ---- P25: IDF down-weights common tokens ----
def test_idf_downweights_common_tokens():
    mem = AdaptiveMemory(AMemConfig(idf=True))
    for i in range(20):
        mem.write(f"common token {i}", f"v{i}")
    mem.write("rare unicorn", "v")
    assert mem._weight("common") < mem._weight("unicorn")


# ---- P28: replay policy validation ----
def test_replay_policy_is_explicit_and_validated():
    b = ReplayBuffer()
    for i in range(6):
        b.add(ReplayItem(f"old-{i}", f"old key {i}", f"old-{i}", category="old", verified=True))
    for i in range(4):
        b.add(ReplayItem(f"new-{i}", f"new key {i}", f"new-{i}", category="new", verified=True))
    recent = b.replay_set("new", 0.5, policy="recent")
    assert any(i.id == "old-5" for i in recent)
    with pytest.raises(ValueError):
        b.replay_set("new", 0.5, policy="newest")
    with pytest.raises(ValueError):
        DreamConfig(replay_policy="newest")


def test_storage_report_separates_audit_tables_from_records():
    db, ama = mk()
    ama.admit(Experience("2+2", "4", verification_status="verified"))
    report = ama.storage_report()
    assert report["rows"]["experiences"] == 1
    assert report["rows"]["admission_log"] == 1
    assert report["total_bytes"] > 0
