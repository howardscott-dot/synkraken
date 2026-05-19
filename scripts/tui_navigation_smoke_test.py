#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken import tui


def make_result(count: int = 80) -> dict:
    return {
        "conversation_id": "room:test1",
        "messages": [
            {
                "message_id": f"m-{idx}",
                "conversation_id": "room:test1",
                "source": "goose" if idx % 2 else "synkraken-team",
                "target": "room:test1",
                "timestamp": "2026-05-19T12:00:00+00:00",
                "body": (
                    "nomination phase owner vote"
                    if idx == 12
                    else f"long transcript line {idx}"
                ),
            }
            for idx in range(count)
        ],
        "deliveries": [],
        "dead_letters": [],
    }


def main() -> None:
    state = {
        "view": "chat",
        "current_room": "test1",
        "chat_target": "room:test1",
        "command_result": ("#test1", make_result()),
        "transcripts": {},
    }
    lines = tui._chat_lines(state["command_result"][1], 100)
    viewport_h = 12

    visible, start, offset = tui._visible_transcript_slice(lines, viewport_h, 0)
    assert offset == 0
    assert start == len(lines) - viewport_h
    assert "long transcript line 79" in "\n".join(tui._line_text(line) for line in visible)
    tui._sync_transcript_line_count(tui._transcript_state(state), len(lines))

    tui._scroll_transcript(state, 20, len(lines), viewport_h)
    assert tui._transcript_state(state)["scroll_offset"] == 20
    visible, start, offset = tui._visible_transcript_slice(
        lines, viewport_h, tui._transcript_state(state)["scroll_offset"]
    )
    assert offset == 20
    assert start == len(lines) - viewport_h - 20
    before_text = "\n".join(tui._line_text(line) for line in visible)

    before = tui._transcript_state(state)["scroll_offset"]
    state["command_result"][1]["messages"].append({
        "message_id": "m-new",
        "conversation_id": "room:test1",
        "source": "hermes",
        "target": "room:test1",
        "timestamp": "2026-05-19T12:01:00+00:00",
        "body": "new live message",
    })
    newer_lines = tui._chat_lines(state["command_result"][1], 100)
    tui._sync_transcript_line_count(tui._transcript_state(state), len(newer_lines))
    assert tui._transcript_state(state)["scroll_offset"] > before
    visible, _, _ = tui._visible_transcript_slice(newer_lines, viewport_h, before)
    assert "new live message" not in "\n".join(tui._line_text(line) for line in visible)
    visible, _, _ = tui._visible_transcript_slice(
        newer_lines, viewport_h, tui._transcript_state(state)["scroll_offset"]
    )
    assert "\n".join(tui._line_text(line) for line in visible) == before_text

    tui._jump_transcript(state, True, len(newer_lines), viewport_h)
    assert tui._transcript_state(state)["scroll_offset"] == 0
    visible, _, _ = tui._visible_transcript_slice(newer_lines, viewport_h, 0)
    assert "new live message" in "\n".join(tui._line_text(line) for line in visible)

    state["last_chat_viewport_h"] = viewport_h
    assert tui._search_transcript(state, newer_lines, "nomination")
    assert tui._transcript_state(state)["scroll_offset"] > 0
    current = tui._transcript_state(state)["scroll_offset"]
    assert tui._repeat_search_transcript(state, newer_lines)
    assert tui._transcript_state(state)["scroll_offset"] == current
    assert tui._repeat_search_transcript(state, newer_lines, backwards=True)

    with tempfile.TemporaryDirectory() as tmp:
        old_cwd = Path.cwd()
        os.chdir(tmp)
        try:
            path = tui._save_current_transcript(state)
            assert path == Path("exports/room-test1-20260519.txt")
            text = path.read_text(encoding="utf-8")
            assert "Transcript: #test1" in text
            assert "nomination phase owner vote" in text
            assert "new live message" in text
        finally:
            os.chdir(old_cwd)

    print("tui navigation smoke test: ok")


if __name__ == "__main__":
    main()
