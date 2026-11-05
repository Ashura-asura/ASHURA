"""Public retrieval APIs reject invalid limits rather than returning surprising partial results."""
import pytest

from learning.ama import AMA
from memory.database import Database
from memory.fts import FTS5Index


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_fts_rejects_invalid_limits(limit):
    with pytest.raises(ValueError):
        FTS5Index(Database()).search("hello", limit=limit)


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_ama_rejects_invalid_limits(limit):
    with pytest.raises(ValueError):
        AMA(Database()).retrieve("hello", limit=limit)


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_ama_rejects_invalid_reliability_threshold(threshold):
    with pytest.raises(ValueError):
        AMA(Database()).retrieve("hello", min_reliability=threshold)
