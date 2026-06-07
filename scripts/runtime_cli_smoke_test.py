#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken import cli_main


def run_cli(argv: list[str]) -> tuple[int, str]:
    old_argv = sys.argv[:]
    stdout = io.StringIO()
    try:
        sys.argv = ["synkraken", *argv]
        with redirect_stdout(stdout):
            try:
                cli_main.main()
            except SystemExit as exc:
                code = int(exc.code or 0)
            else:
                code = 0
    finally:
        sys.argv = old_argv
    return code, stdout.getvalue()


def main() -> None:
    parser = cli_main.build_parser()
    assert parser.parse_args(["runtimes"]).command == "runtimes"
    runtime_args = parser.parse_args(["runtime", "codex"])
    assert runtime_args.command == "runtime"
    assert runtime_args.runtime_args == ["codex"]
    doctor_args = parser.parse_args(["runtime", "doctor"])
    assert doctor_args.command == "runtime"
    assert doctor_args.runtime_args == ["doctor"]

    original_get_json = cli_main.get_json
    original_cwd = Path.cwd()
    try:
        requested_urls: list[str] = []

        def fake_get_json(url: str) -> dict:
            requested_urls.append(url)
            if url.endswith("/v1/runtimes/doctor"):
                return {
                    "runtimes": [
                        {
                            "runtime_id": "crush",
                            "runtime_type": "crush",
                            "adapter_type": "crush",
                            "command": ["crush"],
                            "enabled": True,
                            "registered": True,
                            "ok": True,
                            "health": {"type": "crush", "enabled": True},
                            "node_available": True,
                        }
                    ]
                }
            raise AssertionError(f"unexpected URL: {url}")

        cli_main.get_json = fake_get_json
        code, output = run_cli(["runtime", "doctor"])
        assert code == 0
        assert any(url.endswith("/v1/runtimes/doctor") for url in requested_urls)
        assert "Runtime doctor:" in output
        assert "node available to adapter: yes" in output

        cli_main.get_json = lambda url: (_ for _ in ()).throw(urllib.error.URLError("offline"))
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            code, output = run_cli(["runtimes"])
            assert code == 0
            assert "Runtime registry:" in output
            assert "(no runtimes)" in output

            config = {
                "adapters": {
                    "claude": {
                        "type": "claude",
                        "runtime_type": "claude",
                        "runtime_name": "Claude Code",
                        "command": ["claude"],
                        "capabilities": ["coding"],
                        "cost_tier": "premium",
                        "enabled": True,
                    }
                },
                "runtime_registry": {
                    "codex": {
                        "runtime_id": "codex",
                        "runtime_type": "codex",
                        "adapter_type": "unsupported",
                        "command": ["codex"],
                        "capabilities": ["coding", "review"],
                        "cost_tier": "premium",
                        "enabled": False,
                    }
                },
            }
            Path("config.local.json").write_text(json.dumps(config), encoding="utf-8")

            code, output = run_cli(["runtimes"])
            assert code == 0
            assert "Claude Code" in output
            assert "Codex" in output
            assert "status: registry-only" in output
            assert "note: adapter not implemented yet" in output

            code, output = run_cli(["runtime", "codex"])
            assert code == 0
            assert "id: codex" in output
            assert "display name: Codex" in output
            assert "adapter-supported: no" in output

            code, output = run_cli(["runtime", "doctor"])
            assert code == 0
            assert "Runtime doctor:" in output
            assert "adapter: registry-only" in output
            assert "configured command exists:" in output
    finally:
        os.chdir(original_cwd)
        cli_main.get_json = original_get_json

    print("runtime CLI smoke test: ok")


if __name__ == "__main__":
    main()
