#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.models import FabricMessage
from synkraken.storage import Storage


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "synkraken.db")
        storage.sync_agents([{"adapter_id": "goose", "runtime_name": "Goose", "type": "goose", "enabled": True}])
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
            actor="operator",
            created_at="2026-05-18T00:00:01+00:00",
        )
        assert task["room_name"] == "ops"
        assert task["assigned_agent_id"] == "goose"
        updated = storage.update_task("task-1", {"status": "blocked", "priority": "high"}, "operator", "2026-05-18T00:00:02+00:00")
        assert updated and updated["status"] == "blocked"
        commented = storage.add_task_comment("comment-1", "task-1", "operator", "Waiting on logs", "operator", "2026-05-18T00:00:03+00:00")
        assert commented and commented["comments"][0]["body"] == "Waiting on logs"
        assert storage.list_tasks(room_name="ops")[0]["task_id"] == "task-1"
    print("task smoke test: ok")
