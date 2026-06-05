from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from synkraken.storage import Storage


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    storage_source = _read("synkraken/storage.py")
    api_source = _read("synkraken/api.py")
    _require("assignment_id TEXT" in storage_source, "handoff assignment_id column missing")
    _require("def create_assignment_handoff" in storage_source, "assignment handoff writer missing")
    _require("/v1/assignments/([^/]+)/handoff" in api_source, "assignment handoff API missing")
    _require("/v1/handoffs/recent" in api_source, "recent handoffs API missing")

    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "handoff.db")
        now = datetime.now(timezone.utc).isoformat()
        storage.sync_agents([
            {"adapter_id": "sherlock", "runtime_name": "Sherlock", "type": "claude", "enabled": True},
            {"adapter_id": "quill", "runtime_name": "Quill", "type": "claude", "enabled": True},
            {"adapter_id": "scout", "runtime_name": "Scout", "type": "claude", "enabled": True},
        ])
        storage.create_assignment(
            assignment_id="assign-copy",
            title="Write customer-facing copy",
            owner_worker="sherlock",
            contributor_workers=["quill"],
            created_at=now,
        )
        first = storage.create_assignment_handoff(
            "assign-copy",
            to_worker="quill",
            reason="Research complete.",
            context_summary="Tier logic and evidence are ready for copy.",
            actor="operator",
        )
        _require(first["handoff"]["assignment_id"] == "assign-copy", "handoff assignment link missing")
        _require(first["handoff"]["from_worker"] == "sherlock", "handoff from worker incorrect")
        _require(first["assignment"]["owner_worker"] == "quill", "handoff did not transfer owner")
        _require(first["assignment"]["status"] == "handoff", "handoff status not recorded")
        _require("quill" not in first["assignment"]["contributor_workers"], "handoff owner remained a contributor")
        second = storage.create_assignment_handoff(
            "assign-copy",
            to_worker="scout",
            reason="Copy draft ready.",
            context_summary="QA review requested.",
            actor="operator",
        )
        _require(second["handoff"]["from_worker"] == "quill", "second handoff from worker incorrect")
        _require(storage.get_assignment("assign-copy")["owner_worker"] == "scout", "second handoff did not transfer owner")
        handoffs = storage.assignment_handoffs("assign-copy")
        _require(len(handoffs) == 2, "assignment handoff timeline count failed")
        _require(handoffs[0]["context_summary"] == "QA review requested.", "handoff context summary missing")
        _require(storage.recent_assignment_handoffs()[0]["assignment_id"] == "assign-copy", "recent handoffs missing assignment")
        events = storage.assignment_events("assign-copy")
        event_types = {event["event_type"] for event in events}
        _require({"created", "handoff"} <= event_types, "assignment handoff audit events missing")

    print("workforce handoff smoke test passed")


if __name__ == "__main__":
    main()
