"""SQLite connection-level integrity settings must be active for every Database instance."""
import sqlite3

import pytest

from memory.database import Database


def test_foreign_keys_are_enabled_on_each_connection():
    db = Database()
    try:
        assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO facts(id, text, source_exp_id, reliability, ts) VALUES(?,?,?,?,?)",
                ("fact", "orphan", "missing-experience", 1.0, 0.0),
            )
    finally:
        db.close()


@pytest.mark.parametrize("timeout", [-1, 1.5, True, "500"])
def test_database_rejects_invalid_busy_timeout(timeout):
    with pytest.raises(ValueError):
        Database(busy_timeout_ms=timeout)
