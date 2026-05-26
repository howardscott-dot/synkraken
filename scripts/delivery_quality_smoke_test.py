#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken import cli_main
from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.storage import Storage


class FakeAdapter:
    def __init__(self, adapter_id: str, body: str | None, *, ok: bool = True) -> None:
        self.adapter_id = adapter_id
        self.body = body
        self.ok = ok

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id,
            "type": "fake",
            "enabled": True,
        }

    def send(self, _message) -> AdapterReply:
        return AdapterReply(self.adapter_id, self.ok, self.body)


def _fabric(path: Path) -> AgentFabric:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}}, storage)
    fabric.adapters = {
        "none": FakeAdapter("none", None),
        "empty": FakeAdapter("empty", ""),
        "space": FakeAdapter("space", "   \n\t"),
        "normal": FakeAdapter("normal", "normal reply"),
        "wrapped": FakeAdapter("wrapped", "<tool_code>\nprint('hello')\n</tool_code>"),
    }
    storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
    return fabric


def _delivery(fabric: AgentFabric, target: str) -> dict:
    result = fabric.dispatch({"source": "quality-smoke", "target": target, "body": "reply"})
    return result["deliveries"][0]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric = _fabric(Path(tmp) / "smoke.sqlite3")

        none = _delivery(fabric, "none")
        assert none["status"] == "empty_reply"
        assert none["ok"] is True

        empty = _delivery(fabric, "empty")
        assert empty["status"] == "empty_reply"

        space = _delivery(fabric, "space")
        assert space["status"] == "empty_reply"

        normal = _delivery(fabric, "normal")
        assert normal["status"] == "replied"
        assert normal.get("quality") is None

        wrapped = _delivery(fabric, "wrapped")
        assert wrapped["status"] == "replied"
        assert wrapped["quality"] == "suspicious_output"

        rows = fabric.storage.list_recent_deliveries(limit=10)["deliveries"]
        status_by_agent = {row["adapter_id"]: row["status"] for row in rows}
        assert status_by_agent["none"] == "empty_reply"
        assert status_by_agent["space"] == "empty_reply"
        assert status_by_agent["normal"] == "replied"

        calls = {"count": 0}
        original_get_json = cli_main.get_json

        def fake_get_json(_url: str) -> dict:
            calls["count"] += 1
            if calls["count"] < 3:
                raise ConnectionError("connection refused")
            return {"ok": True}

        try:
            cli_main.get_json = fake_get_json
            assert cli_main._wait_for_daemon_health("http://127.0.0.1:9460", 3)
            assert calls["count"] == 3
        finally:
            cli_main.get_json = original_get_json

    print("delivery quality smoke test: ok")


if __name__ == "__main__":
    main()
