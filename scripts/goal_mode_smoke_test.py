#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
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
from synkraken.models import new_id, utc_now_iso
from synkraken.models import AdapterReply
from synkraken.storage import Storage
from synkraken.tui import _parse_goal_args


class GoalAdapter:
    def __init__(self, adapter_id: str, score: int = 90) -> None:
        self.adapter_id = adapter_id
        self.score = score
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
        if "criteria" in phase:
            body = (
                "Done means the requested generic workflow is documented.\n"
                "Must be true: output is bounded and inspectable.\n"
                "Should not happen: hidden work or unbounded retries.\n"
                "Risks: vague success criteria."
            )
        elif "assignment" in phase:
            body = "Owner: alpha\nReviewer: beta\nSupport: gamma"
        elif "execute" in phase:
            body = "Owner output: a concise bounded implementation note with checklist coverage."
        elif "token" in phase:
            body = "Token review: context is compact. No warning. Another round is only useful if score is below threshold."
        elif "guardrail" in phase:
            body = "CLEAR: scope is generic, safe, bounded, and not overengineered."
        elif "review" in phase:
            decision = "pass" if self.score >= 80 else "fail"
            body = (
                f"Score: {self.score}\n"
                f"Pass/fail: {decision}\n"
                "Missing items: none for high score, revision detail for low score.\n"
                "Risks: keep changes bounded.\n"
                "Suggested revision: tighten the checklist."
            )
        else:
            body = f"{self.adapter_id} handled {phase}"
        return AdapterReply(adapter_id=self.adapter_id, ok=True, body=body, raw={"phase": phase})


def build_fabric(path: Path, *, review_score: int = 90) -> tuple[AgentFabric, dict[str, GoalAdapter]]:
    storage = Storage(path)
    fabric = AgentFabric({
        "adapters": {},
        "routing": {"retry_limit": 0},
        "goal": {
            "max_rounds": 3,
            "threshold": 80,
            "max_reviewers": 3,
            "max_context_chars": 1800,
            "max_revision_chars": 700,
            "max_agents": 4,
        },
    }, storage)
    adapters = {name: GoalAdapter(name, review_score) for name in ["alpha", "beta", "gamma", "delta"]}
    fabric.adapters = adapters
    storage.sync_agents([adapter.health() for adapter in adapters.values()])
    storage.create_room("goal-room", "Goal smoke room", "2026-05-19T00:00:00+00:00", list(adapters))
    return fabric, adapters


def post_json(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.status, json.load(resp)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw)


def get_json(base: str, path: str) -> dict:
    with urlopen(base + path, timeout=20) as resp:
        return json.load(resp)


def event_types(fabric: AgentFabric, goal_run_id: str) -> set[str]:
    return {event["event_type"] for event in fabric.storage.list_goal_events(goal_run_id) or []}


def assert_core_run(fabric: AgentFabric, result: dict, *, expected_status: str) -> None:
    run = result["goal_run"]
    assert run["status"] == expected_status
    assert run["success_criteria"]
    assert run["owner_agent"] == "alpha"
    assert run["token_police_agent"] != run["owner_agent"]
    assert run["guardrail_agent"] != run["owner_agent"]
    assert run["estimated_context_chars"] <= run["token_budget_chars"]
    assert run["linked_task_id"]
    task = fabric.storage.get_task(run["linked_task_id"])
    assert task is not None
    assert task["assigned_agent_id"] == "alpha"
    types = event_types(fabric, run["goal_run_id"])
    assert {
        "goal_started",
        "criteria_defined",
        "owner_selected",
        "control_roles_selected",
        "round_started",
        "owner_work_completed",
        "token_budget_checked",
        "guardrail_checked",
        "review_started",
        "review_completed",
        "score_recorded",
    } <= types
    transcript = "\n".join(message["body"] for message in fabric.storage.get_room_messages("goal-room", limit=300))
    assert "Goal success criteria:" in transcript
    assert "Goal context budget:" in transcript
    assert "Goal review score:" in transcript


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        fabric, _adapters = build_fabric(Path(tmp) / "goal.sqlite3", review_score=90)
        try:
            fabric.goal_run({"source": "smoke", "goal": "No room should fail"})
            raise AssertionError("goal without room should fail")
        except ValueError as exc:
            assert str(exc) == "Goal mode needs a room. Create or select a room first."
        try:
            _parse_goal_args('"No room"', None)
            raise AssertionError("TUI goal parser without room should fail")
        except ValueError as exc:
            assert str(exc) == "Goal mode needs a room. Create or select a room first."

        achieved = fabric.goal_run({
            "source": "smoke",
            "room_name": "goal-room",
            "goal": "Produce a bounded generic implementation checklist",
            "threshold": 80,
            "max_rounds": 3,
        })
        assert_core_run(fabric, achieved, expected_status="achieved")
        achieved_run = achieved["goal_run"]
        assert achieved_run["latest_score"] >= 80
        assert "threshold_met" in event_types(fabric, achieved_run["goal_run_id"])
        achieved_task = fabric.storage.get_task(achieved_run["linked_task_id"])
        assert achieved_task is not None and achieved_task["status"] == "done"

        low_fabric, _low_adapters = build_fabric(Path(tmp) / "goal-low.sqlite3", review_score=50)
        partial = low_fabric.goal_run({
            "source": "smoke",
            "room_name": "goal-room",
            "goal": "Exercise bounded revision rounds",
            "threshold": 80,
            "max_rounds": 2,
        })
        assert_core_run(low_fabric, partial, expected_status="partially_achieved")
        partial_run = partial["goal_run"]
        partial_events = event_types(low_fabric, partial_run["goal_run_id"])
        assert "revision_requested" in partial_events
        assert "max_rounds_reached" in partial_events
        assert partial_run["current_round"] == 2
        partial_task = low_fabric.storage.get_task(partial_run["linked_task_id"])
        assert partial_task is not None and partial_task["status"] == "done"

        now = utc_now_iso()
        task = fabric.storage.create_task(
            new_id(),
            "Cancellable generic goal",
            "",
            "open",
            "normal",
            "goal-room",
            None,
            None,
            "smoke",
            now,
        )
        cancellable = fabric.storage.create_goal_run(
            goal_run_id=new_id(),
            room_name="goal-room",
            source_goal="Cancellable generic goal",
            status="planning",
            threshold=80,
            max_rounds=3,
            current_round=0,
            participants=["alpha", "beta"],
            token_budget_chars=1800,
            started_at=now,
            created_by="smoke",
            linked_task_id=task["task_id"],
        )
        cancelled = fabric.cancel_goal_run(cancellable["goal_run_id"], actor="smoke")
        assert cancelled["goal_run"]["status"] == "cancelled"
        assert "goal_cancelled" in event_types(fabric, cancellable["goal_run_id"])
        cancelled_task = fabric.storage.get_task(task["task_id"])
        assert cancelled_task is not None and cancelled_task["status"] == "blocked"

        FabricRequestHandler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), FabricRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            status, no_room = post_json(base, "/v1/goal-runs", {"source": "smoke", "goal": "No room"})
            assert status == 400
            assert no_room["error"] == "Goal mode needs a room. Create or select a room first."
            listed = get_json(base, "/v1/goal-runs?room=goal-room")
            assert any(item["goal_run_id"] == achieved_run["goal_run_id"] for item in listed["goal_runs"])
            fetched = get_json(base, f"/v1/goal-runs/{achieved_run['goal_run_id']}")
            assert fetched["goal_run_id"] == achieved_run["goal_run_id"]
            assert fetched["events"]
            events = get_json(base, f"/v1/goal-runs/{achieved_run['goal_run_id']}/events")
            assert events["events"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    audit = subprocess.run([sys.executable, "scripts/context_audit.py"], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
    assert audit.returncode == 0, audit.stdout + audit.stderr
    print("goal mode smoke test: ok")


if __name__ == "__main__":
    main()
