"""Storage-layer correctness, including the INSERT OR REPLACE data-loss fixes."""
from __future__ import annotations

import pytest

from synkraken.models import FabricMessage
from synkraken.storage import Storage


@pytest.fixture()
def storage(tmp_path):
    return Storage(tmp_path / "test.db")


def test_wal_and_busy_timeout_enabled(storage):
    assert storage._conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert storage._conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000


def test_recreate_mission_preserves_children(storage):
    storage.create_mission(mission_id="m1", title="M1", status="active", workers=["a1"])
    storage.create_outcome(outcome_id="o1", mission_id="m1", title="O1", status="in_progress")

    # Re-creating an existing mission must NOT cascade-delete its children.
    storage.create_mission(mission_id="m1", title="renamed", status="active")

    assert storage.get_mission("m1")["title"] == "renamed"
    outcomes = storage._conn.execute(
        "SELECT COUNT(*) FROM outcomes WHERE mission_id='m1'"
    ).fetchone()[0]
    workers = storage._conn.execute(
        "SELECT COUNT(*) FROM mission_workers WHERE mission_id='m1'"
    ).fetchone()[0]
    assert outcomes == 1
    assert workers == 1


def test_save_message_is_idempotent_with_deliveries(storage):
    msg = FabricMessage(
        message_id="msg1",
        conversation_id="c1",
        source="operator",
        target="echo",
        body="hello",
    )
    storage.save_message(msg)
    # Re-saving a message that already has a delivery must not raise a foreign
    # key violation (the old INSERT OR REPLACE deleted the row first).
    storage.save_message(msg)
    assert storage._conn.execute(
        "SELECT COUNT(*) FROM messages WHERE message_id='msg1'"
    ).fetchone()[0] == 1


def test_find_duplicate_memory_handles_wildcards_safely(storage):
    # A '%'/'_' bearing query must not raise and must not spuriously match on an
    # empty store (the LIKE wildcards are now escaped).
    assert storage.find_duplicate_memory("100%_progress") is None
