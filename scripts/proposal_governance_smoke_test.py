#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import FabricMessage
from synkraken.storage import Storage


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "synkraken.sqlite3")
        fabric = AgentFabric({"adapters": {}}, storage)
        now = "2026-05-28T19:20:00+00:00"
        storage.create_room("ops", "Operations", now)
        message = FabricMessage(
            message_id="msg-1",
            conversation_id="conv-1",
            source="claude",
            target="room:ops",
            body="I propose restarting the daemon.",
            timestamp=now,
        ).normalized()
        storage.save_message(message)
        task = storage.create_task(
            task_id="task-1",
            title="Restart daemon safely",
            description="",
            status="open",
            priority="normal",
            room_name="ops",
            assigned_agent_id=None,
            source_message_id=message.message_id,
            actor="operator",
            created_at=now,
        )
        goal = storage.create_goal_run(
            goal_run_id="goal-1",
            room_name="ops",
            source_goal="Restore daemon health",
            status="running",
            threshold=80,
            max_rounds=1,
            current_round=0,
            participants=[],
            token_budget_chars=4000,
            linked_task_id=task["task_id"],
            started_at=now,
            created_by="operator",
        )

        shell = fabric.create_proposal({
            "proposal_id": "prop-shell",
            "proposal_type": "shell",
            "title": "Restart daemon",
            "summary": "Restart synkraken service",
            "proposed_by": "claude",
            "room_id": "ops",
            "task_id": task["task_id"],
            "goal_id": goal["goal_run_id"],
            "linked_message_ids": [message.message_id],
            "execution_payload": {"command": ["synkraken", "restart"]},
        })["proposal"]
        assert shell["status"] == "proposed"
        assert shell["risk_level"] == "high"
        assert shell["requires_approval"] is True
        assert shell["approval_reason"] == "shell execution requires human approval"
        assert shell["room_id"] == "ops"
        assert shell["task_id"] == "task-1"
        assert shell["goal_id"] == "goal-1"

        pending = storage.list_proposals(status="proposed")
        assert any(item["proposal_id"] == "prop-shell" for item in pending)

        approved = fabric.approve_proposal("prop-shell", "operator")["proposal"]
        assert approved["status"] == "approved"

        executed = fabric.execute_proposal("prop-shell", "synkraken")
        assert executed["proposal"]["status"] == "executed"
        assert executed["execution_result"]["result"] == "simulated execution"
        events = storage.list_proposal_events("prop-shell")
        assert events is not None
        assert any(event["event_type"] == "executed" for event in events)

        reject_me = fabric.create_proposal({
            "proposal_id": "prop-delete",
            "proposal_type": "delete",
            "title": "Delete temp file",
            "summary": "Remove a generated file",
            "proposed_by": "goose",
        })["proposal"]
        assert reject_me["risk_level"] == "high"
        rejected = fabric.reject_proposal("prop-delete", "operator", "not needed")["proposal"]
        assert rejected["status"] == "rejected"
        try:
            fabric.execute_proposal("prop-delete", "synkraken")
        except ValueError as exc:
            assert "cannot be executed" in str(exc)
        else:
            raise AssertionError("rejected proposal executed")

        low = fabric.create_proposal({
            "proposal_id": "prop-summary",
            "proposal_type": "room_summarize",
            "title": "Summarize room",
            "summary": "Summarize recent ops transcript",
            "proposed_by": "operator",
            "room_id": "ops",
        })["proposal"]
        assert low["risk_level"] == "low"
        assert low["requires_approval"] is False

        replay = fabric.get_replay("prop-shell")
        assert replay["kind"] == "proposal"
        assert replay["summary"]["proposal_count"] == 1
        assert any(item["source"] == "proposals" and item["event_type"] == "proposal_executed" for item in replay["timeline"])

        trace = fabric.get_trace("prop-shell")
        assert trace["proposals"][0]["proposal_id"] == "prop-shell"
        assert trace["task"]["task_id"] == "task-1"
        assert trace["goal"]["goal_run_id"] == "goal-1"

        reputation = storage.get_runtime_reputation("claude")
        assert reputation is not None
        assert reputation["proposals_created"] >= 1
        assert reputation["proposals_executed"] >= 1

    print("proposal governance smoke test: ok")


if __name__ == "__main__":
    main()
