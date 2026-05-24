#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.storage import Storage
from synkraken.tui import _parse_handoff_create_args


def _json(url: str, payload: dict | None = None) -> dict:
    if payload is None:
        with urlopen(url, timeout=10) as resp:
            return json.load(resp)
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "synkraken.sqlite3"
        storage = Storage(db_path)
        fabric = AgentFabric({"adapters": {}}, storage)

        created = fabric.create_handoff({
            "from_agent": "goose",
            "to_agent": "hermes",
            "room_id": "general",
            "task_id": "task-1",
            "goal_id": "goal-1",
            "summary": "Continue the implementation review.",
            "open_questions": ["Is the API shape complete?"],
            "risks": ["Route drift"],
            "recommended_next_step": "Verify the handoff routes.",
            "confidence": 82,
            "linked_message_ids": ["msg-1"],
            "linked_decision_ids": ["decision-1"],
        })["handoff"]
        handoff_id = created["id"]
        assert created["status"] == "pending"
        assert created["handoff_id"] == handoff_id
        assert created["room_id"] == "general"
        assert created["linked_message_ids"] == ["msg-1"]
        assert storage.get_handoff(handoff_id)["id"] == handoff_id
        assert storage.list_handoffs(room_id="general")[0]["id"] == handoff_id
        assert storage.latest_handoff(room_id="general")["id"] == handoff_id

        accepted = fabric.accept_handoff(handoff_id, "hermes")["handoff"]
        assert accepted["status"] == "accepted"
        completed = fabric.complete_handoff(handoff_id, "hermes")["handoff"]
        assert completed["status"] == "completed"

        rejected_candidate = fabric.create_handoff({
            "from_agent": "goose",
            "to_agent": "claude",
            "summary": "Reject coverage.",
            "recommended_next_step": "No action.",
        })["handoff"]
        rejected = fabric.reject_handoff(rejected_candidate["id"], "claude", "not needed")["handoff"]
        assert rejected["status"] == "rejected"
        assert len(storage.list_handoff_events(handoff_id) or []) >= 3
        assert len(storage.list_handoff_events(rejected_candidate["id"]) or []) >= 2

        reloaded = Storage(db_path)
        assert reloaded.get_handoff(handoff_id)["status"] == "completed"
        assert reloaded.latest_handoff()["id"] == rejected_candidate["id"]

        parsed = _parse_handoff_create_args(
            'from=goose to=hermes summary="Parser coverage" next="Run smoke test" confidence=75',
            "general",
        )
        assert parsed["from_agent"] == "goose"
        assert parsed["to_agent"] == "hermes"
        assert parsed["summary"] == "Parser coverage"
        assert parsed["room_id"] == "general"

        class Handler(FabricRequestHandler):
            pass

        Handler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            api_created = _json(f"{base}/v1/handoff", {
                "from_agent": "operator",
                "to_agent": "goose",
                "summary": "Exercise Handoffs HTTP routes.",
                "recommended_next_step": "Accept and complete.",
            })["handoff"]
            api_id = api_created["id"]
            assert _json(f"{base}/v1/handoff/{api_id}")["id"] == api_id
            assert _json(f"{base}/v1/handoffs")["handoffs"]
            assert _json(f"{base}/v1/handoff/latest")["id"] == api_id
            assert _json(f"{base}/v1/handoff/accept", {"id": api_id, "actor": "api-test"})["handoff"]["status"] == "accepted"
            assert _json(f"{base}/v1/handoff/complete", {"id": api_id, "actor": "api-test"})["handoff"]["status"] == "completed"
            reject_api = _json(f"{base}/v1/handoff", {
                "to_agent": "hermes",
                "summary": "Exercise reject endpoint.",
            })["handoff"]
            assert _json(
                f"{base}/v1/handoff/reject",
                {"id": reject_api["id"], "actor": "api-test", "reason": "coverage"},
            )["handoff"]["status"] == "rejected"
        finally:
            server.shutdown()
            thread.join(timeout=5)

    print("handoff smoke test: ok")


if __name__ == "__main__":
    main()
