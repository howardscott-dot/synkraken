#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.models import FabricMessage
from synkraken.storage import Storage


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "synkraken.db")
        storage.sync_agents([
            {"adapter_id": "goose", "runtime_name": "Goose", "type": "goose", "enabled": True},
            {"adapter_id": "hermes", "runtime_name": "Hermes", "type": "hermes", "enabled": True},
        ])
        storage.create_room("ops", "", "2026-05-18T00:00:00+00:00", members=["goose"])
        message = FabricMessage(source="operator", target="room:ops", body="Investigate auth").normalized()
        storage.save_message(message)
        task = storage.create_task(
            task_id="task-1",
            title="Investigate auth",
            description="",
            status="open",
            priority="normal",
            room_name="ops",
            assigned_agent_id="goose",
            source_message_id=message.message_id,
            actor="Howard",
            created_at="2026-05-18T00:00:01+00:00",
        )
        assert task["created_by"] == "Howard"
        storage.update_task("task-1", {"assigned_agent_id": "hermes"}, "Howard", "2026-05-18T00:00:02+00:00")
        storage.update_task("task-1", {"status": "blocked"}, "hermes", "2026-05-18T00:00:03+00:00")
        storage.add_task_comment("comment-1", "task-1", "Howard", "Waiting on logs", "Howard", "2026-05-18T00:00:04+00:00")
        storage.update_task("task-1", {"status": "done"}, "hermes", "2026-05-18T00:00:05+00:00")

        events = storage.list_task_events("task-1")
        assert events is not None
        assert [event["event_type"] for event in events] == [
            "created", "assigned", "status_changed", "blocked", "commented", "status_changed", "completed"
        ]

        try:
            storage.create_task(
                task_id="bad-room",
                title="bad",
                description="",
                status="open",
                priority="normal",
                room_name="missing",
                assigned_agent_id=None,
                source_message_id=None,
                actor="system",
                created_at="2026-05-18T00:00:06+00:00",
            )
            raise AssertionError("invalid room reference should fail")
        except sqlite3.IntegrityError:
            pass
        try:
            storage.create_task(
                task_id="bad-agent",
                title="bad",
                description="",
                status="open",
                priority="normal",
                room_name=None,
                assigned_agent_id="missing",
                source_message_id=None,
                actor="system",
                created_at="2026-05-18T00:00:07+00:00",
            )
            raise AssertionError("invalid agent reference should fail")
        except sqlite3.IntegrityError:
            pass
        try:
            storage.create_task(
                task_id="bad-message",
                title="bad",
                description="",
                status="open",
                priority="normal",
                room_name=None,
                assigned_agent_id=None,
                source_message_id="missing",
                actor="system",
                created_at="2026-05-18T00:00:08+00:00",
            )
            raise AssertionError("invalid source message reference should fail")
        except sqlite3.IntegrityError:
            pass

        storage.delete_room("ops")
        assert storage.get_task("task-1")["room_name"] is None
        with storage._lock, storage._conn:
            storage._conn.execute("DELETE FROM agents WHERE adapter_id = ?", ("hermes",))
            storage._conn.execute("DELETE FROM messages WHERE message_id = ?", (message.message_id,))
        after_parent_delete = storage.get_task("task-1")
        assert after_parent_delete["assigned_agent_id"] is None
        assert after_parent_delete["source_message_id"] is None
        with storage._lock, storage._conn:
            storage._conn.execute("DELETE FROM tasks WHERE task_id = ?", ("task-1",))
        assert storage.list_task_events("task-1") is None
    print("task event smoke test: ok")
