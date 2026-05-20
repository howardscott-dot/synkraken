#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken import tui
from synkraken.tui import _is_unknown_slash_command, _local_command_lines, _parse_leading_mentions


def main() -> None:
    data = {
        "health": {"ok": True, "timestamp": "2026-05-18T12:00:00+00:00"},
        "agents": {"agents": [{"adapter_id": "goose", "runtime_name": "Goose", "type": "goose", "enabled": True}]},
        "rooms": {"rooms": [{"name": "ops", "member_count": 1}]},
        "tasks": {"tasks": [{"task_id": "task-1", "title": "Check bridge", "status": "open"}]},
    }
    state = {"view": "dashboard", "event_filter": "all"}

    assert _local_command_lines("/status", "http://127.0.0.1:9460", data, state)
    assert _local_command_lines("/health", "http://127.0.0.1:9460", data, state)
    assert _local_command_lines("/agents", "http://127.0.0.1:9460", data, state)
    assert _local_command_lines("/rooms", "http://127.0.0.1:9460", data, state)
    assert _local_command_lines("/tasks", "http://127.0.0.1:9460", data, state)
    assert _is_unknown_slash_command("/notreal")
    assert not _is_unknown_slash_command("/status")
    assert not _is_unknown_slash_command("@goose hello")
    assert not _is_unknown_slash_command("#ops hello")
    aliases = {"claude": "claude", "goose": "goose", "hermes": "hermes", "openclaw": "openclaw-main"}
    assert _parse_leading_mentions('@claude send a message to "@goose" and ask him to reply', aliases) == (
        ["claude"], 'send a message to "@goose" and ask him to reply'
    )
    assert _parse_leading_mentions('@hermes @openclaw please confer', aliases) == (
        ["hermes", "openclaw-main"], 'please confer'
    )

    sent: list[tuple[str, str]] = []
    original_handle_send = tui._handle_send
    original_thread = tui.threading.Thread
    class InlineThread:
        def __init__(self, target, daemon=True):
            self.target = target
        def start(self):
            self.target()
    try:
        tui._handle_send = lambda _base, target, body: sent.append((target, body)) or {
            "message": {"source": "synkraken-tui", "target": target},
            "deliveries": [{"adapter_id": target, "ok": True}],
            "dead_letters": [],
        }
        tui.threading.Thread = InlineThread
        pending_state: dict = {}
        tui._start_async_multi_send(pending_state, "http://127.0.0.1:9460", ["hermes", "openclaw-main"], "please confer")
    finally:
        tui._handle_send = original_handle_send
        tui.threading.Thread = original_thread
    assert sent == [("hermes", "please confer"), ("openclaw-main", "please confer")]
    assert pending_state["pending"]["done"] is True
    assert pending_state["pending"]["result"]["deliveries"] == [
        {"adapter_id": "hermes", "ok": True},
        {"adapter_id": "openclaw-main", "ok": True},
    ]

    # While a room chat is open, completion of a direct send must not replace
    # the visible room transcript with the direct-message result.
    original_room_transcript = tui._handle_room_transcript
    try:
        tui._handle_room_transcript = lambda _base, name: {"messages": [{"target": f"room:{name}"}]}
        state = {
            "view": "chat",
            "current_room": "test1",
            "chat_target": "room:test1",
            "pending": {
                "label": "@hermes",
                "target": "hermes",
                "started_at": 0,
                "done": True,
                "result": {"message": {"target": "hermes"}, "deliveries": [], "dead_letters": []},
                "error": None,
            },
        }
        p = state.pop("pending")
        if state.get("view") == "chat" and state.get("current_room"):
            room_name = state["current_room"]
            state["command_result"] = (f"#{room_name}", tui._handle_room_transcript("base", room_name))
            state["chat_target"] = f"room:{room_name}"
    finally:
        tui._handle_room_transcript = original_room_transcript
    assert state["command_result"] == ("#test1", {"messages": [{"target": "room:test1"}]})
    assert state["chat_target"] == "room:test1"
    print("tui slash smoke test: ok")


if __name__ == "__main__":
    main()
