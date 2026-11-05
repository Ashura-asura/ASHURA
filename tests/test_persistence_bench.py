"""EXP-017: a promoted NumPy candidate must survive a fresh process and roll back."""
from __future__ import annotations

from experiments.learning.persistence_bench import _case, _run_verify, write_case


def test_promoted_candidate_survives_a_fresh_process_and_rolls_back(tmp_path):
    case = _case("mul-6x7")
    written = write_case(case, 0, str(tmp_path))
    assert written["promoted"] is True

    verified = _run_verify(str(tmp_path), case["id"], 0)
    assert "error" not in verified
    assert verified["pid"] != written["pid"]
    assert verified["stable_name"] == written["stable_name"]
    assert verified["stable_sha256"] == written["stable_sha256"]
    assert verified["promoted"]["by_category"]["corrected"] == {"correct": 3, "total": 3}
    assert verified["promoted"]["by_category"]["old"] == {"correct": 20, "total": 20}
    assert verified["rollback"]["parent_name"] == "old_memory.npz"
    assert verified["rollback"]["scores"]["by_category"]["corrected"] == {"correct": 0, "total": 3}
    assert verified["rollback"]["scores"]["by_category"]["old"] == {"correct": 20, "total": 20}
