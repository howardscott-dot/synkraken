from __future__ import annotations

from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.storage import Storage


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _json(base: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    request = Request(f"{base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    prd = _read("docs/prds/2026-06-01-v11-workforce-assignment-and-handoffs.md")
    api_source = _read("synkraken/api.py")
    storage_source = _read("synkraken/storage.py")

    for heading in ("problem", "user workflow", "architecture", "read models", "ui changes", "apis", "acceptance criteria", "testing plan", "out of scope"):
        _require(heading in prd.lower(), f"PRD section missing: {heading}")
    for needle in (
        "/v1/assignments",
        "/v1/assignments/summary",
        "/v1/assignments/([^/]+)/activity",
        "/v1/assignments/([^/]+)/handoffs",
        "/v1/workforce/([^/]+)/assignments",
        "/v1/missions/([^/]+)/assignments",
        "/v1/outcomes/([^/]+)/assignments",
        "/v1/rooms/([^/]+)/assignments",
    ):
        _require(needle in api_source, f"assignment API route missing: {needle}")
    for needle in (
        "def create_assignment",
        "def update_assignment",
        "def list_assignments",
        "def get_assignment",
        "def assignment_summary",
        "def worker_assignments",
        "def mission_assignments",
        "def outcome_assignments",
        "def room_assignments",
    ):
        _require(needle in storage_source, f"assignment storage method missing: {needle}")

    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "assignment.db")
        storage.sync_agents([
            {"adapter_id": "sherlock", "runtime_name": "Sherlock", "type": "claude", "enabled": True},
            {"adapter_id": "claude", "runtime_name": "Claude", "type": "claude", "enabled": True},
        ])
        now = datetime.now(timezone.utc).isoformat()
        storage.create_room("ops", "Operations", now, members=["sherlock", "claude"])
        storage.create_mission(mission_id="mission-pricing", title="Studio Blueprint Pricing Calculator", status="active")
        storage.create_outcome(outcome_id="outcome-mvp", mission_id="mission-pricing", title="Release calculator MVP", status="in_progress")
        assignment = storage.create_assignment(
            assignment_id="assign-tier-logic",
            title="Define tier logic",
            description="Define pricing tiers and evidence.",
            owner_worker="sherlock",
            contributor_workers=["claude"],
            mission_id="mission-pricing",
            outcome_id="outcome-mvp",
            room_id="ops",
            created_at=now,
        )
        _require(assignment["owner_worker"] == "sherlock", "assignment owner not stored")
        _require(assignment["contributor_workers"] == ["claude"], "assignment contributors not stored")
        _require(storage.assignment_summary()["assigned"] == 1, "assignment summary failed")
        storage.update_assignment_status("assign-tier-logic", "blocked", actor="operator")
        _require(storage.get_assignment("assign-tier-logic")["status"] == "blocked", "assignment status update failed")
        storage.add_assignment_contributor("assign-tier-logic", "quill", actor="operator")
        _require("quill" in storage.get_assignment("assign-tier-logic")["contributor_workers"], "add contributor failed")
        storage.remove_assignment_contributor("assign-tier-logic", "quill", actor="operator")
        _require("quill" not in storage.get_assignment("assign-tier-logic")["contributor_workers"], "remove contributor failed")
        _require(storage.worker_assignments("sherlock")["counts"]["owned"] == 1, "worker owned assignment count failed")
        _require(storage.mission_assignments("mission-pricing")[0]["assignment_id"] == "assign-tier-logic", "mission assignments failed")
        _require(storage.outcome_assignments("outcome-mvp")[0]["assignment_id"] == "assign-tier-logic", "outcome assignments failed")
        _require(storage.room_assignments("ops")[0]["assignment_id"] == "assign-tier-logic", "room assignments failed")
        _require(storage.list_live_activity(assignment="assign-tier-logic")["activity"], "assignment activity filter failed")
        relationships = storage.list_canvas_relationships()
        kinds = {relationship["kind"] for relationship in relationships if relationship["source_type"] in {"mission", "outcome", "assignment"}}
        _require({"has_assignment", "contributes_assignment", "owned_by", "assisted_by"} <= kinds, "assignment canvas relationships missing")

        fabric = AgentFabric({"adapters": {}}, storage)

        class BoundHandler(FabricRequestHandler):
            pass

        BoundHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), BoundHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            created = _json(base, "/v1/assignments", "POST", {"title": "Write customer-facing copy", "owner_worker": "claude"})
            created_id = created["assignment_id"]
            _require(_json(base, "/v1/assignments")["assignments"], "GET /v1/assignments failed")
            _require(_json(base, "/v1/assignments/summary")["total"] >= 2, "GET /v1/assignments/summary failed")
            _require(_json(base, f"/v1/assignments/{created_id}")["owner_worker"] == "claude", "GET /v1/assignments/{id} failed")
            _require(_json(base, f"/v1/assignments/{created_id}", "PATCH", {"status": "review"})["status"] == "review", "PATCH /v1/assignments/{id} failed")
            _require(_json(base, f"/v1/workforce/claude/assignments")["counts"]["owned"] >= 1, "GET /v1/workforce/{id}/assignments failed")
            _require(_json(base, "/v1/missions/mission-pricing/assignments")["assignments"], "GET /v1/missions/{id}/assignments failed")
            _require(_json(base, "/v1/outcomes/outcome-mvp/assignments")["assignments"], "GET /v1/outcomes/{id}/assignments failed")
            _require(_json(base, "/v1/rooms/ops/assignments")["assignments"], "GET /v1/rooms/{name}/assignments failed")
        finally:
            server.shutdown()
            server.server_close()

    print("workforce assignment smoke test passed")


if __name__ == "__main__":
    main()
