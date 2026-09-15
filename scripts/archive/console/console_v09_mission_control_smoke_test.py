from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    api_source = _read("synkraken/api.py")
    storage_source = _read("synkraken/storage.py")
    fabric_source = _read("synkraken/fabric.py")
    app_source = _read("apps/console/src/App.tsx")
    css_source = _read("apps/console/src/styles.css")
    client_source = _read("apps/console/src/lib/api.ts")

    for needle in (
        '"/v1/missions"',
        '"/v1/missions/summary"',
        '"/v1/missions/([^/]+)/activity"',
        '"/v1/missions/([^/]+)/workers"',
        '"/v1/missions/([^/]+)/incidents"',
        '"/v1/missions/([^/]+)/proposals"',
    ):
        _require(needle in api_source, f"mission api route missing: {needle}")
    for needle in (
        "def list_missions",
        "def get_mission",
        "def mission_summary",
        "def mission_activity",
        "def mission_workers",
        "def mission_proposals",
        "def mission_incidents",
        "mission_relationships",
        "MISSION_STATUSES",
    ):
        _require(needle in storage_source, f"mission storage read model missing: {needle}")
    _require("mission: str | None = None" in fabric_source, "fabric live activity mission filter missing")
    for needle in (
        "Mission Centre",
        "Mission Summary",
        "ops-table-missions",
        'type === "mission"',
        "MissionNode",
        'value="mission"',
        "activeMissionOnly",
        "current_mission",
        "Mission Impact",
    ):
        _require(needle in app_source, f"console mission control wiring missing: {needle}")
    _require("ops-table-missions" in css_source, "mission table CSS missing")
    for needle in ("Mission", "MissionSummary", "getMissions", "getMissionSummary", "getMissionActivity"):
        _require(needle in client_source, f"mission API client missing: {needle}")

    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "mission-control.db")
        storage.sync_agents([
            {"adapter_id": "claude", "runtime_name": "Claude", "type": "claude", "enabled": True},
            {"adapter_id": "hermes", "runtime_name": "Hermes", "type": "hermes", "enabled": True},
        ])
        now = datetime.now(timezone.utc)
        older = (now - timedelta(minutes=5)).isoformat()
        recent = (now - timedelta(seconds=30)).isoformat()
        storage.create_room("ops", "Operations", older, members=["claude", "hermes"])
        message = FabricMessage(
            source="operator",
            target="room:ops",
            body="mission status",
            message_id="msg-mission",
            conversation_id="trace-mission",
            timestamp=recent,
        ).normalized()
        storage.save_message(message)
        storage.save_delivery("msg-mission", AdapterReply(adapter_id="claude", ok=True, body="progressing"), recent, status="replied")
        proposal = storage.create_proposal(
            proposal_id="prop-mission",
            created_at=recent,
            proposal_type="write",
            title="Record mission outcome",
            summary="Capture mission outcome",
            details="",
            proposed_by="claude",
            room_id="ops",
            task_id=None,
            goal_id=None,
            linked_decision_ids=[],
            linked_handoff_ids=[],
            linked_message_ids=["msg-mission"],
            execution_payload={},
            risk_level="medium",
            requires_approval=True,
            approval_reason="operator approval required",
        )
        _require(proposal["proposal_id"] == "prop-mission", "proposal fixture failed")
        storage.save_dead_letter("msg-mission", "hermes", "timeout", {"message_id": "msg-mission"}, recent)
        mission = storage.create_mission(
            mission_id="mission-v09",
            title="Build Release v0.9",
            description="Mission Control smoke mission",
            status="active",
            priority="high",
            created_at=older,
            updated_at=recent,
            owner="operator",
            goal="Ship mission read model",
            outcome="",
            risk_level="medium",
            workers=["claude"],
            rooms=["ops"],
            traces=["trace-mission"],
            incidents=["1"],
            proposals=["prop-mission"],
        )
        _require(mission["mission_id"] == "mission-v09", "mission creation failed")
        _require(storage.get_mission("mission-v09") is not None, "get_mission failed")
        _require(storage.mission_summary()["active_missions"] == 1, "mission summary active count failed")
        _require(storage.mission_workers("mission-v09")[0]["adapter_id"] == "claude", "mission workers failed")
        _require(storage.mission_proposals("mission-v09")[0]["proposal_id"] == "prop-mission", "mission proposals failed")
        _require(storage.mission_incidents("mission-v09")[0]["incident_id"] == "1", "mission incidents failed")

        activity = storage.mission_activity("mission-v09", limit=20) or []
        _require(activity, "mission activity missing")
        _require(all("mission-v09" in record.get("mission_ids", []) for record in activity), "mission activity records are not tagged")
        filtered = storage.list_live_activity(limit=20, mission="mission-v09")["activity"]
        _require(filtered and all(record["mission_id"] == "mission-v09" for record in filtered), "mission activity filter failed")
        active_filtered = storage.list_live_activity(limit=20, active_missions=True)["activity"]
        _require(active_filtered and all("mission-v09" in record.get("mission_ids", []) for record in active_filtered), "active mission activity filter failed")

        rooms = {room["name"]: room for room in storage.list_rooms()}
        _require(rooms["ops"]["current_mission"]["title"] == "Build Release v0.9", "room mission association missing")
        presence = {worker["runtime_id"]: worker for worker in storage.workforce_presence()["workers"]}
        _require(presence["claude"]["current_mission"]["title"] == "Build Release v0.9", "worker mission association missing")
        relationships = storage.list_canvas_relationships()
        kinds = {relationship["kind"] for relationship in relationships if relationship["source_type"] == "mission"}
        _require({"involves_worker", "uses_room", "has_proposal", "impacted_by_incident"} <= kinds, "mission canvas relationships missing")

        fabric = AgentFabric({"adapters": {}}, storage)

        class BoundHandler(FabricRequestHandler):
            pass

        BoundHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), BoundHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            _require(_get_json(base, "/v1/missions")["missions"][0]["mission_id"] == "mission-v09", "GET /v1/missions failed")
            _require(_get_json(base, "/v1/missions/summary")["active_missions"] == 1, "GET /v1/missions/summary failed")
            _require(_get_json(base, "/v1/missions/mission-v09")["title"] == "Build Release v0.9", "GET /v1/missions/{id} failed")
            _require(_get_json(base, "/v1/missions/mission-v09/activity")["activity"], "GET /v1/missions/{id}/activity failed")
            _require(_get_json(base, "/v1/missions/mission-v09/workers")["workers"][0]["adapter_id"] == "claude", "GET /v1/missions/{id}/workers failed")
            _require(_get_json(base, "/v1/missions/mission-v09/incidents")["incidents"][0]["incident_id"] == "1", "GET /v1/missions/{id}/incidents failed")
            _require(_get_json(base, "/v1/missions/mission-v09/proposals")["proposals"][0]["proposal_id"] == "prop-mission", "GET /v1/missions/{id}/proposals failed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    print("console v0.9 mission control smoke test: ok")


if __name__ == "__main__":
    main()
