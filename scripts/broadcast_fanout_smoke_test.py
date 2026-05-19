#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.storage import Storage


class SlowAdapter:
    def __init__(self, adapter_id: str, delay: float, *, ok: bool = True) -> None:
        self.adapter_id = adapter_id
        self.delay = delay
        self.ok = ok
        self.seen_targets: list[str] = []

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id,
            "type": "fake",
            "enabled": True,
        }

    def send(self, message) -> AdapterReply:
        self.seen_targets.append(message.target)
        time.sleep(self.delay)
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=self.ok,
            body=f"{self.adapter_id} reply" if self.ok else "",
            error=None if self.ok else "fake failure",
            duration_ms=int(self.delay * 1000),
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "broadcast.sqlite3")
        fabric = AgentFabric({
            "adapters": {},
            "routing": {"retry_limit": 0, "fanout_workers": 4},
        }, storage)
        adapters = {
            "alpha": SlowAdapter("alpha", 0.35),
            "bravo": SlowAdapter("bravo", 0.35),
            "charlie": SlowAdapter("charlie", 0.35, ok=False),
        }
        fabric.adapters = adapters
        storage.sync_agents([adapter.health() for adapter in adapters.values()])

        started = time.perf_counter()
        result = fabric.dispatch({
            "source": "smoke-test",
            "target": "broadcast",
            "body": "broadcast fanout smoke",
        })
        elapsed = time.perf_counter() - started

        assert elapsed < 0.8, f"fanout should run concurrently, took {elapsed:.3f}s"
        assert result["routing"]["requested_target"] == "broadcast"
        assert result["routing"]["resolved_targets"] == ["alpha", "bravo", "charlie"]
        assert {adapter.seen_targets[-1] for adapter in adapters.values()} == {"alpha", "bravo", "charlie"}
        assert {delivery["delivery_target"] for delivery in result["deliveries"]} == {"alpha", "bravo", "charlie"}
        assert {delivery["persisted_transcript_target"] for delivery in result["deliveries"] if delivery["ok"]} == {"broadcast"}
        assert result["dead_letters"][0]["adapter_id"] == "charlie"

        history = storage.get_conversation(result["message"]["conversation_id"])
        assert [(m["source"], m["target"], m["body"]) for m in history["messages"]] == [
            ("smoke-test", "broadcast", "broadcast fanout smoke"),
            ("alpha", "broadcast", "alpha reply"),
            ("bravo", "broadcast", "bravo reply"),
        ]

    print("broadcast fanout smoke test: ok")


if __name__ == "__main__":
    main()
