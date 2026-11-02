import os

from brain.working_memory import WorkingMemory
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from memory.fts import FTS5Index
from memory.index import MemoryIndex


def test_fts_implements_interface_and_roundtrip():
    db = Database()
    idx = FTS5Index(db)
    assert isinstance(idx, MemoryIndex)
    idx.add("a", "the access code for project alpha is 4821")
    idx.add("b", "bananas are yellow")
    hits = idx.search("alpha access code")
    assert hits[0][0] == "a"
    idx.delete("a")
    assert idx.search("alpha") == []


def test_fts_survives_hostile_query():
    idx = FTS5Index(Database())
    idx.add("a", "hello world")
    assert idx.search('"; DROP TABLE x; -- AND OR NEAR(') is not None
    assert idx.search("???") == []


def test_episodic_filter_delete_and_defaults():
    db = Database()
    m = EpisodicMemory(db)
    a = m.add(Experience("2+2", "4", task_category="arithmetic", verification_status="verified"))
    m.add(Experience("hi", "hello"))
    assert m.get(a).reliability == 1.0
    assert len(m.filter(category="arithmetic")) == 1
    assert len(m.filter(status="unverified")) == 1
    m.delete(a)
    assert m.get(a) is None and m.count() == 1


def test_persistence_across_restart(tmp_path):
    p = str(tmp_path / "t.db")
    db = Database(p)
    e = Experience("q", "a", verification_status="verified")
    EpisodicMemory(db).add(e)
    FTS5Index(db).add(e.id, e.text)
    db.close()
    db2 = Database(p)
    assert EpisodicMemory(db2).get(e.id).output == "a"
    assert FTS5Index(db2).search("q")[0][0] == e.id


def test_working_memory_bounded_and_expiring():
    t = [0.0]
    wm = WorkingMemory(slots=2, ttl_s=10, clock=lambda: t[0])
    wm.put("a", 1); wm.put("b", 2); wm.put("c", 3)
    assert wm.get("a") is None and wm.get("c") == 3 and len(wm) == 2
    t[0] = 11
    assert len(wm) == 0


# ---- deletion integrity (regression: deleted items used to stay in the FTS5 index and facts) ----
def _admit_verified(db, q="code for project p1", a="code is 4821"):
    from learning.ama import AMA
    return AMA(db).admit(Experience(q, a, verification_status="verified"))


def test_delete_removes_search_entry_fact_and_queue():
    db = Database()
    d = _admit_verified(db)
    assert FTS5Index(db).search("code project p1")
    assert EpisodicMemory(db).delete(d.exp_id) is True
    c = db.conn
    assert FTS5Index(db).search("code project p1") == []
    assert FTS5Index(db).count() == 0
    assert c.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM dream_queue").fetchone()[0] == 0
    assert EpisodicMemory(db).get(d.exp_id) is None


def test_delete_missing_returns_false_and_changes_nothing():
    db = Database()
    d = _admit_verified(db)
    assert EpisodicMemory(db).delete("nope") is False
    assert EpisodicMemory(db).count() == 1 and FTS5Index(db).count() == 1 and d.exp_id


def test_delete_only_touches_the_target():
    db = Database()
    a = _admit_verified(db, "code for project p1", "code is 4821")
    b = _admit_verified(db, "code for project p2", "code is 1111")
    EpisodicMemory(db).delete(a.exp_id)
    assert [i for i, _ in FTS5Index(db).search("code project")] == [b.exp_id]
    assert db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 1


def test_delete_scrubs_related_ids_of_other_records():
    from learning.ama import AMA
    db = Database()
    ama = AMA(db)
    old = ama.admit(Experience("code for project p1", "code is 9999"))
    new = ama.admit(Experience("code for project p1", "code is 4821", verification_status="user_corrected"))
    assert old.exp_id in EpisodicMemory(db).get(new.exp_id).related_ids
    EpisodicMemory(db).delete(old.exp_id)
    assert old.exp_id not in EpisodicMemory(db).get(new.exp_id).related_ids


def test_delete_works_by_raw_sql_too(tmp_path):
    """The guarantee lives in the database (triggers), not only in the Python helper."""
    db = Database(str(tmp_path / "t.db"))
    d = _admit_verified(db)
    db.conn.execute("DELETE FROM experiences WHERE id = ?", (d.exp_id,))
    db.conn.commit()
    assert FTS5Index(db).count() == 0 and db.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0


def test_reconcile_repairs_database_written_before_the_fix():
    db = Database()
    d = _admit_verified(db)
    c = db.conn
    # simulate the old bug: row gone, but index entry and an orphaned fact left behind
    c.execute("DROP TRIGGER trg_exp_delete_fts"); c.execute("DROP TRIGGER trg_exp_delete_facts")
    c.execute("DELETE FROM experiences WHERE id = ?", (d.exp_id,)); c.commit()
    assert FTS5Index(db).count() == 1
    out = EpisodicMemory(db).reconcile_index()
    assert out == {"stale_fts_removed": 1, "orphan_facts_removed": 1}
    assert FTS5Index(db).search("code project p1") == []
