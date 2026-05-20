#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.router import resolve_targets
from synkraken.storage import Storage


class RoomAdapter:
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
        phase = str(message.metadata.get("phase") or "")
        if phase == "nominate" or "assignment" in phase:
            return AdapterReply(self.adapter_id, True, "Owner: alpha\nReviewer: beta")
        if "review" in phase:
            return AdapterReply(self.adapter_id, True, "Score: 90\nLooks good.")
        if "token" in phase:
            return AdapterReply(self.adapter_id, True, "Token review: compact. No warning.")
        if "guardrail" in phase:
            return AdapterReply(self.adapter_id, True, "CLEAR")
        return AdapterReply(self.adapter_id, True, f"{self.adapter_id} {phase} ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "room-membership.sqlite3")
        fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}, "goal": {"max_rounds": 1}}, storage)
        adapters = {name: RoomAdapter(name) for name in ("alpha", "beta", "gamma")}
        fabric.adapters = adapters
        storage.sync_agents([adapter.health() for adapter in adapters.values()])
        storage.create_room("crew", "Crew", "2026-05-20T00:00:00+00:00", ["alpha", "beta"])

        fabric.add_room_member("crew", "gamma", actor="smoke")
        assert set(storage.get_room_members("crew")) == {"alpha", "beta", "gamma"}
        fabric.remove_room_member("crew", "gamma", actor="smoke")
        assert set(storage.get_room_members("crew")) == {"alpha", "beta"}
        assert resolve_targets("operator", "room:crew", adapters.keys(), storage) == ["alpha", "beta"]

        team = fabric.team_task({
            "source": "smoke",
            "room_name": "crew",
            "question": "Check removed agent exclusion",
        })
        assert "gamma" not in team["agents"]
        assert not adapters["gamma"].messages

        goal = fabric.goal_run({
            "source": "smoke",
            "room_name": "crew",
            "goal": "Check goal membership exclusion",
            "threshold": 80,
            "max_rounds": 1,
        })
        assert "gamma" not in goal["goal_run"]["participants"]
        assert not adapters["gamma"].messages

        transcript = "\n".join(message["body"] for message in storage.get_room_messages("crew", limit=200))
        assert "Room member added: gamma" in transcript
        assert "Room member removed: gamma" in transcript

    print("room membership smoke test: ok")


if __name__ == "__main__":
    main()
