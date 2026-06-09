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
    original_get_json = tui._get_json
    original_post_json = tui._post_json
    original_thread = tui.threading.Thread

    def fake_get_json(url: str) -> dict:
        if "/v1/rooms/missing" in url:
            raise tui.TuiHttpError(404, "room not found: missing")
        raise AssertionError(url)

    def fake_post_json(url: str, payload: dict) -> dict:
        if url.endswith("/v1/messages") and payload.get("target") == "room:missing":
            raise tui.TuiHttpError(404, "room not found: missing")
        raise AssertionError((url, payload))

    try:
        tui._get_json = fake_get_json
        tui._post_json = fake_post_json
        tui.threading.Thread = InlineThread

        state: dict = {}
        label, result, hint = tui._exec_room_command("http://daemon", "enter missing", state, {})
        assert label == "room error"
        assert hint == ""
        assert result is not None
        body = result["messages"][0]["body"]
        assert body == "Room not found: missing\n\nSuggested actions:\n/room create missing\n/rooms"
        assert state.get("current_room") is None

        try:
            tui._room_member_ids("http://daemon", "missing")
        except tui.TuiHttpError as exc:
            assert exc.status == 404
            assert exc.detail == "room not found: missing"
        else:
            raise AssertionError("missing room member lookup should raise TuiHttpError")

        state = {"view": "chat", "current_room": "missing", "command_result": ("#missing", {"messages": []})}
        tui._start_async_send(state, "http://daemon", "room:missing", "say hello", "#missing")
        assert state["pending"]["done"] is True
        assert state["pending"]["http_status"] == 404
        assert state["pending"]["error"] == "room not found: missing"
    finally:
        tui._get_json = original_get_json
        tui._post_json = original_post_json
        tui.threading.Thread = original_thread

    print("tui missing room smoke test: ok")


if __name__ == "__main__":
    main()
