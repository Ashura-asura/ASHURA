"""Session store pagination tests (Phase 2, additive API)."""
from __future__ import annotations

import pytest

from app.sessions import SessionStore


@pytest.fixture
def store(tmp_path):
    value = SessionStore(str(tmp_path / "sessions.db"))
    yield value
    value.close()


def seed(store: SessionStore, count: int = 230) -> str:
    session = store.create("Long conversation")
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        store.append(session["id"], role, f"message-{index}")
    return session["id"]


def test_default_page_is_the_latest_200_in_ascending_order(store):
    session_id = seed(store)
    messages = store.messages(session_id)
    assert len(messages) == 200
    assert messages[0]["content"] == "message-30"
    assert messages[-1]["content"] == "message-229"
    assert [m["id"] for m in messages] == sorted(m["id"] for m in messages)
    assert store.count_messages(session_id) == 230


def test_before_walks_backwards_without_gaps_or_duplicates(store):
    session_id = seed(store, 120)
    latest = store.messages(session_id, limit=50)
    older = store.messages(session_id, limit=50, before=latest[0]["id"])
    oldest = store.messages(session_id, limit=50, before=older[0]["id"])

    assert len(latest) == len(older) == 50
    assert len(oldest) == 20
    assert older[-1]["id"] < latest[0]["id"]
    assert oldest[-1]["id"] < older[0]["id"]
    assert [m["content"] for m in oldest + older + latest] == [
        f"message-{index}" for index in range(120)]

    assert store.has_older(session_id, latest[0]["id"]) is True
    assert store.has_older(session_id, older[0]["id"]) is True
    assert store.has_older(session_id, oldest[0]["id"]) is False


def test_full_transcript_ignores_the_page_limit(store):
    session_id = seed(store, 25)
    messages = store.messages(session_id, limit=None)
    assert len(messages) == 25
    assert messages[0]["content"] == "message-0"
    assert messages[-1]["content"] == "message-24"


def test_page_limit_is_clamped_for_direct_callers(store):
    session_id = seed(store, 12)
    assert len(store.messages(session_id, limit=0)) == 1
    assert len(store.messages(session_id, limit=5000)) == 12


def test_page_before_the_oldest_message_returns_no_messages(store):
    session_id = seed(store, 5)
    oldest_id = store.messages(session_id, limit=None)[0]["id"]
    assert store.messages(session_id, limit=10, before=oldest_id) == []
    assert store.has_older(session_id, oldest_id) is False
    # An id beyond the range means "everything is older", not an error.
    assert len(store.messages(session_id, limit=10, before=10_000)) == 5
