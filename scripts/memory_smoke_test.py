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
from synkraken.models import AdapterReply
from synkraken.storage import Storage


class MemoryReviewAdapter:
    def __init__(self, adapter_id: str) -> None:
        self.adapter_id = adapter_id
        self.messages = []

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id.title(),
            "type": "fake",
            "enabled": True,
        }

    def send(self, message) -> AdapterReply:
        self.messages.append(message)
        body = str(message.body)
        proposed = body.split("Content:", 1)[-1]
        if "reject-me" in proposed:
            review = "Decision: reject\nConfidence: 40\nMemory type: fact\nReason: too vague"
        else:
            review = "Decision: approve\nConfidence: 88\nMemory type: rule\nReason: useful durable workspace guidance"
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=review, raw={"body": review})


def post_json(base: str, path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as resp:
        return json.load(resp)


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=5) as resp:
        return json.load(resp)


def build_fabric(path: Path) -> tuple[AgentFabric, dict[str, MemoryReviewAdapter]]:
    storage = Storage(path)
    fabric = AgentFabric({
        "adapters": {},
        "routing": {"retry_limit": 0},
        "memory": {
            "max_items_injected": 2,
            "max_chars_injected": 120,
            "max_memory_chars": 80,
            "min_confidence": 70,
        },
        "workspace": "smoke-workspace",
    }, storage)
    adapters = {
        "goose": MemoryReviewAdapter("goose"),
        "hermes": MemoryReviewAdapter("hermes"),
    }
    fabric.adapters = adapters
    storage.sync_agents([adapter.health() for adapter in adapters.values()])
    storage.create_room("memtest", "Shared memory test", "2026-05-19T00:00:00+00:00", ["goose", "hermes"])
    return fabric, adapters


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric, adapters = build_fabric(Path(tmp) / "memory.sqlite3")
        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            approved = post_json(base, "/v1/memory/propose", {
                "created_by": "goose",
                "room_name": "memtest",
                "memory_type": "fact",
                "content": "Always keep memory proposals concise and inspectable.",
            })
            approved_memory = approved["memory"]
            assert approved_memory["status"] == "peer_approved"
            assert approved_memory["reviewed_by"] == "hermes"
            assert approved_memory["confidence"] >= 70

            rejected = post_json(base, "/v1/memory/propose", {
                "created_by": "goose",
                "room_name": "memtest",
                "memory_type": "fact",
                "content": "reject-me",
            })
            assert rejected["memory"]["status"] == "rejected"

            duplicate = post_json(base, "/v1/memory/propose", {
                "created_by": "goose",
                "room_name": "memtest",
                "memory_type": "fact",
                "content": "Always keep memory proposals concise and inspectable.",
            })
            assert duplicate["memory"]["status"] == "rejected"
            assert duplicate.get("duplicate")

            long_memory = post_json(base, "/v1/memory/propose", {
                "created_by": "goose",
                "room_name": "memtest",
                "memory_type": "fact",
                "content": "x" * 120,
            })
            assert long_memory["memory"]["status"] == "rejected"

            pending = post_json(base, "/v1/memory/propose", {
                "created_by": "operator",
                "room_name": "memtest",
                "memory_type": "lesson",
                "content": "Pending memories must not be injected.",
                "auto_review": False,
            })
            assert pending["memory"]["status"] == "proposed"

            budget = get_json(base, "/v1/memory/budget?room=memtest")
            assert budget["injected_max_items"] == 2
            assert budget["injected_max_chars"] == 120
            assert budget["estimated_chars"] <= 120
            assert len(budget["selected"]) == 1
            assert budget["selected"][0]["memory_id"] == approved_memory["memory_id"]

            search = get_json(base, "/v1/memory/search?q=concise")
            assert any(item["memory_id"] == approved_memory["memory_id"] for item in search["memories"])

            dispatched = fabric.dispatch({
                "source": "smoke-test",
                "target": "room:memtest",
                "body": "Check approved memory injection.",
            })
            memory_context = dispatched["routing"]["memory_context"]
            assert "[SynKraken approved memory]" in memory_context
            assert "Always keep memory proposals concise and inspectable." in memory_context
            assert "reject-me" not in memory_context
            assert "Pending memories must not be injected." not in memory_context
            assert "[SynKraken approved memory]" in adapters["goose"].messages[-1].body

            fetched = get_json(base, f"/v1/memory/{approved_memory['memory_id']}")
            event_types = {event["event_type"] for event in fetched["events"]}
            assert {"memory_proposed", "peer_review_requested", "peer_approved", "memory_used"} <= event_types
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print("memory smoke test: ok")


if __name__ == "__main__":
    main()
