from learning.ama import AMA, AMAConfig, StoreEverything
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index


def mk():
    db = Database()
    return db, AMA(db)


def test_exact_duplicate_is_merged_not_stored():
    db, ama = mk()
    ama.admit(Experience("capital of france", "Paris", verification_status="verified"))
    d = ama.admit(Experience("Capital  of France", "paris", verification_status="verified"))
    assert d.decision == "MERGED" and EpisodicMemory(db).count() == 1


def test_unverified_claim_never_becomes_fact_or_dream_target():
    db, ama = mk()
    d = ama.admit(Experience("who won the 2031 cup", "Brazil won it", verification_status="unverified"))
    assert d.decision == "ADMITTED"
    assert "semantic" not in d.destinations and "dream_queue" not in d.destinations
    assert db.conn.execute("SELECT COUNT(*) FROM dream_queue").fetchone()[0] == 0


def test_verified_goes_to_semantic_fts_and_dream():
    db, ama = mk()
    d = ama.admit(Experience("2+2", "4", task_category="arithmetic", verification_status="verified"))
    assert {"episodic", "fts5", "semantic", "dream_queue"} <= set(d.destinations)


def test_weaker_conflict_is_kept_as_evidence_but_not_searchable():
    db, ama = mk()
    ama.admit(Experience("code for project p1", "code is 4821", verification_status="verified"))
    d = ama.admit(Experience("code for project p1", "code is 9999", verification_status="unverified"))
    assert d.decision == "REVIEW_REQUIRED"
    assert EpisodicMemory(db).count() == 2                      # historical evidence retained
    top = FTS5Index(db).search("code project p1")
    assert len(top) == 1 and "4821" in EpisodicMemory(db).get(top[0][0]).output
    assert db.conn.execute("SELECT COUNT(*) FROM dream_queue WHERE exp_id=?", (d.exp_id,)).fetchone()[0] == 0


def test_user_correction_does_not_supersede_by_reliability_alone():
    """P21: 0.6 user evidence is stronger than 0.2 unverified, but it is still not verified truth."""
    db, ama = mk()
    old = ama.admit(Experience("code for project p1", "code is 9999", verification_status="unverified"))
    d = ama.admit(Experience("code for project p1", "code is 4821", verification_status="user_corrected"))
    assert d.decision == "REVIEW_REQUIRED"
    assert EpisodicMemory(db).count() == 2
    assert db.conn.execute("SELECT COUNT(*) FROM conflicts WHERE status='open'").fetchone()[0] == 1
    ids = [i for i, _ in FTS5Index(db).search("code project p1")]
    assert old.exp_id in ids and d.exp_id not in ids          # old search result retained, new is evidence only


def test_near_duplicate_with_formatting_noise_is_merged():
    db, ama = mk()
    ama.admit(Experience("explain the water cycle briefly", "Water evaporates, condenses into clouds, and falls as rain."))
    d = ama.admit(Experience("Explain the water cycle briefly!", "water evaporates condenses into clouds and falls as rain"))
    assert d.decision == "MERGED" and EpisodicMemory(db).count() == 1


def test_discard_branch_with_explicit_threshold():
    # NOTE: under the DEFAULT weights this branch is nearly unreachable (see research/failures.md F-001).
    db = Database()
    ama = AMA(db, AMAConfig(discard_threshold=0.8))
    ama.admit(Experience("tell me something random please", "ok sure thing here you go"))
    d = ama.admit(Experience("tell me something random please now", "ok sure thing here you go then"))
    assert d.decision == "DISCARDED" and EpisodicMemory(db).count() == 1


def test_repeated_reliable_association_queues_neural_memory():
    db, ama = mk()
    e = lambda: Experience("what is 7*8", "56", task_category="arithmetic", verification_status="verified")
    for _ in range(3):
        d = ama.admit(e())
    assert "neural_memory_queue" in d.destinations


def test_every_decision_is_logged_with_reason():
    db, ama = mk()
    ama.admit(Experience("a b c", "d e f"))
    ama.admit(Experience("a b c", "d e f"))
    rows = db.conn.execute("SELECT decision, reason FROM admission_log").fetchall()
    assert len(rows) == 2 and all(r["reason"] for r in rows)


def test_baseline_stores_everything():
    db = Database()
    b = StoreEverything(db)
    for _ in range(3):
        b.admit(Experience("x", "y"))
    assert EpisodicMemory(db).count() == 3


# ---- F-002: rewordings must merge, real contradictions must still be caught ----
import pytest

from learning.ama import answers_agree


@pytest.mark.parametrize("q,a,b", [
    ("what is the access code for project P7", "The access code for project P7 is 4821", "code is 4821"),
    ("what is the access code for project P7", "4821", "The code is 4821."),
    ("capital of france", "It is Paris", "The capital of France is Paris"),
    ("capital of france", "Paris", "Paris."),
    ("what is 6*7", "42", "The answer is 42"),
])
def test_rewordings_of_the_same_answer_agree(q, a, b):
    assert answers_agree(q, a, b) and answers_agree(q, b, a)


@pytest.mark.parametrize("q,a,b", [
    ("access code for project P7", "code is 4821", "code is 4812"),             # transposed digits
    ("access code for project P7", "code is 4821", "code is not 4821"),          # negation, same value
    ("access code for project P7", "code is 4821", "code is 4821 or 9999"),      # hedged extra value
    ("access code for project P7", "code is 4821", "I do not know"),            # value vs none
    ("capital of france", "Paris", "Lyon"),
    ("capital of france", "It is Paris", "It is Lyon"),
    ("capital of france", "Paris", "Paris is not the capital"),
    ("meeting day", "The meeting is on Monday", "The meeting is on Friday"),
])
def test_real_contradictions_are_not_merged(q, a, b):
    assert not answers_agree(q, a, b) and not answers_agree(q, b, a)


def test_reworded_answer_is_merged_not_flagged_for_review():
    db, ama = mk()
    ama.admit(Experience("what is the access code for project P7", "The access code for project P7 is 4821", verification_status="verified"))
    d = ama.admit(Experience("what is the access code for project P7", "code is 4821", verification_status="verified"))
    assert d.decision == "MERGED" and EpisodicMemory(db).count() == 1


def test_contradiction_is_still_review_required_after_the_fix():
    db, ama = mk()
    ama.admit(Experience("what is the access code for project P7", "The access code for project P7 is 4821", verification_status="verified"))
    d = ama.admit(Experience("what is the access code for project P7", "code is 4812", verification_status="unverified"))
    assert d.decision == "REVIEW_REQUIRED"


# ---- surprise is now computed (it used to be a constant 0) ----
def test_surprise_is_prediction_error_against_prior_belief():
    from learning.ama import surprise_from_prior
    q = "what is the access code for project P7"
    assert surprise_from_prior(q, "code is 4821", None) == 0.0                 # no prior belief -> nothing to be surprised by
    assert surprise_from_prior(q, "code is 4821", "The access code for project P7 is 4821") == 0.0
    assert surprise_from_prior(q, "code is 4812", "The access code for project P7 is 4821") == 1.0


def test_controller_passes_surprise_to_ama():
    import json
    from brain.controller import Controller
    from foundation.language_model import EchoModel
    db = Database()
    ama = AMA(db)
    q = "what did I say about project p7"
    ama.admit(Experience(q, "code is 4821", verification_status="user_corrected"))        # memory already believes this
    Controller(EchoModel(), ama=ama).handle(q)                                           # echo model answers something else
    feats = json.loads(db.conn.execute("SELECT features FROM admission_log ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert feats["surprise"] == 1.0
