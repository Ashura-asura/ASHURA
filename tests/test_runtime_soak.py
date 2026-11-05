"""EXP-016 persistence check without loading a language model."""
from __future__ import annotations

from experiments.runtime.real_soak import restart_check


def test_restart_check_reads_records_from_a_fresh_process(tmp_path):
    result = restart_check(str(tmp_path))
    assert result["written"]["verified"] is True
    assert result["child"]["found"] is True
    assert result["child"]["arithmetic_found"] is True
    assert result["child"]["memory_found"] is True
    assert result["child"]["pid"] != result["written"]["pid"]
