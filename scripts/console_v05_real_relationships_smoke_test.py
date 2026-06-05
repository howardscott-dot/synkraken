from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(text: str, needles: list[str], label: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{label} missing: {', '.join(missing)}")


def _kinds(relationships: list[dict]) -> set[str]:
    return {str(item.get("kind")) for item in relationships}


def main() -> None:
    api = _read("synkraken/api.py")
    storage_source = _read("synkraken/storage.py")
    app = _read("apps/console/src/App.tsx")
    client = _read("apps/console/src/lib/api.ts")
    prd = _read("docs/prds/2026-05-31-console-v0-5-real-canvas-relationships.md")

    _require(
        api,
        ['"/v1/canvas/relationships"', "list_canvas_relationships"],
        "daemon relationship endpoint",
    )
    _require(
        storage_source,
        [
            "def list_canvas_relationships",
            '"source_type"',
            '"target_type"',
            '"evidence"',
            '"observed_at"',
            '"proposals"',
            '"dead_letters"',
            '"runtime_reputation"',
            "latest_incident_anchor",
        ],
        "storage relationship read model",
    )
    _require(
        client,
        ["CanvasRelationship", "CanvasRelationshipsResponse", "getCanvasRelationships", "`/v1/canvas/relationships?limit="],
        "console relationship API client",
    )
    _require(
        app,
        [
            "canvasRelationships",
            "api.getCanvasRelationships",
            "buildRelationships(nodes, data.canvasRelationships)",
            "RelationshipJumpRow",
            "No daemon relationship records touch this node.",
        ],
        "console real relationship usage",
    )
    if "buildRelationships(nodes, workers" in app or "relevantProposals.some" in app:
        raise AssertionError("client-side production relationship inference remains")
    _require(
        prd,
        ["GET /v1/canvas/relationships", "Missing relationships are omitted.", "No Rust business logic is added."],
        "v0.5 PRD contract",
    )

    with TemporaryDirectory() as temp_dir:
        storage = Storage(Path(temp_dir) / "relationships.sqlite")
        storage.sync_agents([
            {
                "adapter_id": "goose",
                "runtime_name": "goose",
                "type": "goose",
                "enabled": True,
            }
        ])
        storage.create_room("ops", "Operations", "2026-05-31T00:00:00+00:00", members=["goose"])
        message = FabricMessage(
            source="operator",
            target="room:ops",
            body="Investigate failed delivery",
            message_id="msg-1",
            conversation_id="conv-1",
            timestamp="2026-05-31T00:00:01+00:00",
        ).normalized()
        storage.save_message(message)
        storage.save_delivery(
            "msg-1",
            AdapterReply(adapter_id="goose", ok=False, body="", error="timeout", duration_ms=1000, raw={}),
            "2026-05-31T00:00:02+00:00",
            status="timeout",
        )
        storage.save_dead_letter(
            "msg-1",
            "goose",
            "timeout",
            {"message_id": "msg-1"},
            "2026-05-31T00:00:03+00:00",
        )
        storage.create_proposal(
            proposal_id="prop-1",
            created_at="2026-05-31T00:00:04+00:00",
            proposal_type="retry",
            title="Retry failed delivery",
            summary="Retry the failed message",
            details="Retry msg-1",
            proposed_by="goose",
            room_id="ops",
            task_id=None,
            goal_id=None,
            linked_decision_ids=[],
            linked_handoff_ids=[],
            linked_message_ids=["msg-1"],
            execution_payload={"message_id": "msg-1"},
            risk_level="medium",
            requires_approval=True,
            approval_reason="retry requires approval",
        )
        relationships = storage.list_canvas_relationships()
        kinds = _kinds(relationships)
        expected = {
            "proposed_by",
            "contains_proposal",
            "has_proposal",
            "in_room",
            "linked_message_trace",
            "failed_message_trace",
            "has_dead_letter",
            "failed_runtime",
            "has_runtime_incident",
            "latest_incident_trace",
            "latest_incident_runtime",
            "latest_incident_dead_letter",
        }
        missing = sorted(expected - kinds)
        if missing:
            raise AssertionError(f"missing real relationship kinds: {', '.join(missing)}")
        if not all(item.get("evidence") for item in relationships):
            raise AssertionError("relationship without evidence found")

    print("console v0.5 real relationships smoke test: ok")


if __name__ == "__main__":
    main()
