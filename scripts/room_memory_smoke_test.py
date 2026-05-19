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
from synkraken.tui import _memory_command_lines


class RecordingAdapter:
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
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=True,
            body=f"{self.adapter_id} saw {message.body[:80]}",
            raw={"body": message.body},
        )


def build_fabric(path: Path) -> tuple[AgentFabric, dict[str, RecordingAdapter]]:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}}, storage)
    adapters = {
        "goose": RecordingAdapter("goose"),
        "hermes": RecordingAdapter("hermes"),
    }
    fabric.adapters = adapters
    storage.sync_agents([adapter.health() for adapter in adapters.values()])
    storage.create_room("test1", "Room Memory test", "2026-05-19T00:00:00+00:00", ["goose", "hermes"])
    return fabric, adapters


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=5) as resp:
        return json.load(resp)


def put_json(base: str, path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urlopen(req, timeout=5) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric, adapters = build_fabric(Path(tmp) / "room-memory.sqlite3")

        memory = fabric.storage.upsert_room_memory("test1", {
            "purpose": "Build SynKraken",
            "objective": "Implement room memory",
            "rules": "No cloud dependencies",
            "constraints": "Python stdlib preferred",
            "current_focus": "Room Memory v0.1",
            "notes": "Keep this operational, not semantic search",
        }, "smoke-test", "2026-05-19T00:01:00+00:00")
        assert memory is not None
        assert memory["room"] == "test1"
        assert memory["objective"] == "Implement room memory"
        events = fabric.storage.list_room_memory_events("test1")
        assert events is not None
        assert {event["field_changed"] for event in events} >= {"purpose", "objective", "current_focus"}

        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            api_memory = get_json(base, "/v1/rooms/test1/memory")
            assert api_memory["purpose"] == "Build SynKraken"
            updated = put_json(base, "/v1/rooms/test1/memory", {
                "objective": "Verify memory APIs",
                "actor": "api-smoke",
            })
            assert updated["objective"] == "Verify memory APIs"
            api_events = get_json(base, "/v1/rooms/test1/memory/events")
            assert any(event["actor"] == "api-smoke" for event in api_events["events"])
            state = {"current_room": "test1"}
            label, lines = _memory_command_lines("/memory", base, state)
            assert label == "#test1 memory"
            assert any("Verify memory APIs" in line for line in lines)
            _label, updated_lines = _memory_command_lines('/memory set focus "TUI command smoke"', base, state)
            assert any("TUI command smoke" in line for line in updated_lines)
            _label, edit_lines = _memory_command_lines("/memory edit", base, state)
            assert any('/memory set objective "..."' in line for line in edit_lines)
            _label, error_lines = _memory_command_lines("/memory", base, {})
            assert error_lines == ["not in a room"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        room_result = fabric.dispatch({
            "source": "smoke-test",
            "target": "room:test1",
            "body": "Does room memory reach room fanout?",
        })
        assert room_result["routing"]["memory_context"]
        assert len(room_result["routing"]["memory_context"]) <= 485
        assert {delivery["delivery_target"] for delivery in room_result["deliveries"]} == {"goose", "hermes"}
        assert "Room context:" in adapters["goose"].messages[-1].body
        assert "Purpose: Build SynKraken" in adapters["goose"].messages[-1].body
        assert "Message:\nDoes room memory reach room fanout?" in adapters["goose"].messages[-1].body

        direct_result = fabric.dispatch({
            "source": "smoke-test",
            "target": "goose",
            "body": "Does room memory reach room-scoped direct messages?",
            "metadata": {"room_context": "room:test1"},
        })
        assert direct_result["routing"]["memory_context"]
        assert "Room context:" in adapters["goose"].messages[-1].body
        assert "Does room memory reach room-scoped direct messages?" in adapters["goose"].messages[-1].body

        discussion = fabric.discuss({
            "source": "smoke-test",
            "room_name": "test1",
            "agents": ["goose", "hermes"],
            "topic": "Confirm discussion prompt receives room memory",
            "max_turns": 2,
        })
        assert discussion["status"] == "completed"
        assert discussion["memory_context"]
        assert any("Room context:" in message.body for message in adapters["goose"].messages)
        transcript = fabric.storage.get_room_messages("test1", limit=50)
        assert any(message["source"] == "goose" for message in transcript)
        assert any(message["source"] == "hermes" for message in transcript)

    print("room memory smoke test: ok")


if __name__ == "__main__":
    main()
