#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken import tui


class InlineThread:
    def __init__(self, target, daemon=True):
        self.target = target

    def start(self):
        self.target()


def main() -> None:
    data = {
        "agents": {
            "agents": [
                {"adapter_id": "crush", "runtime_name": "crush", "enabled": True, "status": "online"},
                {"adapter_id": "goose", "runtime_name": "goose", "enabled": True, "status": "online"},
            ],
        },
        "rooms": {"rooms": [{"name": "stress1", "member_count": 2}]},
    }

    original_post_json = tui._post_json
    original_get_json = tui._get_json
    original_thread = tui.threading.Thread
    original_room_transcript = tui._handle_room_transcript
    calls: list[tuple[str, dict]] = []

    def fake_post_json(url: str, payload: dict) -> dict:
        calls.append((url, payload))
        target = str(payload.get("target") or "room:stress1")
        if target == "room:missing":
            raise tui.TuiHttpError(404, "room not found: missing")
        delivery_target = "goose" if target.startswith("room:") else target
        return {
            "message": {
                "message_id": "m1",
                "conversation_id": "room:stress1",
                "source": payload.get("source", "synkraken-tui"),
                "target": target,
                "body": payload.get("body", ""),
            },
            "routing": {
                "requested_target": target,
                "resolved_targets": ["crush", "goose"] if target == "room:stress1" else [target],
                "reply_context": "room:stress1",
                "transcript_target": "room:stress1",
            },
            "deliveries": [
                {
                    "message_id": "m1",
                    "adapter_id": delivery_target,
                    "delivery_target": delivery_target,
                    "original_target": target,
                    "reply_context": "room:stress1",
                    "ok": True,
                    "body": "",
                    "status": "empty_reply",
                }
            ],
            "dead_letters": [],
        }

    def fake_get_json(url: str) -> dict:
        if url.endswith("/v1/rooms/stress1"):
            return {"name": "stress1", "members": [{"adapter_id": "crush"}, {"adapter_id": "goose"}]}
        if url.endswith("/v1/rooms/empty"):
            return {"name": "empty", "members": []}
        if url.endswith("/v1/rooms/missing"):
            raise tui.TuiHttpError(404, "room not found: missing")
        raise AssertionError(url)

    try:
        tui._post_json = fake_post_json
        tui._get_json = fake_get_json
        tui.threading.Thread = InlineThread
        tui._handle_room_transcript = lambda _base, name: {
            "conversation_id": f"room:{name}",
            "messages": [
                {
                    "message_id": "m1",
                    "source": "synkraken-tui",
                    "target": f"room:{name}",
                    "timestamp": "2026-05-26T12:00:00+00:00",
                    "body": "Reply with your ID only.",
                }
            ],
        }

        aliases = tui._mention_alias_map(data)
        targets, body = tui._parse_leading_mentions("@everyone Reply with your ID only.", aliases)
        assert targets == ["broadcast"]
        dashboard_state = {"view": "dashboard", "current_room": "stress1"}
        assert tui._chat_input_room_name(dashboard_state) == ""
        target, dashboard_body = tui._mention_route(targets[0], body, tui._chat_input_room_name(dashboard_state))
        assert target == "broadcast"
        assert dashboard_body == "Reply with your ID only."
        assert tui._pending_room_name({"target": "broadcast", "metadata": {}}) == ""
        assert tui._pending_room_name({"target": "crush", "metadata": {}}) == ""
        assert tui._pending_room_name({"target": "room:stress1", "metadata": {}}) == "stress1"
        assert tui._pending_room_name({"target": "crush", "metadata": {"room_context": "room:stress1"}}) == "stress1"

        chat_state = {"view": "chat", "current_room": "stress1", "chat_target": "room:stress1"}
        assert tui._chat_input_room_name(chat_state) == "stress1"
        target, body = tui._mention_route(targets[0], body, "stress1")
        assert target == "room:stress1"
        assert tui._room_member_ids("http://daemon", "stress1") == ["crush", "goose"]

        state = {"view": "chat", "current_room": "stress1", "command_result": ("#stress1", {"messages": []})}
        tui._start_async_send(state, "http://daemon", target, body, "#stress1")
        assert state["pending"]["done"] is True
        assert calls[-1][0] == "http://daemon/v1/messages"
        assert calls[-1][1]["target"] == "room:stress1"
        assert "/v1/rooms/stress1/messages" not in calls[-1][0]

        empty_members = tui._room_member_ids("http://daemon", "empty")
        assert empty_members == []
        assert tui._no_room_members_message() == "This room has no workers yet.\nAdd workers with:\n/room add <room> <worker>"

        try:
            tui._room_member_ids("http://daemon", "missing")
        except tui.TuiHttpError as exc:
            assert exc.status == 404
            assert tui._room_not_found_message("missing") == (
                "Room not found: missing\n\nSuggested actions:\n/room create missing\n/rooms"
            )
        else:
            raise AssertionError("missing room should raise TuiHttpError")

        calls.clear()
        state = {"view": "chat", "current_room": "missing", "command_result": ("#missing", {"messages": []})}
        tui._start_async_send(state, "http://daemon", "room:missing", "hello", "#missing")
        assert state["pending"]["done"] is True
        assert state["pending"]["http_status"] == 404
        assert state["pending"]["error"] == "room not found: missing"

        calls.clear()
        targets, body = tui._parse_leading_mentions("@crush ping", aliases)
        assert targets == ["crush"]
        state = {"view": "chat", "current_room": "stress1", "command_result": ("#stress1", {"messages": []})}
        tui._start_async_send(
            state,
            "http://daemon",
            "crush",
            body,
            "@crush",
            metadata={"room_context": "room:stress1"},
        )
        assert calls[-1][0] == "http://daemon/v1/messages"
        assert calls[-1][1]["target"] == "crush"
        assert calls[-1][1]["metadata"] == {"room_context": "room:stress1"}

        calls.clear()
        state = {"view": "chat", "current_room": "stress1", "command_result": ("#stress1", {"messages": []})}
        tui._start_async_room_note(state, "http://daemon", "stress1", "plain operator note")
        assert state["pending"]["done"] is True
        assert calls[-1][0] == "http://daemon/v1/rooms/stress1/messages"
        assert "target" not in calls[-1][1]

        merged = tui._merge_dispatch_result_into_room_transcript(
            "http://daemon",
            "stress1",
            {
                "deliveries": [
                    {"message_id": "m1", "adapter_id": "crush", "ok": True, "body": "crush"},
                    {"message_id": "m1", "adapter_id": "goose", "ok": True, "body": "", "status": "empty_reply"},
                ],
                "dead_letters": [],
            },
        )
        assert len(merged["deliveries"]) == 2
        assert merged["delivery_summary"] == "targets: 2  replied: 1  empty: 1  failed: 0  timeout: 0"
        chat_text = "\n".join(str(line[0]) for line in tui._chat_lines(merged, 160))
        assert "targets: 2" in chat_text
        assert "crush" in chat_text
        assert "goose" in chat_text
        assert "[empty reply]" in chat_text

        label, _result, hint = tui._exec_room_command("http://daemon", "members", {"current_room": "stress1"}, data)
        assert label == "room members"
        assert "#stress1: crush, goose" == hint

        calls.clear()
        label, result, hint = tui._exec_room_command(
            "http://daemon",
            "add @crush @goose",
            {"current_room": "stress1"},
            data,
        )
        assert label == "rooms"
        assert result is None
        assert hint == "added crush, goose to #stress1"
        assert calls == [
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "crush"}),
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "goose"}),
        ]

        calls.clear()
        label, result, hint = tui._exec_room_command(
            "http://daemon",
            "add @crush @goose",
            {"chat_target": "room:stress1"},
            data,
        )
        assert label == "rooms"
        assert result is None
        assert hint == "added crush, goose to #stress1"
        assert calls == [
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "crush"}),
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "goose"}),
        ]

        calls.clear()
        label, result, hint = tui._exec_room_command(
            "http://daemon",
            "add @crush @goose",
            {"command_result": ("#stress1", {"messages": []})},
            data,
        )
        assert label == "rooms"
        assert result is None
        assert hint == "added crush, goose to #stress1"
        assert calls == [
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "crush"}),
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "goose"}),
        ]

        calls.clear()
        label, result, hint = tui._exec_room_command(
            "http://daemon",
            "add @crush @goose",
            {},
            data,
        )
        assert label == "rooms"
        assert result is None
        assert hint == "open a room first, or use /room add <room> <agent...>"
        assert calls == []

        calls.clear()
        label, result, hint = tui._exec_room_command(
            "http://daemon",
            "add stress1 @crush @goose",
            {},
            data,
        )
        assert label == "rooms"
        assert result is None
        assert hint == "added crush, goose to #stress1"
        assert calls == [
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "crush"}),
            ("http://daemon/v1/rooms/stress1/members", {"adapter_id": "goose"}),
        ]
    finally:
        tui._post_json = original_post_json
        tui._get_json = original_get_json
        tui.threading.Thread = original_thread
        tui._handle_room_transcript = original_room_transcript

    print("tui room dispatch smoke test: ok")


if __name__ == "__main__":
    main()
