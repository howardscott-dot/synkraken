#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage
from synkraken.tui import _workforce_health_lines


def _save_message(storage: Storage, target: str = "alpha") -> str:
    message = FabricMessage(source="test", target=target, body="ping").normalized()
    storage.save_message(message)
    return message.message_id


def _delivery(storage: Storage, adapter_id: str, *, ok: bool = True, body: str = "ok",
              status: str = "replied", error: str | None = None, quality: str | None = None,
              duration_ms: int = 100) -> dict:
    message_id = _save_message(storage, adapter_id)
    reply = AdapterReply(
        adapter_id=adapter_id,
        ok=ok,
        body=body,
        error=error,
        duration_ms=duration_ms,
        raw={"quality": quality} if quality else {},
    )
    storage.save_delivery(message_id, reply, "2026-05-28T00:00:00+00:00", status=status, quality=quality)
    reputation = storage.get_runtime_reputation(adapter_id)
    assert reputation is not None
    return reputation


def _fabric(storage: Storage) -> AgentFabric:
    config = {
        "adapters": {
            "cheap": {"type": "fake", "enabled": True, "cost_tier": "cheap", "trust": 5},
            "premium": {"type": "fake", "enabled": True, "cost_tier": "premium", "trust": 5, "capabilities": ["architecture"]},
            "failing": {"type": "fake", "enabled": True, "cost_tier": "local", "trust": 5},
        },
        "routing": {"retry_limit": 0},
        "goal": {"max_agents": 2, "max_rounds": 1, "max_reviewers": 1},
    }
    fabric = AgentFabric({"adapters": {}, "routing": {}, "goal": config["goal"]}, storage)
    fabric.config = config
    fabric.adapters = {"cheap": object(), "premium": object(), "failing": object()}
    storage.sync_agents([
        {"adapter_id": "cheap", "runtime_name": "Cheap", "type": "fake", "enabled": True, "cost_tier": "cheap"},
        {"adapter_id": "premium", "runtime_name": "Premium", "type": "fake", "enabled": True, "cost_tier": "premium", "capabilities": ["architecture"]},
        {"adapter_id": "failing", "runtime_name": "Failing", "type": "fake", "enabled": True, "cost_tier": "local"},
    ])
    return fabric


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "reputation.sqlite"
        storage = Storage(db)
        storage.sync_agents([
            {"adapter_id": "alpha", "runtime_name": "Alpha", "type": "fake", "enabled": True},
            {"adapter_id": "beta", "runtime_name": "Beta", "type": "fake", "enabled": True},
        ])

        rep = _delivery(storage, "alpha", ok=True, body="", status="empty_reply")
        after_empty = rep["trust_score"]
        assert after_empty < 100, rep
        rep = _delivery(storage, "alpha", ok=True, body="ok", status="replied")
        assert rep["trust_score"] > after_empty, rep
        rep = _delivery(storage, "alpha", ok=False, body="", status="timeout", error="timeout")
        assert rep["trust_score"] < after_empty, rep
        rep = _delivery(storage, "alpha", ok=True, body="ADAPTER_OK: beta", status="replied", quality="wrong_identity")
        assert rep["wrong_identity"] == 1 and rep["health_status"] == "degraded", rep
        rep = _delivery(storage, "alpha", ok=True, body="<tool_code>x</tool_code>", status="replied", quality="suspicious_output")
        assert rep["suspicious_outputs"] == 1, rep

        for index in range(3):
            rep = _delivery(storage, "alpha", ok=True, body="ADAPTER_OK: beta", status="replied", quality="wrong_identity")
        assert rep["health_status"] == "unstable", rep

        for index in range(6):
            _delivery(storage, "beta", ok=False, body="", status="timeout", error=f"timeout {index}")
        beta = storage.get_runtime_reputation("beta")
        assert beta and beta["health_status"] == "failing", beta
        storage.sync_agents([
            {"adapter_id": "alpha", "runtime_name": "Alpha", "type": "fake", "enabled": True},
            {"adapter_id": "beta", "runtime_name": "Beta", "type": "fake", "enabled": True},
            {"adapter_id": "antigravity", "runtime_name": "Antigravity", "type": "antigravity", "enabled": True},
        ])
        for index in range(6):
            _delivery(storage, "antigravity", ok=True, body="", status="empty_reply")
        antigravity = storage.get_runtime_reputation("antigravity")
        assert antigravity and antigravity["health_status"] == "failing", antigravity
        assert storage._runtime_health_status(95, recent_timeouts=0, recent_empty_replies=0, recent_failures=0, recent_wrong_identity=0) == "healthy"
        assert storage._runtime_health_status(80, recent_timeouts=0, recent_empty_replies=0, recent_failures=0, recent_wrong_identity=0) == "degraded"
        assert storage._runtime_health_status(55, recent_timeouts=0, recent_empty_replies=0, recent_failures=0, recent_wrong_identity=0) == "unstable"
        assert storage._runtime_health_status(20, recent_timeouts=0, recent_empty_replies=0, recent_failures=0, recent_wrong_identity=0) == "unstable"
        assert storage._runtime_health_status(
            20,
            recent_timeouts=1,
            recent_empty_replies=0,
            recent_failures=1,
            recent_wrong_identity=0,
            sample_size=2,
            latest_status="timeout",
        ) == "unstable"

        fabric = _fabric(storage)
        for index in range(6):
            _delivery(storage, "failing", ok=False, body="", status="timeout", error=f"timeout {index}")
        cheap = fabric._goal_mode_agents(["failing", "premium", "cheap"], "cheap", "basic summary")
        full = fabric._goal_mode_agents(["failing", "premium", "cheap"], "full", "architecture plan")
        assert "failing" not in cheap, cheap
        assert "failing" not in full, full

        summary = storage.workforce_summary()
        lines = _workforce_health_lines(summary)
        assert "Workforce Summary" in lines[0]
        assert any(line.startswith("failing:") for line in lines), lines
        storage.upsert_runtime({"runtime_id": "codex", "runtime_type": "codex", "enabled": True})
        storage.upsert_runtime({"runtime_id": "ollama", "runtime_type": "ollama", "enabled": False})
        storage.sync_agents([
            {"adapter_id": "cheap", "runtime_name": "Cheap", "type": "fake", "enabled": True},
            {"adapter_id": "premium", "runtime_name": "Premium", "type": "fake", "enabled": True},
            {"adapter_id": "failing", "runtime_name": "Failing", "type": "fake", "enabled": True},
            {"adapter_id": "disabled-worker", "runtime_name": "Disabled", "type": "fake", "enabled": False},
        ])
        summary = storage.workforce_summary()
        ranked = set(summary["top_trusted"]) | set(summary["most_unstable"])
        assert "codex" not in ranked and "ollama" not in ranked and "disabled-worker" not in ranked, summary
        inactive_ids = {item["runtime_id"] for item in summary["available_but_inactive"]}
        assert {"codex", "ollama", "disabled-worker"}.issubset(inactive_ids), summary

        storage._conn.close()
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE runtime_reputation")
        conn.commit()
        conn.close()
        migrated = Storage(db)
        assert migrated.get_runtime_reputation("alpha") is not None

    print("runtime reputation smoke test: ok")


if __name__ == "__main__":
    main()
