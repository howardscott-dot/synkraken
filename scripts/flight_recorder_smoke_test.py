#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage


def _json(url: str) -> dict:
    with urlopen(url, timeout=10) as resp:
        return json.load(resp)


def _message(message_id: str, conversation_id: str, source: str, target: str, body: str, timestamp: str) -> FabricMessage:
    return FabricMessage(
        message_id=message_id,
        conversation_id=conversation_id,
        source=source,
        target=target,
        body=body,
        timestamp=timestamp,
    ).normalized()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "synkraken.sqlite3")
        fabric = AgentFabric({"adapters": {}}, storage)

        class Handler(FabricRequestHandler):
            pass

        Handler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            empty_incident = _json(f"{base}/v1/incident/latest")
            assert empty_incident["incident"] is None
            assert empty_incident["message"] == "No incidents recorded."

            storage.save_message(_message(
                "msg-1",
                "conv-1",
                "operator",
                "goose",
                "Please review this implementation.",
                "2026-05-24T10:00:00+00:00",
            ))
            storage.save_delivery(
                "msg-1",
                AdapterReply(
                    adapter_id="goose",
                    ok=True,
                    body="Review completed.",
                    duration_ms=42,
                ),
                "2026-05-24T10:00:01+00:00",
            )
            storage.save_message(_message(
                "msg-2",
                "conv-1",
                "goose",
                "operator",
                "Review completed.",
                "2026-05-24T10:00:02+00:00",
            ))

            decision = fabric.propose_decision({
                "id": "decision-1",
                "title": "Use Goose for review work",
                "summary": "Use Goose for cheap review work.",
                "reason": "The task is bounded and low-risk.",
                "proposed_by": "operator",
                "linked_runtime_ids": ["goose"],
                "linked_message_ids": ["msg-1"],
            })["decision"]
            fabric.approve_decision(decision["id"], "operator")

            handoff = fabric.create_handoff({
                "id": "handoff-1",
                "from_agent": "goose",
                "to_agent": "hermes",
                "summary": "Continue the implementation review.",
                "recommended_next_step": "Check the replay API output.",
                "linked_message_ids": ["msg-2"],
                "linked_decision_ids": ["decision-1"],
            })["handoff"]

            replay = _json(f"{base}/v1/replay/conv-1")
            assert replay["id"] == "conv-1"
            assert replay["kind"] == "conversation"
            assert replay["summary"]["message_count"] == 2
            assert replay["summary"]["decision_count"] == 1
            assert replay["summary"]["handoff_count"] == 1
            assert replay["summary"]["failure_count"] == 0
            timestamps = [item["timestamp"] for item in replay["timeline"] if item.get("timestamp")]
            assert timestamps == sorted(timestamps)

            decision_replay = _json(f"{base}/v1/replay/{decision['id']}")
            assert decision_replay["kind"] == "decision"
            assert decision_replay["summary"]["decision_count"] == 1
            assert any(item["source"] == "decisions" for item in decision_replay["timeline"])

            handoff_replay = _json(f"{base}/v1/replay/{handoff['id']}")
            assert handoff_replay["kind"] == "handoff"
            assert handoff_replay["summary"]["handoff_count"] == 1
            assert any(item["source"] == "handoffs" for item in handoff_replay["timeline"])

            unknown = _json(f"{base}/v1/replay/not-real")
            assert unknown["kind"] == "unknown"
            assert unknown["timeline"] == []
            assert unknown["summary"]["outcome"] == "unknown"

            storage.save_message(_message(
                "msg-3",
                "conv-failed",
                "operator",
                "hermes",
                "This delivery should fail.",
                "2026-05-24T10:01:00+00:00",
            ))
            storage.save_delivery(
                "msg-3",
                AdapterReply(
                    adapter_id="hermes",
                    ok=False,
                    body="",
                    error="timeout",
                    duration_ms=1000,
                ),
                "2026-05-24T10:01:01+00:00",
            )
            storage.save_dead_letter(
                "msg-3",
                "hermes",
                "timeout",
                {"message_id": "msg-3"},
                "2026-05-24T10:01:02+00:00",
            )
            incident = _json(f"{base}/v1/incident/latest")
            assert incident["incident"]["id"] == "conv-failed"
            assert incident["incident"]["summary"]["failure_count"] == 2
            assert incident["incident"]["summary"]["outcome"] == "failed"
        finally:
            server.shutdown()
            thread.join(timeout=5)

    print("flight recorder smoke test: ok")


if __name__ == "__main__":
    main()
