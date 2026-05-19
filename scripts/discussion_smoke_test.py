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


class FakeAdapter:
    def __init__(self, adapter_id: str, *, fail_on: int | None = None) -> None:
        self.adapter_id = adapter_id
        self.fail_on = fail_on
        self.calls: list[str] = []

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id,
            "type": "fake",
            "enabled": True,
        }

    def send(self, message) -> AdapterReply:
        self.calls.append(message.body)
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            return AdapterReply(adapter_id=self.adapter_id, ok=False, body="", error="fake discussion failure")
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=True,
            body=f"{self.adapter_id} reply {len(self.calls)}",
        )


def build_fabric(path: Path) -> AgentFabric:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}}, storage)
    fabric.adapters = {
        "goose": FakeAdapter("goose"),
        "hermes": FakeAdapter("hermes"),
        "failing": FakeAdapter("failing", fail_on=1),
    }
    storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
    storage.create_room("test1", "", "2026-05-19T12:00:00+00:00", ["goose", "hermes", "failing"])
    return fabric


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
        fabric = build_fabric(Path(tmp) / "discussion.sqlite3")

        result = fabric.discuss({
            "source": "smoke-test",
            "agents": ["goose", "hermes"],
            "topic": "test discussion",
            "max_turns": 4,
        })
        assert result["status"] == "completed"
        assert len(result["turns"]) == 4
        assert [turn["agent_id"] for turn in result["turns"]] == ["goose", "hermes", "goose", "hermes"]
        assert result["turns"][-1]["final"] is True
        history = fabric.storage.get_conversation(result["conversation_id"])
        bodies = [message["body"] for message in history["messages"]]
        assert "Discussion topic: test discussion" in bodies
        assert "goose turn 1" in bodies
        assert "hermes turn 2" in bodies
        assert "goose turn 3" in bodies
        assert "hermes final recommendation" in bodies
        assert "goose reply 1" in bodies
        assert "hermes reply 2" in bodies

        short = fabric.discuss({
            "source": "smoke-test",
            "agents": ["goose", "hermes"],
            "topic": "short discussion",
            "max_turns": 2,
        })
        assert len(short["turns"]) == 2

        room_result = fabric.discuss({
            "source": "smoke-test",
            "agents": ["goose", "hermes"],
            "topic": "room discussion",
            "max_turns": 3,
            "room_name": "test1",
        })
        room_messages = fabric.storage.get_room_messages("test1", limit=50)
        room_bodies = [message["body"] for message in room_messages]
        assert room_result["room_name"] == "test1"
        assert "Discussion topic: room discussion" in room_bodies
        assert "goose turn 1" in room_bodies
        assert "goose final recommendation" in room_bodies

        failed = fabric.discuss({
            "source": "smoke-test",
            "agents": ["failing", "goose"],
            "topic": "failure discussion",
            "max_turns": 4,
        })
        assert failed["status"] == "failed"
        assert len(failed["turns"]) == 0
        assert failed["dead_letters"][0]["adapter_id"] == "failing"
        failed_history = fabric.storage.get_conversation(failed["conversation_id"])
        assert any("failing failed: fake discussion failure" == message["body"] for message in failed_history["messages"])

        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            api_result = post_json(base, "/v1/discussions", {
                "source": "smoke-test",
                "agents": ["goose", "hermes"],
                "topic": "api discussion",
                "max_turns": 2,
                "room_name": "test1",
            })
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        assert api_result["status"] == "completed"
        assert api_result["room_name"] == "test1"
        assert len(api_result["turns"]) == 2

        try:
            fabric.discuss({
                "source": "smoke-test",
                "agents": ["goose", "hermes"],
                "topic": "too many",
                "max_turns": 21,
            })
        except ValueError as exc:
            assert "max_turns" in str(exc)
        else:
            raise AssertionError("max_turns > 20 should fail")

    print("discussion smoke test: ok")


if __name__ == "__main__":
    main()
