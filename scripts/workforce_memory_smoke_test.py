#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.storage import Storage


class MemoryAdapter:
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
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body="WORKFORCE_MEMORY_OK", raw={})


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "workforce-memory.sqlite3")
        fabric = AgentFabric({
            "adapters": {},
            "routing": {"retry_limit": 0},
            "memory": {"max_items_injected": 8, "max_chars_injected": 1600},
            "workspace": "memory-smoke",
        }, storage)
        adapter = MemoryAdapter("goose")
        fabric.adapters = {"goose": adapter}
        storage.sync_agents([adapter.health()])
        storage.create_room("ops", "Operations", "2026-06-02T00:00:00+00:00", ["goose"])

        global_note = fabric.create_operator_memory_note({
            "title": "Studio Blueprint positioning",
            "body": "Studio Blueprint helps consultancies turn methodology into a repeatable operating system.",
            "scope_type": "global",
            "importance": "high",
        })["memory"]
        assert global_note["status"] == "approved"
        assert global_note["memory_type"] == "operator_note"
        assert global_note["scope_type"] == "global"

        room_note = fabric.create_operator_memory_note({
            "title": "Ops room focus",
            "body": "The ops room should prefer explicit summaries when coordinating weaker runtimes.",
            "scope_type": "room",
            "scope_id": "ops",
            "importance": "medium",
        })["memory"]
        assert room_note["status"] == "approved"
        assert room_note["scope_type"] == "room"
        assert room_note["scope_id"] == "ops"

        proposed = fabric.propose_memory({
            "title": "Goose runtime observation",
            "body": "Goose often loses prior room context; prefer explicit summaries.",
            "memory_type": "runtime_observation",
            "scope_type": "runtime",
            "scope_id": "goose",
            "source_type": "operator",
            "importance": "high",
        })["memory"]
        assert proposed["status"] == "proposed"

        approved = fabric.approve_memory(proposed["memory_id"])["memory"]
        assert approved["status"] == "approved"

        rejected = fabric.propose_memory({
            "title": "Rejected memory",
            "body": "Rejected memory must not appear in active context.",
            "memory_type": "operator_note",
            "scope_type": "global",
        })["memory"]
        fabric.reject_memory(rejected["memory_id"])

        archived = fabric.create_operator_memory_note({
            "title": "Archived memory",
            "body": "Archived memory must not appear in active context.",
            "scope_type": "global",
        })["memory"]
        fabric.archive_memory(archived["memory_id"])

        pending = {"memories": storage.list_shared_memory(status="proposed", limit=100)}
        assert not any(item["memory_id"] == approved["memory_id"] for item in pending["memories"])

        context = fabric.memory_context({"scope_type": "room", "scope_id": "ops"})
        context_ids = {item["memory_id"] for item in context["memories"]}
        assert global_note["memory_id"] in context_ids
        assert room_note["memory_id"] in context_ids
        assert rejected["memory_id"] not in context_ids
        assert archived["memory_id"] not in context_ids

        dispatched = fabric.dispatch({
            "source": "operator",
            "target": "room:ops",
            "body": "Check memory injection.",
        })
        assert global_note["memory_id"] in dispatched["routing"]["memory_context"]
        assert room_note["memory_id"] in dispatched["routing"]["memory_context"]
        assert rejected["memory_id"] not in dispatched["routing"]["memory_context"]
        assert "injected_memory_ids" in dispatched["deliveries"][0]
        assert "[SynKraken approved memory]" in adapter.messages[-1].body

    print("workforce memory smoke test passed")


if __name__ == "__main__":
    main()
