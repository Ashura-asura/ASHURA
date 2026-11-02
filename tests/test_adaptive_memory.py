import numpy as np

from learning.ama import AMA
from memory.adaptive_memory import AdaptiveMemory, AMemConfig, drain_neural_queue
from memory.database import Database
from memory.episodic import Experience


def test_bounded_parameters():
    m = AdaptiveMemory(AMemConfig(dim_k=64, dim_v=32))
    assert m.param_count == 64 * 32
    for i in range(500):
        m.write(f"key {i}", f"v{i}")
    assert m.M.shape == (32, 64)                       # does not grow with experience


def test_learns_one_association_in_one_step():
    m = AdaptiveMemory(AMemConfig(lr=1.0, idf=False))
    m.write("access code project alpha", "4821")
    got, cos = m.recall("access code project alpha", ["1111", "4821", "9999"])
    assert got == "4821" and cos > 0.99


def test_unwritten_memory_recalls_nothing():
    assert AdaptiveMemory().recall("anything", ["a", "b"]) == ("", 0.0)


def test_surprise_drops_after_learning_and_gate_skips_known_pairs():
    m = AdaptiveMemory(AMemConfig(lr=1.0, idf=False, surprise_gate=0.05))
    s1 = m.write("k one", "v1")
    before = m.M.copy()
    s2 = m.write("k one", "v1")
    assert s1 > 0.9 and s2 < 0.05 and np.array_equal(before, m.M)


def test_reset_restores_fresh_state_independently_of_other_stores():
    db = Database()
    m = AdaptiveMemory()
    m.write("a b", "c")
    m.reset()
    assert not m.M.any() and not m.S.any() and m.n_writes == 0 and not m.df


def test_decay_forgets():
    m = AdaptiveMemory(AMemConfig(lr=1.0, idf=False, decay=0.2))
    m.write("old fact", "OLD")
    for i in range(30):
        m.write(f"filler {i}", f"f{i}")
    assert np.linalg.norm(m.read("old fact")) < 0.5


def test_deterministic_across_instances():
    a, b = AdaptiveMemory(AMemConfig(seed=3)), AdaptiveMemory(AMemConfig(seed=3))
    for m in (a, b):
        m.write("x y z", "w")
    assert np.array_equal(a.M, b.M)


def test_save_load_roundtrip(tmp_path):
    m = AdaptiveMemory(AMemConfig(momentum=0.3))
    for i in range(20):
        m.write(f"project p{i} code", f"{1000 + i}")
    p = str(tmp_path / "mem.npz")
    m.save(p)
    m2 = AdaptiveMemory.load(p, AMemConfig(momentum=0.3))
    assert np.array_equal(m.M, m2.M) and np.array_equal(m.S, m2.S) and m.df == m2.df
    assert np.array_equal(m.read("project p3 code"), m2.read("project p3 code"))


def test_drain_ama_queue_into_memory():
    db = Database()
    ama = AMA(db)
    mem = AdaptiveMemory(AMemConfig(lr=1.0, idf=False))
    for _ in range(3):
        ama.admit(Experience("what is 7*8", "56", task_category="arithmetic", verification_status="verified"))
    assert drain_neural_queue(db, mem) == 1
    assert mem.recall("what is 7*8", ["55", "56", "57"])[0] == "56"
    assert drain_neural_queue(db, mem) == 0            # queue emptied


# ---- same-key conflicts (F-009 / EXP-005) ----
def test_adaptive_memory_has_no_reliability_gate_latest_write_wins():
    """Documented property: the neural memory overwrites. Protection comes from what AMA lets into its queue."""
    from memory.adaptive_memory import AdaptiveMemory, AMemConfig
    m = AdaptiveMemory(AMemConfig(lr=0.6))
    cb = ["4821", "9999"]
    m.write("access code project p1", "4821")
    assert m.recall("access code project p1", cb)[0] == "4821"
    m.write("access code project p1", "9999")                      # conflicting claim, same key
    assert m.recall("access code project p1", cb)[0] == "9999"


def test_ama_blocks_the_weaker_claim_before_it_could_reach_the_neural_queue():
    from learning.ama import AMA
    from memory.database import Database
    from memory.episodic import Experience
    db = Database(); ama = AMA(db)
    ama.admit(Experience("access code project p1", "code is 4821", verification_status="trusted_material"))
    d = ama.admit(Experience("access code project p1", "code is 9999", verification_status="unverified"))
    assert d.decision == "REVIEW_REQUIRED"
    assert db.conn.execute("SELECT COUNT(*) FROM dream_queue WHERE exp_id = ?", (d.exp_id,)).fetchone()[0] == 0
