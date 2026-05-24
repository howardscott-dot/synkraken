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
from synkraken.tui import _local_command_lines


class ProfileAdapter:
    def __init__(self, adapter_id: str) -> None:
        self.adapter_id = adapter_id

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id.title(),
            "type": "fake",
            "enabled": True,
        }

    def send(self, message) -> AdapterReply:
        phase = str(message.metadata.get("phase") or "")
        if phase == "nominate" or "assignment" in phase:
            body = "Owner: none\nReviewer: none\nSupport: none"
        elif "review" in phase:
            body = "Score: 90\nRisks: none.\nSuggested revision: none."
        elif "token" in phase:
            body = "Token review: compact and cheap. No warning."
        elif "guardrail" in phase:
            body = "CLEAR: architecture and scope are sound."
        else:
            body = f"{self.adapter_id} handled {phase}"
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=body, raw={"phase": phase})


def patch_json(base: str, path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urlopen(req, timeout=10) as resp:
        return json.load(resp)


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=10) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "profiles.sqlite3")
        fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}}, storage)
        adapters = {name: ProfileAdapter(name) for name in ("cheap", "premium", "local")}
        fabric.adapters = adapters
        storage.sync_agents([adapter.health() for adapter in adapters.values()])
        storage.create_room("profiles", "Agent profile smoke room", "2026-05-20T00:00:00+00:00", list(adapters))

        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            premium = patch_json(base, "/v1/agents/premium/profile", {
                "cost_tier": "premium",
                "preferred_roles": ["owner", "guardrail"],
                "capabilities": ["architecture", "review"],
                "speed": 6,
                "trust": 9,
                "actor": "smoke",
            })["profile"]
            cheap = patch_json(base, "/v1/agents/cheap/profile", {
                "cost_tier": "cheap",
                "preferred_roles": ["summary", "token_police"],
                "capabilities": ["summary", "tokens", "ops"],
                "speed": 9,
                "trust": 7,
                "actor": "smoke",
            })["profile"]
            local = patch_json(base, "/v1/agents/local/profile", {
                "cost_tier": "local",
                "preferred_roles": ["token_police", "ops"],
                "capabilities": ["cost", "summary"],
                "speed": 8,
                "trust": 6,
                "actor": "smoke",
            })["profile"]
            profiles = get_json(base, "/v1/profiles")["profiles"]
            fetched = get_json(base, "/v1/agents/premium/profile")["profile"]
            data = {
                "health": {"ok": True},
                "agents": {"agents": fabric.list_agents()},
                "rooms": {"rooms": []},
                "tasks": {"tasks": []},
            }
            title, lines = _local_command_lines("/profiles", base, data, {"view": "dashboard"})
            assert title == "profiles"
            assert any("premium" in line and "cost=premium" in line for line in lines)
            title, lines = _local_command_lines("/agent profile premium", base, data, {"view": "dashboard"})
            assert title == "agent profile"
            assert any("architecture" in line for line in lines)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        assert premium["cost_tier"] == "premium"
        assert premium["preferred_roles"] == ["owner", "guardrail"]
        assert "architecture" in premium["capabilities"]
        assert cheap["cost_tier"] == "cheap"
        assert local["cost_tier"] == "local"
        assert any(profile["adapter_id"] == "premium" for profile in profiles)
        assert fetched["trust"] == 9

        owner, reviewers, owner_votes, reviewer_votes = fabric._choose_team_owner(
            ["cheap", "premium", "local"],
            [{"ok": True, "body": "No clear nomination."}],
            "Architecture plan for a durable control plane",
        )
        assert owner == "premium", (owner, owner_votes)
        assert reviewers[0] in {"cheap", "local"}, (reviewers, reviewer_votes)

        token_police, guardrail = fabric._choose_control_roles(
            ["cheap", "premium", "local"],
            owner,
            reviewers,
            "Architecture plan with token budget checks",
        )
        assert token_police in {"cheap", "local"}, token_police
        assert guardrail == "premium" or guardrail in reviewers, guardrail

        balanced_agents = fabric._goal_mode_agents(
            ["cheap", "premium", "local"],
            "balanced",
            "Architecture plan for a durable control plane",
        )
        assert "premium" in balanced_agents, balanced_agents
        cheap_agents = fabric._goal_mode_agents(
            ["cheap", "premium", "local"],
            "cheap",
            "Basic review and summary",
        )
        assert cheap_agents == ["local", "cheap"], cheap_agents

        print("agent profile smoke test: ok")


if __name__ == "__main__":
    main()
