#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken import tui


def _agent(adapter_id: str, status: str = "online") -> dict:
    return {
        "adapter_id": adapter_id,
        "runtime_name": adapter_id,
        "type": adapter_id,
        "enabled": True,
        "status": status,
    }


def _captured_panel_lines(fn, *args) -> list[str]:
    captured: list[str] = []
    original_draw_panel = tui._draw_panel
    original_panel_lines = tui._panel_lines

    def capture(_stdscr, _y, _x, _w, _h, lines, inner_pad=2):
        del inner_pad
        for item in lines:
            captured.append(str(item[0] if isinstance(item, tuple) else item))

    try:
        tui._draw_panel = lambda *a, **k: None
        tui._panel_lines = capture
        fn(None, *args)
    finally:
        tui._draw_panel = original_draw_panel
        tui._panel_lines = original_panel_lines
    return captured


def main() -> None:
    agent_ids = [
        "claude",
        "goose",
        "hermes",
        "openclaw-main",
        "crush",
        "google-antigravity",
    ]
    data = {
        "health": {"ok": True},
        "agents": {"agents": [_agent(adapter_id) for adapter_id in agent_ids]},
        "deliveries": {"deliveries": []},
        "recent": {"conversations": []},
        "rooms": {"rooms": []},
        "flight": {},
    }

    dashboard_lines = _captured_panel_lines(
        tui._view_dashboard, data, set(), [], 0, 60, 180
    )
    dashboard_text = "\n".join(dashboard_lines)
    for adapter_id in agent_ids:
        assert adapter_id in dashboard_text, adapter_id
    assert dashboard_text.count("@") >= len(agent_ids)

    extended = dict(data)
    extended["agents"] = {"agents": data["agents"]["agents"] + [_agent("new-runtime-42")]}
    adapter_lines = _captured_panel_lines(tui._view_adapters, extended, 0, 40, 180)
    adapter_text = "\n".join(adapter_lines)
    assert "new-runtime-42" in adapter_text
    assert len([line for line in adapter_lines if " type=" in line]) == 7
    assert tui._agent_color("new-runtime-42") in tui._AGENT_COLOR_PALETTE

    chat_lines = tui._chat_lines(
        {
            "messages": [
                {
                    "message_id": "m1",
                    "source": "synkraken-tui",
                    "target": "broadcast",
                    "timestamp": "2026-05-24T12:00:00+00:00",
                    "body": "@everyone status",
                },
                {
                    "message_id": "m2",
                    "source": "crush",
                    "target": "synkraken-tui",
                    "timestamp": "2026-05-24T12:00:01+00:00",
                    "body": "crush reply",
                },
                {
                    "message_id": "m3",
                    "source": "google-antigravity",
                    "target": "synkraken-tui",
                    "timestamp": "2026-05-24T12:00:02+00:00",
                    "body": "   ",
                },
            ],
            "deliveries": [
                {
                    "message_id": "m1",
                    "adapter_id": "google-antigravity",
                    "ok": True,
                    "body": "   ",
                    "created_at": "2026-05-24T12:00:03+00:00",
                }
            ],
        },
        180,
    )
    chat_text = "\n".join(str(line[0]) for line in chat_lines)
    assert "crush" in chat_text
    assert "google-antigravity" in chat_text
    assert "[empty reply]" in chat_text

    deliveries = [
        {"adapter_id": "claude", "runtime_name": "claude", "ok": True, "body": "ack"},
        {"adapter_id": "goose", "runtime_name": "goose", "ok": True, "body": ""},
        {"adapter_id": "hermes", "runtime_name": "hermes", "ok": False, "error": "failed"},
        {"adapter_id": "openclaw-main", "runtime_name": "openclaw-main", "ok": False, "error": "timeout"},
        {"adapter_id": "crush", "runtime_name": "crush", "ok": True, "body": "ack"},
        {"adapter_id": "google-antigravity", "runtime_name": "google-antigravity", "ok": True, "body": "ack"},
    ]
    result_lines = _captured_panel_lines(
        tui._view_command_result,
        "broadcast",
        {"message": {"source": "synkraken-tui", "target": "broadcast"}, "deliveries": deliveries},
        0,
        60,
        180,
    )
    result_text = "\n".join(result_lines)
    for adapter_id in agent_ids:
        assert adapter_id in result_text, adapter_id
    assert result_text.count("acknowledged") == 3
    assert "empty_reply" in result_text
    assert "failed" in result_text
    assert "timed_out" in result_text
    assert "[empty reply]" in result_text

    source = Path(tui.__file__).read_text(encoding="utf-8")
    assert "_AGENT_COLOR_PAIRS" not in source
    assert "[:4]" not in source
    assert "range(4)" not in source
    print("tui dynamic agents smoke test: ok")


if __name__ == "__main__":
    main()
