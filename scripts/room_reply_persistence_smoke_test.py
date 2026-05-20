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
from synkraken.tui import _exec_room_command


class FakeAdapter:
    def __init__(self, adapter_id: str, body: str) -> None:
        self.adapter_id = adapter_id
        self.body = body

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id.title(),
            "type": "fake",
            "enabled": True,
        }

    def send(self, _message) -> AdapterReply:
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=self.body)


def build_fabric(path: Path) -> AgentFabric:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}}, storage)
    fabric.adapters = {
        "goose": FakeAdapter("goose", "goose reply"),
        "hermes": FakeAdapter("hermes", "hermes reply"),
    }
    storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
    storage.create_room("test1", "", "2026-05-18T12:00:00+00:00", ["goose", "hermes"])
    return fabric


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=5) as resp:
        return json.load(resp)


def post_json(base: str, path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=5) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric = build_fabric(Path(tmp) / "room-replies.sqlite3")

        # Regression: room fan-out must preserve the original room context when
        # persisting replies from the individual delivery targets.
        result = fabric.dispatch({
            "source": "operator",
            "target": "room:test1",
            "body": "room reply persistence test",
        })
        assert {delivery["delivery_target"] for delivery in result["deliveries"]} == {"goose", "hermes"}
        assert {delivery["reply_context"] for delivery in result["deliveries"]} == {"room:test1"}
        storage_messages = fabric.storage.get_room_messages("test1", limit=20)
        stored = [(m["source"], m["target"], m["body"]) for m in storage_messages]
        assert stored[0] == ("operator", "room:test1", "room reply persistence test")
        assert set(stored[1:]) == {
            ("goose", "room:test1", "goose reply"),
            ("hermes", "room:test1", "hermes reply"),
        }

        direct_result = fabric.dispatch({
            "source": "operator",
            "target": "hermes",
            "body": "chat to goose",
            "metadata": {"room_context": "room:test1"},
        })
        direct_messages = fabric.storage.get_room_messages("test1", limit=20)[-2:]
        assert direct_result["deliveries"][0]["original_target"] == "hermes"
        assert direct_result["deliveries"][0]["delivery_target"] == "hermes"
        assert direct_result["deliveries"][0]["reply_context"] == "room:test1"
        assert [(m["source"], m["target"], m["body"]) for m in direct_messages] == [
            ("operator", "room:test1", "chat to goose"),
            ("hermes", "room:test1", "hermes reply"),
        ]

        # API-level assertion: room transcript endpoint must expose the stored
        # outbound message plus replies, not just prove target resolution.
        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            api_result = post_json(base, "/v1/messages", {
                "source": "operator",
                "target": "room:test1",
                "body": "api room transcript test",
            })
            transcript = get_json(base, "/v1/rooms/test1/messages?limit=20")
            state: dict = {}
            label, room_result, hint = _exec_room_command(base, "enter test1", state, {})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        api_messages = transcript["messages"][-3:]
        assert api_result["message"]["target"] == "room:test1"
        api_stored = [(m["source"], m["target"], m["body"]) for m in api_messages]
        assert api_stored[0] == ("operator", "room:test1", "api room transcript test")
        assert set(api_stored[1:]) == {
            ("goose", "room:test1", "goose reply"),
            ("hermes", "room:test1", "hermes reply"),
        }
        assert label == "#test1"
        assert state["current_room"] == "test1"
        assert room_result is not None
        assert room_result["messages"][-3:] == api_messages
        assert "type to chat" in hint

    print("room reply persistence smoke test: ok")


if __name__ == "__main__":
    main()
