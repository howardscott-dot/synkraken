#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply
from synkraken.storage import Storage
from synkraken.tui import _parse_team_args


class TeamAdapter:
    def __init__(
        self,
        adapter_id: str,
        fail_phases: set[str] | None = None,
        timeout_phases: set[str] | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.fail_phases = fail_phases or set()
        self.timeout_phases = timeout_phases or set()
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
        body = message.body
        phase = str(message.metadata.get("phase") or "")
        if phase in self.timeout_phases:
            raise TimeoutError(f"{phase} timed out")
        if phase in self.fail_phases:
            return AdapterReply(adapter_id=self.adapter_id, ok=False, body="", error=f"{phase} failed")
        if phase == "clarify":
            reply = f"{self.adapter_id} clarifies the task. Skills needed: coding, review. Suited: yes."
        elif phase == "nominate":
            reply = "Owner: goose\nReviewer: hermes\nSupport: none"
        elif phase == "execute":
            reply = "Owner output: implement the bounded team task flow and persist it in the room."
        elif phase == "review":
            reply = "Review: output is sound. Risk: keep the orchestration bounded and visible."
        elif phase == "final":
            reply = (
                "Recommended solution: use Team Task Mode.\n"
                "Who did what: goose owned, hermes reviewed.\n"
                "Reviewer feedback: bounded and visible.\n"
                "Next action: ship smoke coverage.\n"
                "Confidence/risks: high confidence, watch adapter failures."
            )
        else:
            reply = f"{self.adapter_id} saw {phase}"
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=reply, raw={"phase": phase, "body": body})


def build_fabric(path: Path, *, review_timeout: bool = False) -> tuple[AgentFabric, dict[str, TeamAdapter]]:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}}, storage)
    adapters = {
        "goose": TeamAdapter("goose"),
        "hermes": TeamAdapter("hermes", timeout_phases={"review"} if review_timeout else None),
        "claude": TeamAdapter("claude", {"clarify"}),
    }
    fabric.adapters = adapters
    storage.sync_agents([adapter.health() for adapter in adapters.values()])
    storage.create_room("teamroom", "Team smoke room", "2026-05-19T00:00:00+00:00", list(adapters))
    return fabric, adapters


def post_json(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status, json.load(resp)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw)


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=10) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric, adapters = build_fabric(Path(tmp) / "team-task.sqlite3")

        try:
            fabric.team_task({"source": "smoke", "question": "No room should fail"})
            raise AssertionError("team_task without room should fail")
        except ValueError as exc:
            assert str(exc) == "Team mode needs a room. Create or select a room first."
        try:
            _parse_team_args('"No room"', None)
            raise AssertionError("TUI parser without room should fail")
        except ValueError as exc:
            assert str(exc) == "Team mode needs a room. Create or select a room first."

        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            status, no_room = post_json(base, "/v1/team-tasks", {"source": "smoke", "question": "No room"})
            assert status == 400
            assert no_room["error"] == "Team mode needs a room. Create or select a room first."
            status, result = post_json(base, "/v1/team-tasks", {
                "source": "smoke",
                "room_name": "teamroom",
                "question": "Build a deterministic team task smoke test",
                "turns": 4,
            })
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        assert status == 200
        assert result["status"] == "completed"
        assert result["owner"] == "goose"
        assert result["reviewers"] == ["hermes"]
        assert "Recommended solution" in result["final_report"]
        assert any(message.metadata.get("phase") == "clarify" for message in adapters["goose"].messages)
        assert any(message.metadata.get("phase") == "nominate" for message in adapters["hermes"].messages)
        assert any(message.metadata.get("phase") == "execute" for message in adapters["goose"].messages)
        assert any(message.metadata.get("phase") == "review" for message in adapters["hermes"].messages)
        assert any(message.metadata.get("phase") == "final" for message in adapters["goose"].messages)
        assert adapters["claude"].messages and adapters["claude"].messages[0].metadata.get("phase") == "clarify"
        assert any(letter["delivery_target"] == "claude" for letter in result["dead_letters"])

        task = fabric.storage.get_task(result["task_id"])
        assert task is not None
        assert task["room_name"] == "teamroom"
        assert task["assigned_agent_id"] == "goose"
        assert task["status"] == "done"
        events = fabric.storage.list_task_events(result["task_id"])
        event_types = {event["event_type"] for event in events or []}
        assert {"created", "nominated", "assigned", "reviewed", "completed", "team_completed"} <= event_types
        transcript = fabric.storage.get_room_messages("teamroom", limit=200)
        bodies = "\n".join(message["body"] for message in transcript)
        assert "Team task: Build a deterministic team task smoke test" in bodies
        assert "Team owner selected: goose" in bodies
        assert "Owner output: implement the bounded team task flow" in bodies
        assert "Review: output is sound" in bodies
        assert "Recommended solution: use Team Task Mode" in bodies

        timeout_fabric, _timeout_adapters = build_fabric(Path(tmp) / "team-task-timeout.sqlite3", review_timeout=True)
        FabricRequestHandler.fabric = timeout_fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            status, timed_out = post_json(base, "/v1/team-tasks", {
                "source": "smoke",
                "room_name": "teamroom",
                "question": "Preserve partial transcript when review times out",
                "turns": 4,
            })
            inspected = get_json(base, f"/v1/team-runs/{timed_out['team_run_id']}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        assert status == 200
        assert timed_out["status"] == "blocked"
        assert timed_out["failure_summary"]["phase"] == "review"
        assert timed_out["failure_summary"]["agent"] == "hermes"
        assert timed_out["failure_summary"]["elapsed_ms"] is not None
        timeout_task = timeout_fabric.storage.get_task(timed_out["task_id"])
        assert timeout_task is not None and timeout_task["status"] == "blocked"
        timeout_run = timeout_fabric.storage.get_team_run(timed_out["team_run_id"])
        assert timeout_run is not None and timeout_run["status"] == "blocked"
        timeout_event_types = {event["event_type"] for event in timeout_fabric.storage.list_team_events(timed_out["team_run_id"]) or []}
        assert {"timeout", "failed_phase", "run_blocked"} <= timeout_event_types
        timeout_bodies = "\n".join(message["body"] for message in timeout_fabric.storage.get_room_messages("teamroom", limit=200))
        assert "Team task: Preserve partial transcript" in timeout_bodies
        assert "Team owner selected: goose" in timeout_bodies
        assert "Owner output: implement the bounded team task flow" in timeout_bodies
        assert "Team run blocked." in timeout_bodies
        assert inspected["status"] == "blocked"
        assert inspected["failure_summary"]["phase"] == "review"
        inspected_bodies = "\n".join(message["body"] for message in inspected["failure_summary"]["partial_transcript"])
        assert "Team owner selected: goose" in inspected_bodies

    print("team task smoke test: ok")


if __name__ == "__main__":
    main()
