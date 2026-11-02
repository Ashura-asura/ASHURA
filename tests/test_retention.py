import json

from learning.ama import AMA
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index
from memory.retention import RetentionPolicy, apply, plan

DAY = 86400.0
NOW = 1_000 * DAY


def put(db, q, a, age_days, **kw):
    e = Experience(q, a, ts=NOW - age_days * DAY, **kw)
    EpisodicMemory(db).add(e)
    FTS5Index(db).add(e.id, e.text)
    return e.id


def test_old_unreinforced_unverified_is_forgotten_everything_else_kept():
    db = Database()
    stale = put(db, "chit chat one", "ok sure", 90)
    fresh = put(db, "chit chat two", "ok sure", 2)
    verified = put(db, "code p1", "4821", 400, verification_status="verified")
    corrected = put(db, "code p2", "1111", 400, verification_status="user_corrected")
    reinforced = put(db, "chit chat three", "ok sure", 90, repeat_count=3)
    assert [i for i, _ in plan(db, RetentionPolicy(30), NOW)] == [stale]
    forgotten = apply(db, RetentionPolicy(30), NOW)
    assert forgotten == [stale]
    mem = EpisodicMemory(db)
    assert mem.get(stale) is None and all(mem.get(i) for i in (fresh, verified, corrected, reinforced))


def test_forgotten_record_is_gone_from_search_and_logged():
    db = Database()
    stale = put(db, "chit chat one", "ok sure", 90)
    apply(db, RetentionPolicy(30), NOW)
    assert FTS5Index(db).search("chit chat one") == []
    row = db.conn.execute("SELECT decision, exp_id FROM admission_log WHERE decision='FORGOTTEN'").fetchone()
    assert row["exp_id"] == stale


def test_conflict_evidence_is_never_forgotten():
    db = Database()
    ama = AMA(db)
    ama.admit(Experience("code for project p1", "code is 4821", verification_status="verified"))
    weak = ama.admit(Experience("code for project p1", "code is 9999"))             # REVIEW_REQUIRED, related to the verified one
    db.conn.execute("UPDATE experiences SET ts = ?", (NOW - 500 * DAY,)); db.conn.commit()
    assert weak.decision == "REVIEW_REQUIRED"
    assert plan(db, RetentionPolicy(30), NOW) == []                                   # history kept (decision D-005)


def test_row_cap_forgets_oldest_candidates_but_never_reliable_data():
    db = Database()
    ids = [put(db, f"chat {i}", "ok", age) for i, age in enumerate([5, 4, 3, 2, 1])]   # all recent, all candidates by cap only
    keep = put(db, "code", "1", 1, verification_status="verified")
    forgotten = apply(db, RetentionPolicy(max_age_days=30, max_rows=4), NOW)
    assert forgotten == ids[:2]                                                        # 6 rows -> 4, oldest two go
    assert EpisodicMemory(db).get(keep) is not None
    tiny = apply(db, RetentionPolicy(max_age_days=30, max_rows=1), NOW)                # cap below what is allowed to go
    assert EpisodicMemory(db).get(keep) is not None and len(tiny) == 3                 # only the 3 candidates left; verified stays
