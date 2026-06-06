#!/usr/bin/env python3
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters import ADAPTER_TYPES, build_adapter
from synkraken.adapters.antigravity import AntigravityAdapter
from synkraken.adapters.base import BaseAdapter
from synkraken.adapters.cli_utils import build_adapter_command
from synkraken.adapters.goose import GooseAdapter
from synkraken.adapters.openclaw import OpenClawAdapter


def main() -> None:
    remote_command = build_adapter_command(
        {
            "remote_host": "agent-box.local",
            "remote_user": "operator",
            "remote_port": 2222,
            "ssh_identity_file": "~/.ssh/synkraken_worker",
            "remote_working_dir": "/workspace/project",
            "remote_path": ["/home/operator/.nvm/versions/node/v24.15.0/bin"],
            "ssh_options": ["-o", "BatchMode=yes"],
        },
        ["goose", "run", "--text", "hello remote worker"],
    )
    assert remote_command[:8] == [
        "ssh",
        "-p",
        "2222",
        "-i",
        str(Path("~/.ssh/synkraken_worker").expanduser()),
        "-o",
        "BatchMode=yes",
        "operator@agent-box.local",
    ]
    assert (
        "cd /workspace/project && "
        "PATH=/home/operator/.nvm/versions/node/v24.15.0/bin:$PATH "
        "goose run --text 'hello remote worker'"
    ) == remote_command[-1]

    goose = GooseAdapter("goose", {"type": "goose"})
    assert goose._normalize_output(
        "──────────────── ▸ todo_write todo content: - [ ] Stop requested Stopped. Let me know if you need anything else."
    ) == "Stopped. Let me know if you need anything else."

    openclaw = OpenClawAdapter("openclaw-main", {"type": "openclaw"})
    assert openclaw._fallback_text(
        {"runId": "abc", "status": "ok", "summary": "completed", "result": {"payloads": []}},
        '{"runId":"abc","status":"ok","summary":"completed"}',
        "",
        True,
    ) == "OpenClaw completed."

    antigravity = AntigravityAdapter("antigravity", {"type": "google_antigravity"})
    assert antigravity._auth_required(
        "Authentication required. Please visit https://accounts.google.com/o/oauth2/auth"
    )

    assert ADAPTER_TYPES, "no adapters registered"
    for adapter_type, adapter_class in ADAPTER_TYPES.items():
        assert issubclass(adapter_class, BaseAdapter), f"{adapter_type} does not extend BaseAdapter"
        adapter = build_adapter(f"{adapter_type}-test", {
            "type": adapter_type,
            "runtime_name": f"{adapter_type} Test",
            "command": ["synkraken-adapter-conformance-placeholder"],
            "enabled": True,
            "timeout_seconds": 1,
            "capabilities": ["conformance"],
        })
        health = adapter.health()
        assert health["adapter_id"] == f"{adapter_type}-test"
        assert health["type"] == adapter_type
        assert health["runtime_name"] == f"{adapter_type} Test"
        assert health["enabled"] is True
        assert "send" in adapter_class.__dict__, f"{adapter_type} must implement send()"

        module = inspect.getmodule(adapter_class)
        source = inspect.getsource(module)
        if "subprocess" in source:
            assert "subprocess.run" not in source, f"{adapter_type} must use cli_utils.run_command"
            assert "run_command" in source, f"{adapter_type} should use cli_utils.run_command"

    print("adapter conformance smoke test: ok")


if __name__ == "__main__":
    main()
