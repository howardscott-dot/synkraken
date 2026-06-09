#!/usr/bin/env python3
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.api import FabricRequestHandler
from synkraken.storage import Storage


class FakeFabric:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.dispatched: list[dict] = []

    def list_agents(self) -> list[dict]:
        return [
            {"adapter_id": "hermes", "enabled": True, "status": "online", "capabilities": ["coding", "research"]},
            {"adapter_id": "goose", "enabled": True, "status": "online", "capabilities": ["research"]},
            {"adapter_id": "crush", "enabled": True, "status": "online", "capabilities": ["coding"]},
        ]

    def dispatch(self, payload: dict) -> dict:
        self.dispatched.append(payload)
        target = payload["target"]
        if str(target).startswith("room:"):
            members = self.storage.get_room_members(str(target).split(":", 1)[1])
            deliveries = [
                {"adapter_id": member, "ok": True, "body": f"{member} researched {payload['body'][:24]}", "error": None}
                for member in members
            ]
        else:
            deliveries = [{"adapter_id": target, "ok": True, "body": f"{target} answered", "error": None}]
        return {"message": {"target": target}, "deliveries": deliveries}

    def add_room_member(self, room: str, adapter_id: str, actor: str = "operator") -> None:
        self.storage.add_room_member(room, adapter_id, "2026-06-09T00:00:00+00:00")


class ApiServer:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "phase4.sqlite3")
        fake_fabric = FakeFabric(self.storage)
        self.storage.sync_agents(fake_fabric.list_agents())
        FabricRequestHandler.fabric = fake_fabric
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "ApiServer":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def run_cli(base_url: str, *args: str) -> dict:
    cmd = [sys.executable, "-m", "synkraken.cli_main", *args, "--url", base_url, "--json"]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def main() -> int:
    with ApiServer() as api:
        briefing = get_json(f"{api.base_url}/v1/briefing")
        assert briefing["workforce"]["agents_total"] == 3
        assert briefing["recommended_actions"]

        cookbook = get_json(f"{api.base_url}/v1/cookbook")
        assert any(recipe["name"] == "compare-workers" for recipe in cookbook["recipes"])

        arena = run_cli(api.base_url, "arena", "run", "Who should handle docs?", "--agents", "hermes", "goose")
        assert arena["status"] == "completed"
        assert arena["winner_agent"] == "hermes"
        assert len(arena["result"]["deliveries"]) == 2

        judged = run_cli(api.base_url, "arena", "judge", arena["arena_run_id"], "--winner", "goose", "--reason", "clearer answer")
        assert judged["status"] == "judged"
        assert judged["winner_agent"] == "goose"

        research = run_cli(api.base_url, "research", "run", "Find the best launch checklist", "--agents", "hermes", "goose")
        assert research["status"] == "completed"
        assert research["room_name"].startswith("research-")
        assert "hermes researched" in research["report"]

        runbook = run_cli(api.base_url, "runbook", "create", "Restart daemon", "--step", "Check health", "--step", "Restart service")
        assert runbook["title"] == "Restart daemon"
        assert runbook["steps"] == ["Check health", "Restart service"]

        artifact = run_cli(api.base_url, "artifact", "create", "Research note", "--body", "Keep this as a durable note.")
        assert artifact["artifact_type"] == "note"

        evidence = run_cli(api.base_url, "evidence", "create", "README source", "--uri", "https://example.invalid/readme", "--summary", "Reference")
        assert evidence["uri"].startswith("https://")

        approval = run_cli(api.base_url, "approval", "request", "Allow remote benchmark", "--reason", "Uses operator machine")
        assert approval["status"] == "pending"
        resolved = run_cli(api.base_url, "approval", "approve", approval["approval_id"])
        assert resolved["status"] == "approved"

    print("phase4 operator primitives smoke test: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
