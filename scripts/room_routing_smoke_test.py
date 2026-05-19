#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.storage import Storage
from synkraken.tui import _mention_route


class FakeAdapter:
    def __init__(self, adapter_id: str, *, ok: bool = True, body: str | None = None) -> None:
        self.adapter_id = adapter_id
        self.ok = ok
        self.body = body or f"hello from {adapter_id}"

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id.title(),
            "type": "fake",
            "enabled": True,
        }

    def send(self, _message) -> AdapterReply:
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=self.ok,
            body=self.body if self.ok else "",
            error=None if self.ok else "fake delivery failure",
        )


def build_fabric(path: Path) -> AgentFabric:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}}, storage)
    fabric.adapters = {
        "goose": FakeAdapter("goose"),
        "hermes": FakeAdapter("hermes"),
        "fake": FakeAdapter("fake", ok=False),
    }
    storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
    return fabric


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric = build_fabric(Path(tmp) / "smoke.sqlite3")
        fabric.storage.create_room("test1", "", "2026-05-18T12:00:00+00:00", ["goose", "hermes", "fake"])

        target, body = _mention_route("broadcast", "welcome to the test room", "test1")
        assert target == "room:test1"
        room_result = fabric.dispatch({"source": "smoke-test", "target": target, "body": body})
        room_messages = fabric.storage.get_room_messages("test1", limit=20)
        assert room_messages[0]["body"] == "welcome to the test room"
        assert {message["source"] for message in room_messages[1:]} == {"goose", "hermes"}
        room_history = fabric.storage.get_conversation(room_result["message"]["conversation_id"])
        assert {message["source"] for message in room_history["messages"]} == {"smoke-test", "goose", "hermes"}
        assert room_result["dead_letters"][0]["adapter_id"] == "fake"

        target, body = _mention_route("broadcast", "welcome globally", None)
        assert target == "broadcast"
        global_result = fabric.dispatch({"source": "smoke-test", "target": target, "body": body})
        assert global_result["message"]["target"] == "broadcast"
        assert global_result["routing"]["resolved_targets"] == ["goose", "hermes", "fake"]
        assert {delivery["delivery_target"] for delivery in global_result["deliveries"]} == {"goose", "hermes", "fake"}
        assert {delivery["persisted_transcript_target"] for delivery in global_result["deliveries"] if delivery["ok"]} == {"broadcast"}
        broadcast_history = fabric.storage.get_conversation(global_result["message"]["conversation_id"])
        assert {message["source"] for message in broadcast_history["messages"]} == {"smoke-test", "goose", "hermes"}
        assert all(message["target"] == "room:test1" for message in room_messages)

        target, body = _mention_route("broadcast", "--global explicit global", "test1")
        assert (target, body) == ("broadcast", "explicit global")

    print("room routing smoke test: ok")


if __name__ == "__main__":
    main()
