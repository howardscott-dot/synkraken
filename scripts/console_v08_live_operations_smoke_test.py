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
    app_source = _read("apps/console/src/App.tsx")
    css_source = _read("apps/console/src/styles.css")

    _require('"/v1/activity/live"' in api_source, "/v1/activity/live route missing")
    _require("def live_activity" in fabric_source, "fabric live_activity wrapper missing")
    _require("def list_live_activity" in storage_source, "storage live activity read model missing")
    _require('"activity"' in app_source and "ActivityView" in app_source, "Activity screen missing")
    _require("current_activity" in app_source, "Workforce current activity column missing")
    _require("last_meaningful_action" in app_source, "Workforce last meaningful action missing")
    _require("seconds_since_activity" in app_source, "Workforce seconds since activity missing")
    _require("most_active_workers" in app_source, "Rooms most active workers context missing")
    _require("canvas-live-indicator" in css_source, "Canvas live indicator styles missing")

    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "live-operations.db")
        storage.sync_agents([
            {"adapter_id": "claude", "runtime_name": "Claude", "type": "claude", "enabled": True},
            {"adapter_id": "hermes", "runtime_name": "Hermes", "type": "hermes", "enabled": True},
            {"adapter_id": "goose", "runtime_name": "Goose", "type": "goose", "enabled": True},
        ])
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(seconds=23)).isoformat()
        older = (now - timedelta(minutes=8)).isoformat()

        storage.create_room("ops", "Operations", older, members=["claude", "hermes", "goose"])
        msg = FabricMessage(
            source="operator",
            target="room:ops",
            body="status check",
            message_id="msg-live-ops",
            conversation_id="trace-live-ops",
            timestamp=recent,
        ).normalized()
        storage.save_message(msg)
        storage.save_delivery("msg-live-ops", AdapterReply(adapter_id="claude", ok=True, body="ready"), recent, status="replied")
        storage.save_message(FabricMessage(
            source="claude",
            target="room:ops",
            body="ready",
            message_id="msg-live-ops-reply",
            conversation_id="trace-live-ops",
            reply_to="msg-live-ops",
            timestamp=recent,
        ).normalized())

        timeout_msg = FabricMessage(
            source="operator",
            target="goose",
            body="review",
            message_id="msg-timeout",
            conversation_id="trace-timeout",
            timestamp=older,
        ).normalized()
        storage.save_message(timeout_msg)
        storage.save_delivery("msg-timeout", AdapterReply(adapter_id="goose", ok=False, body="", error="timeout"), older, status="timeout")

        proposal = storage.create_proposal(
            proposal_id="prop-live",
            created_at=older,
            proposal_type="write",
            title="Record operational note",
            summary="Hermes created proposal",
            details="",
            proposed_by="hermes",
            room_id="ops",
            task_id=None,
            goal_id=None,
            linked_decision_ids=[],
            linked_handoff_ids=[],
            linked_message_ids=[],
            execution_payload={},
            risk_level="medium",
            requires_approval=True,
            approval_reason="operator approval required",
        )
        _require(proposal is not None, "proposal creation failed")
        storage.update_proposal("prop-live", {"status": "approved", "approved_by": "operator"}, actor="operator", event_type="approved")

        live = storage.list_live_activity(limit=20)
        records = live["activity"]
        summaries = [record["summary"] for record in records]

        _require({"active_workers", "recent_events", "last_activity_seconds_ago"} <= set(live["summary"]), "live summary fields incomplete")
        _require(all({"runtime", "room", "event_type", "timestamp", "summary"} <= set(record) for record in records), "activity record contract incomplete")
        _require(any("claude replied in #ops" in summary.lower() for summary in summaries), "reply summary missing")
        _require(any("goose timeout" in summary.lower() for summary in summaries), "timeout summary missing")
        _require(any("hermes created proposal" in summary.lower() for summary in summaries), "proposal summary missing")
        _require(any("operator approved proposal" in summary.lower() for summary in summaries), "approval summary missing")

        room_filtered = storage.list_live_activity(limit=20, room="ops")["activity"]
        runtime_filtered = storage.list_live_activity(limit=20, runtime="goose")["activity"]
        type_filtered = storage.list_live_activity(limit=20, event_type="timeout")["activity"]
        _require(room_filtered and all(record["room"] == "ops" for record in room_filtered), "room filter failed")
        _require(runtime_filtered and all(record["runtime"] == "goose" or record["actor"] == "goose" for record in runtime_filtered), "runtime filter failed")
        _require(type_filtered and all(record["event_type"] == "timeout" for record in type_filtered), "event type filter failed")

        presence = {worker["runtime_id"]: worker for worker in storage.workforce_presence()["workers"]}
        _require(presence["claude"]["current_activity"] == "Reply generated", "current activity not derived")
        _require(presence["claude"]["last_meaningful_action"], "last meaningful action missing")
        _require(presence["claude"]["seconds_since_activity"] is not None, "seconds since activity missing")

        rooms = {room["name"]: room for room in storage.list_rooms()}
        _require(rooms["ops"]["most_active_workers"], "room most active workers missing")
        _require(rooms["ops"]["last_room_event"], "room last event missing")
        _require(rooms["ops"]["activity_rate_label"], "room activity rate missing")

    print("console v0.8 live operations awareness smoke test: ok")


if __name__ == "__main__":
    main()
