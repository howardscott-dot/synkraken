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
        '"/v1/outcomes"',
        '"/v1/outcomes/summary"',
        '"/v1/outcomes/([^/]+)/activity"',
        '"/v1/outcomes/([^/]+)/workers"',
        '"/v1/outcomes/([^/]+)/incidents"',
        '"/v1/outcomes/([^/]+)/proposals"',
        '"/v1/missions/([^/]+)/outcomes"',
    ):
        _require(needle in api_source, f"outcome api route missing: {needle}")
    for needle in (
        "def list_outcomes",
        "def get_outcome",
        "def list_mission_outcomes",
        "def outcome_summary",
        "def outcome_activity",
        "def outcome_workers",
        "def outcome_proposals",
        "def outcome_incidents",
        "OUTCOME_STATUSES",
        "current_outcome_for_worker",
        "current_outcome_for_room",
    ):
        _require(needle in storage_source, f"outcome storage read model missing: {needle}")
    _require("outcome: str | None = None" in fabric_source, "fabric outcome activity filter missing")
    for needle in (
        "Outcome Centre",
        "Outcome Summary",
        "ops-table-outcomes",
        'type === "outcome"',
        "OutcomeNode",
        'value=\"outcome\"',
        "OutcomeDetailView",
        "current_outcome",
        "outcomeFilter",
        "Outcome impacted",
    ):
        _require(needle in app_source, f"console outcome governance wiring missing: {needle}")
    _require("ops-table-outcomes" in css_source, "outcome table CSS missing")
    for needle in ("Outcome", "OutcomeSummary", "getOutcomes", "getOutcomeSummary", "getOutcomeActivity", "getMissionOutcomes"):
        _require(needle in client_source, f"outcome API client missing: {needle}")

    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "outcome-governance.db")
        storage.sync_agents([
            {"adapter_id": "claude", "runtime_name": "Claude", "type": "claude", "enabled": True},
            {"adapter_id": "hermes", "runtime_name": "Hermes", "type": "hermes", "enabled": True},
        ])
        now = datetime.now(timezone.utc)
        older = (now - timedelta(minutes=8)).isoformat()
        recent = (now - timedelta(seconds=40)).isoformat()
        storage.create_room("research", "Research", older, members=["claude", "hermes"])
        message = FabricMessage(
            source="operator",
            target="room:research",
            body="prepare recommendation",
            message_id="msg-outcome",
            conversation_id="trace-outcome",
            timestamp=recent,
        ).normalized()
        storage.save_message(message)
        storage.save_delivery("msg-outcome", AdapterReply(adapter_id="claude", ok=True, body="recommendation drafted"), recent, status="replied")
        storage.save_dead_letter("msg-outcome", "hermes", "timeout", {"message_id": "msg-outcome"}, recent)
        proposal = storage.create_proposal(
            proposal_id="prop-outcome",
            created_at=recent,
            proposal_type="write",
            title="Approve recommendation",
            summary="Approve the outcome recommendation",
            details="",
            proposed_by="claude",
            room_id="research",
            task_id=None,
            goal_id=None,
            linked_decision_ids=[],
            linked_handoff_ids=[],
            linked_message_ids=["msg-outcome"],
            execution_payload={},
            risk_level="medium",
            requires_approval=True,
            approval_reason="operator approval required",
        )
        _require(proposal["proposal_id"] == "prop-outcome", "proposal fixture failed")
        storage.create_mission(
            mission_id="mission-governance",
            title="Review MCP Governance",
            description="Outcome governance smoke mission",
            status="active",
            priority="high",
            created_at=older,
            updated_at=recent,
            owner="operator",
            goal="Produce governance recommendation",
            risk_level="medium",
            workers=["claude"],
            rooms=["research"],
            traces=["trace-outcome"],
            incidents=["1"],
            proposals=["prop-outcome"],
        )
        completed = storage.create_outcome(
            outcome_id="outcome-research-completed",
            mission_id="mission-governance",
            title="Research Completed",
            description="Research evidence gathered",
            status="completed",
            confidence="high",
            owner="claude",
            created_at=older,
            updated_at=recent,
            completed_at=recent,
            workers=["claude"],
            traces=["trace-outcome"],
        )
        in_progress = storage.create_outcome(
            outcome_id="outcome-recommendation-produced",
            mission_id="mission-governance",
            title="Recommendation Produced",
            description="Recommendation ready for approval",
            status="in_progress",
            confidence="medium",
            owner="claude",
            created_at=older,
            updated_at=recent,
            workers=["claude"],
            traces=["trace-outcome"],
            incidents=["1"],
            proposals=["prop-outcome"],
        )
        _require(completed["status"] == "completed", "completed outcome creation failed")
        _require(in_progress["status"] == "in_progress", "in-progress outcome creation failed")
        _require(storage.get_outcome("outcome-recommendation-produced") is not None, "get_outcome failed")
        _require(len(storage.list_mission_outcomes("mission-governance")) == 2, "list_mission_outcomes failed")
        _require(storage.outcome_summary()["in_progress"] == 1, "outcome summary in_progress count failed")
        _require(storage.outcome_workers("outcome-recommendation-produced")[0]["adapter_id"] == "claude", "outcome workers failed")
        _require(storage.outcome_proposals("outcome-recommendation-produced")[0]["proposal_id"] == "prop-outcome", "outcome proposals failed")
        _require(storage.outcome_incidents("outcome-recommendation-produced")[0]["incident_id"] == "1", "outcome incidents failed")

        mission = storage.get_mission("mission-governance")
        _require(mission is not None, "mission lookup failed")
        _require(mission["progress"]["completed"] == 1, "mission outcome progress completed count failed")
        _require(mission["progress"]["total"] == 2, "mission outcome progress total failed")
        _require(mission["progress"]["percent"] == 50, "mission outcome progress percent failed")

        activity = storage.outcome_activity("outcome-recommendation-produced", limit=20) or []
        _require(activity, "outcome activity missing")
        _require(all("outcome-recommendation-produced" in record.get("outcome_ids", []) for record in activity), "outcome activity records are not tagged")
        filtered = storage.list_live_activity(limit=20, outcome="outcome-recommendation-produced")["activity"]
        _require(filtered and all(record["outcome_id"] == "outcome-recommendation-produced" for record in filtered), "outcome activity filter failed")

        rooms = {room["name"]: room for room in storage.list_rooms()}
        _require(rooms["research"]["current_outcome"]["title"] == "Recommendation Produced", "room current outcome missing")
        presence = {worker["runtime_id"]: worker for worker in storage.workforce_presence()["workers"]}
        _require(presence["claude"]["current_outcome"]["title"] == "Recommendation Produced", "worker current outcome missing")
        relationships = storage.list_canvas_relationships()
        kinds = {relationship["kind"] for relationship in relationships if relationship["source_type"] in {"mission", "outcome"}}
        _require({"has_outcome", "contributed_by", "has_proposal", "impacted_by_incident", "evidenced_by_trace"} <= kinds, "outcome canvas relationships missing")

        fabric = AgentFabric({"adapters": {}}, storage)

        class BoundHandler(FabricRequestHandler):
            pass

        BoundHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), BoundHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            _require(_get_json(base, "/v1/outcomes")["outcomes"][0]["outcome_id"], "GET /v1/outcomes failed")
            _require(_get_json(base, "/v1/outcomes/summary")["in_progress"] == 1, "GET /v1/outcomes/summary failed")
            _require(_get_json(base, "/v1/outcomes/outcome-recommendation-produced")["title"] == "Recommendation Produced", "GET /v1/outcomes/{id} failed")
            _require(_get_json(base, "/v1/missions/mission-governance/outcomes")["outcomes"], "GET /v1/missions/{id}/outcomes failed")
            _require(_get_json(base, "/v1/outcomes/outcome-recommendation-produced/activity")["activity"], "GET /v1/outcomes/{id}/activity failed")
            _require(_get_json(base, "/v1/outcomes/outcome-recommendation-produced/workers")["workers"][0]["adapter_id"] == "claude", "GET /v1/outcomes/{id}/workers failed")
            _require(_get_json(base, "/v1/outcomes/outcome-recommendation-produced/incidents")["incidents"][0]["incident_id"] == "1", "GET /v1/outcomes/{id}/incidents failed")
            _require(_get_json(base, "/v1/outcomes/outcome-recommendation-produced/proposals")["proposals"][0]["proposal_id"] == "prop-outcome", "GET /v1/outcomes/{id}/proposals failed")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    print("console v1.0 outcome governance smoke test: ok")


if __name__ == "__main__":
    main()
