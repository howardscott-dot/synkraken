#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.storage import Storage


class FakeAdapter:
    def __init__(self, adapter_id: str, *, ok: bool = True, error: str | None = None) -> None:
        self.adapter_id = adapter_id
        self.ok = ok
        self.error = error

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id.title(),
            "type": "fake",
            "runtime": "fake",
            "enabled": True,
        }

    def send(self, _message) -> AdapterReply:
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=self.ok,
            body=f"{self.adapter_id} reply" if self.ok else "",
            error=None if self.ok else (self.error or "fake failure"),
        )


def build_fabric(path: Path) -> AgentFabric:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}}, storage)
    fabric.adapters = {
        "goose": FakeAdapter("goose"),
        "hermes": FakeAdapter("hermes"),
        "slow": FakeAdapter("slow", ok=False, error="fake timed out"),
    }
    storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
    return fabric


def event_types(storage: Storage, agent_id: str) -> list[str]:
    events = storage.list_agent_events(agent_id, limit=100)
    assert events is not None
    return [event["event_type"] for event in events]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "offline.sqlite3")
        storage.sync_agents([{
            "adapter_id": "old-agent",
            "runtime_name": "Old Agent",
            "type": "fake",
            "enabled": True,
        }])
        assert storage.get_agent("old-agent")["status"] == "online"
        storage.sync_agents([])
        assert storage.get_agent("old-agent")["status"] == "offline"

    with tempfile.TemporaryDirectory() as tmp:
        fabric = build_fabric(Path(tmp) / "presence.sqlite3")
        storage = fabric.storage

        assert storage.get_agent("goose")["status"] == "online"
        assert storage.get_agent("hermes")["status"] == "online"

        direct = fabric.dispatch({
            "source": "smoke-test",
            "target": "goose",
            "body": "presence direct",
        })
        assert direct["deliveries"][0]["ok"] is True
        assert storage.get_agent("goose")["status"] == "idle"
        goose_events = event_types(storage, "goose")
        assert "message_received" in goose_events
        assert "message_sent" in goose_events

        broadcast = fabric.dispatch({
            "source": "smoke-test",
            "target": "broadcast",
            "body": "presence broadcast",
        })
        assert {delivery["delivery_target"] for delivery in broadcast["deliveries"]} == {"goose", "hermes", "slow"}
        assert storage.get_agent("goose")["status"] == "idle"
        assert storage.get_agent("hermes")["status"] == "idle"
        assert storage.get_agent("slow")["status"] == "blocked"
        assert "timeout" in event_types(storage, "slow")

        discussion = fabric.discuss({
            "source": "smoke-test",
            "agents": ["goose", "hermes"],
            "topic": "presence discussion",
            "max_turns": 2,
        })
        assert discussion["status"] == "completed"
        assert storage.get_agent("goose")["status"] == "idle"
        assert storage.get_agent("hermes")["status"] == "idle"
        assert "discussion_started" in event_types(storage, "goose")
        assert "discussion_completed" in event_types(storage, "goose")

        assert storage.list_agents()
        assert storage.list_agent_events("missing") is None

    print("presence smoke test: ok")


if __name__ == "__main__":
    main()
