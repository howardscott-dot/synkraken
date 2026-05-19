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


class GovernanceAdapter:
    def __init__(self, adapter_id: str, *, fail_all: bool = False, timeout_phases: set[str] | None = None) -> None:
        self.adapter_id = adapter_id
        self.fail_all = fail_all
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
        phase = str(message.metadata.get("phase") or "")
        if phase in self.timeout_phases:
            raise TimeoutError(f"{phase} timed out")
        if self.fail_all:
            return AdapterReply(adapter_id=self.adapter_id, ok=False, body="", error=f"{phase} failed")
        replies = {
            "clarify": f"{self.adapter_id} clarifies governance work. Suited: yes.",
            "nominate": "Owner: goose\nReviewer: hermes\nSupport: none",
            "execute": "Owner output: governance tables and approval commands are implemented.",
            "review": "Review: approval gate is visible. Risk: keep it explicit.",
            "final": "Recommended solution: require approval when requested.\nWho did what: goose owned, hermes reviewed.\nReviewer feedback: explicit gate.\nNext action: approve or reject.\nConfidence/risks: high.",
        }
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=replies.get(phase, phase), raw={"phase": phase})


def build_fabric(path: Path, *, fail_all: bool = False, execute_timeout: bool = False) -> AgentFabric:
    storage = Storage(path)
    fabric = AgentFabric({"adapters": {}, "routing": {"retry_limit": 0}}, storage)
    adapters = {
        "goose": GovernanceAdapter("goose", fail_all=fail_all, timeout_phases={"execute"} if execute_timeout else None),
        "hermes": GovernanceAdapter("hermes", fail_all=fail_all, timeout_phases={"execute"} if execute_timeout else None),
    }
    fabric.adapters = adapters
    storage.sync_agents([adapter.health() for adapter in adapters.values()])
    storage.create_room("gov", "Governance smoke room", "2026-05-19T00:00:00+00:00", list(adapters))
    return fabric


def post_json(base: str, path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.load(resp)


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=10) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric = build_fabric(Path(tmp) / "team-governance.sqlite3")
        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            approve_run = post_json(base, "/v1/team-tasks", {
                "source": "smoke",
                "room_name": "gov",
                "question": "Implement approval governance",
                "approval_mode": "REVIEW_REQUIRED",
            })
            assert approve_run["status"] == "awaiting_approval"
            team_run_id = approve_run["team_run_id"]
            run = get_json(base, f"/v1/team-runs/{team_run_id}")
            assert run["approval_required"] is True
            assert run["status"] == "awaiting_approval"
            assert run["owner_agent"] == "goose"
            task = fabric.storage.get_task(run["task_id"])
            assert task is not None and task["status"] == "in_progress"
            approved = post_json(base, f"/v1/team-runs/{team_run_id}/approve", {"actor": "howard"})
            assert approved["team_run"]["status"] == "approved"
            assert approved["team_run"]["approved_by"] == "howard"
            task = fabric.storage.get_task(run["task_id"])
            assert task is not None and task["status"] == "done"
            events = get_json(base, f"/v1/team-runs/{team_run_id}/events")["events"]
            event_types = {event["event_type"] for event in events}
            assert {"team_started", "clarify_complete", "owner_nominated", "owner_selected", "execution_started", "execution_completed", "review_started", "review_completed", "final_report", "approved"} <= event_types

            reject_run = post_json(base, "/v1/team-tasks", {
                "source": "smoke",
                "room_name": "gov",
                "question": "Reject this governance run",
                "approval_mode": "REVIEW_REQUIRED",
            })
            rejected = post_json(base, f"/v1/team-runs/{reject_run['team_run_id']}/reject", {"actor": "howard"})
            assert rejected["team_run"]["status"] == "rejected"
            reject_task = fabric.storage.get_task(rejected["team_run"]["task_id"])
            assert reject_task is not None and reject_task["status"] == "blocked"
            reject_events = {event["event_type"] for event in rejected["events"]}
            assert "rejected" in reject_events

            runs = get_json(base, "/v1/team-runs?room=gov")["team_runs"]
            assert len(runs) >= 2
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        failing = build_fabric(Path(tmp) / "team-governance-fail.sqlite3", fail_all=True)
        failed = failing.team_task({
            "source": "smoke",
            "room_name": "gov",
            "question": "This should fail",
            "approval_mode": "REVIEW_REQUIRED",
        })
        assert failed["status"] == "blocked"
        failed_run = failing.storage.get_team_run(failed["team_run_id"])
        assert failed_run is not None and failed_run["status"] == "blocked"
        failed_events = {event["event_type"] for event in failing.storage.list_team_events(failed["team_run_id"]) or []}
        assert {"failed_phase", "run_blocked"} <= failed_events

        timeout_fabric = build_fabric(Path(tmp) / "team-governance-timeout.sqlite3", execute_timeout=True)
        timed_out = timeout_fabric.team_task({
            "source": "smoke",
            "room_name": "gov",
            "question": "Timeout during execution should preserve governance state",
            "approval_mode": "REVIEW_REQUIRED",
        })
        assert timed_out["status"] == "blocked"
        assert timed_out["failure_summary"]["phase"] == "execute"
        timeout_run = timeout_fabric.storage.get_team_run(timed_out["team_run_id"])
        assert timeout_run is not None and timeout_run["status"] == "blocked"
        timeout_task = timeout_fabric.storage.get_task(timed_out["task_id"])
        assert timeout_task is not None and timeout_task["status"] == "blocked"
        timeout_events = {event["event_type"] for event in timeout_fabric.storage.list_team_events(timed_out["team_run_id"]) or []}
        assert {"timeout", "failed_phase", "run_blocked"} <= timeout_events
        timeout_bodies = "\n".join(message["body"] for message in timeout_fabric.storage.get_room_messages("gov", limit=200))
        assert "Team task: Timeout during execution" in timeout_bodies
        assert "Team owner selected: goose" in timeout_bodies
        assert "Team run blocked." in timeout_bodies

    print("team governance smoke test: ok")


if __name__ == "__main__":
    main()
