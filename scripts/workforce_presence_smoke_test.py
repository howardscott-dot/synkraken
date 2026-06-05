from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    api_source = _read("synkraken/api.py")
    fabric_source = _read("synkraken/fabric.py")
    storage_source = _read("synkraken/storage.py")
    _require('"/v1/workforce/presence"' in api_source, "/v1/workforce/presence route missing")
    _require('"/v1/activity/recent"' in api_source, "/v1/activity/recent route missing")
    _require("def workforce_presence" in fabric_source, "fabric workforce_presence wrapper missing")
    _require("def workforce_presence" in storage_source, "storage workforce_presence read model missing")

    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "presence.db")
        storage.sync_agents([
            {"adapter_id": "claude", "runtime_name": "Claude", "type": "claude", "enabled": True},
            {"adapter_id": "antigravity", "runtime_name": "Google Antigravity", "type": "antigravity", "enabled": True},
            {"adapter_id": "idlebot", "runtime_name": "Idle Bot", "type": "hermes", "enabled": True},
        ])
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(minutes=2)).isoformat()
        old = (now - timedelta(hours=3)).isoformat()

        active_message = FabricMessage(
            source="operator",
            target="room:coding",
            body="status",
            message_id="msg-active",
            conversation_id="msg-active",
            timestamp=recent,
        )
        weak_message = FabricMessage(
            source="operator",
            target="room:ops",
            body="status",
            message_id="msg-weak",
            conversation_id="msg-weak",
            timestamp=recent,
        )
        idle_message = FabricMessage(
            source="operator",
            target="idlebot",
            body="status",
            message_id="msg-idle",
            conversation_id="msg-idle",
            timestamp=old,
        )
        storage.save_message(active_message)
        storage.save_message(weak_message)
        storage.save_message(idle_message)
        storage.save_delivery("msg-active", AdapterReply(adapter_id="claude", ok=True, body="ready"), recent, status="acknowledged")
        storage.save_delivery("msg-weak", AdapterReply(adapter_id="antigravity", ok=True, body=""), recent, status="empty_reply", quality="empty")
        storage.save_delivery("msg-idle", AdapterReply(adapter_id="idlebot", ok=True, body="done"), old, status="acknowledged")

        result = storage.workforce_presence(active_window_seconds=300)
        summary = result["summary"]
        workers = {worker["runtime_id"]: worker for worker in result["workers"]}
        activity = storage.list_recent_activity(limit=10)["activity"]

        _require({"total", "active", "idle", "watching", "needs_attention", "unavailable", "highest_priority", "suggested_next_action"} <= set(summary), "presence summary fields incomplete")
        _require(workers["claude"]["presence_state"] == "active", "recent successful delivery should produce active")
        _require(workers["idlebot"]["presence_state"] == "idle", "old successful delivery should produce idle")
        _require(workers["antigravity"]["needs_attention"], "empty reply should derive needs_attention")
        _require(workers["antigravity"]["presence_state"] == "needs_attention", "weak health should produce needs_attention presence")
        _require(workers["antigravity"]["suggested_action"], "suggested_action missing")
        _require(any(item["activity_type"] == "delivery" for item in activity), "recent activity feed missing delivery record")

    print("workforce presence smoke test: ok")


if __name__ == "__main__":
    main()
