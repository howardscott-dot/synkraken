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
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=f"{self.adapter_id} ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "runtime-workspace-flight.sqlite3")
        config = {
            "routing": {"retry_limit": 0, "default_timeout_seconds": 12},
            "adapters": {
                "codex": {
                    "type": "goose",
                    "runtime_type": "codex",
                    "command": ["codex"],
                    "working_dir": "/workspace",
                    "timeout_seconds": 12,
                    "cost_profile": "premium",
                    "supported_modes": ["direct", "team", "goal"],
                    "capabilities": ["architecture", "code"],
                },
                "goose": {
                    "type": "goose",
                    "command": ["goose"],
                    "timeout_seconds": 8,
                    "cost_profile": "cheap",
                    "supported_modes": ["direct", "room", "memory"],
                    "capabilities": ["summary"],
                },
            },
        }
        fabric = AgentFabric(config, storage)
        fabric.adapters = {"codex": FakeAdapter("codex"), "goose": FakeAdapter("goose")}
        storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
        fabric._sync_runtime_registry()

        runtimes = {item["runtime_id"]: item for item in fabric.list_runtimes()}
        assert runtimes["codex"]["runtime_type"] == "codex"
        assert runtimes["codex"]["command"] == ["codex"]
        assert runtimes["codex"]["working_dir"] == "/workspace"
        assert runtimes["codex"]["timeout"] == 12
        assert runtimes["codex"]["cost_profile"] == "premium"
        assert "goal" in runtimes["codex"]["supported_modes"]
        doctor = fabric.runtime_doctor()
        assert any(item["runtime_id"] == "codex" and item["registered"] for item in doctor["runtimes"])

        storage.create_room("ops", "Ops", "2026-05-20T00:00:00+00:00", ["codex", "goose"])
        workspace = fabric.init_workspace("ops-pack")["workspace"]
        assert workspace["name"] == "ops-pack"
        assert workspace["rooms"]
        assert workspace["agents"]
        assert "codex" in workspace["runtime_refs"]
        loaded = fabric.load_workspace("ops-pack")["workspace"]
        exported = fabric.export_workspace("ops-pack")["workspace"]
        assert loaded["workspace_id"] == workspace["workspace_id"]
        assert exported["runtime_refs"] == workspace["runtime_refs"]
        assert storage.list_workspace_packs()

        flight = fabric.flight_summary()
        assert flight["agents_total"] == 2
        assert flight["agents_online"] >= 1
        assert flight["active_goals"] == 0
        assert flight["token_risk"] == "low"
        assert flight["memory_count"] == 0
        assert flight["pending_reviews"] == 0
        assert flight["cost_complexity"] in {"low", "medium", "high"}

    print("runtime/workspace/flight smoke test: ok")


if __name__ == "__main__":
    main()
