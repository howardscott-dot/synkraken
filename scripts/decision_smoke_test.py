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

        first = fabric.propose_decision({
            "title": "Use durable decision records",
            "summary": "Record workforce choices and approvals in SQLite.",
            "reason": "Operators need inspectable control-plane history.",
            "confidence": 88,
            "room_id": "general",
            "proposed_by": "operator",
            "linked_runtime_ids": ["goose"],
            "linked_message_ids": ["msg-1"],
        })["decision"]
        assert first["status"] == "proposed"
        assert first["reason"] == "Operators need inspectable control-plane history."
        assert first["linked_runtime_ids"] == ["goose"]

        decision_id = first["id"]
        assert storage.get_decision(decision_id)["id"] == decision_id
        assert storage.list_decisions(room_id="general")[0]["id"] == decision_id
        assert storage.latest_decision(room_id="general")["id"] == decision_id

        approved = fabric.approve_decision(decision_id, "operator")["decision"]
        assert approved["status"] == "approved"
        assert approved["approved_by"] == "operator"

        second = fabric.propose_decision({
            "title": "Reject this option",
            "summary": "A separate record for rejection coverage.",
            "reason": "The option is intentionally not selected.",
            "proposed_by": "operator",
        })["decision"]
        rejected = fabric.reject_decision(second["id"], "reviewer", "not the selected path")["decision"]
        assert rejected["status"] == "rejected"
        assert rejected["approved_by"] == "reviewer"
        assert len(storage.list_decision_events(decision_id) or []) >= 2
        assert len(storage.list_decision_events(second["id"]) or []) >= 2

        reloaded = Storage(db_path)
        assert reloaded.get_decision(decision_id)["status"] == "approved"
        assert reloaded.latest_decision()["id"] == second["id"]

        class Handler(FabricRequestHandler):
            pass

        Handler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            proposed = _json(f"{base}/v1/decision/propose", {
                "title": "API route shape",
                "summary": "Exercise Decision Records HTTP routes.",
                "reason": "The smoke test should cover daemon API shape.",
                "proposed_by": "api-test",
            })["decision"]
            api_id = proposed["id"]
            assert _json(f"{base}/v1/decision/{api_id}")["id"] == api_id
            assert _json(f"{base}/v1/decisions")["decisions"]
            assert _json(f"{base}/v1/decision/latest")["id"] == api_id
            assert _json(f"{base}/v1/decision/approve", {"id": api_id, "actor": "api-test"})["decision"]["status"] == "approved"
            reject_api = _json(f"{base}/v1/decision/propose", {
                "title": "API reject route",
                "summary": "Exercise reject endpoint.",
                "proposed_by": "api-test",
            })["decision"]
            assert _json(
                f"{base}/v1/decision/reject",
                {"id": reject_api["id"], "actor": "api-test", "reason": "coverage"},
            )["decision"]["status"] == "rejected"
        finally:
            server.shutdown()
            thread.join(timeout=5)

    print("decision smoke test: ok")


if __name__ == "__main__":
    main()
