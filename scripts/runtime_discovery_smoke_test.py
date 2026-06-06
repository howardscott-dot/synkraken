#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synkraken.discovery import (  # noqa: E402
    discover_local_runtimes,
    discover_remote_runtimes,
    merge_discovered_config,
    parse_runtime_selection,
)
from synkraken import discovery, setup_mode  # noqa: E402


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _input_returning(value: str):
    def _fake_input(prompt: str = "") -> str:
        if prompt:
            print(prompt, end="")
        return value

    return _fake_input


def _input_sequence(values: list[str]):
    pending = iter(values)

    def _fake_input(prompt: str = "") -> str:
        if prompt:
            print(prompt, end="")
        return next(pending)

    return _fake_input


def _fake_binary(directory: Path, name: str, version: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_fake_path_and_versions(tmp: Path) -> list[dict]:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "goose", "goose 1.2.3")
    _fake_binary(bin_dir, "claude", "claude 0.9.0")
    _fake_binary(bin_dir, "ollama", "ollama version 0.5.0")

    runtimes = discover_local_runtimes(search_path=str(bin_dir), home=tmp, include_common_dirs=False)
    by_id = {runtime["runtime_id"]: runtime for runtime in runtimes}
    assert set(by_id) == {"claude", "goose", "ollama"}, by_id
    assert by_id["goose"]["adapter_supported"] is True
    assert by_id["ollama"]["adapter_supported"] is False
    assert by_id["claude"]["version"] == "claude 0.9.0"
    assert by_id["goose"]["command"][0] == str(bin_dir / "goose")
    return runtimes


def test_selection_parser(runtimes: list[dict]) -> None:
    assert parse_runtime_selection(runtimes, "") == runtimes
    assert parse_runtime_selection(runtimes, "all") == runtimes
    assert parse_runtime_selection(runtimes, "none") == []
    selected = parse_runtime_selection(runtimes, "1,3")
    assert [runtime["runtime_id"] for runtime in selected] == ["claude", "ollama"]
    spaced = parse_runtime_selection(runtimes, "1, 3")
    assert [runtime["runtime_id"] for runtime in spaced] == ["claude", "ollama"]
    space_only = parse_runtime_selection(runtimes, "1 3")
    assert [runtime["runtime_id"] for runtime in space_only] == ["claude", "ollama"]
    mixed = parse_runtime_selection(runtimes, "1 2,3")
    assert [runtime["runtime_id"] for runtime in mixed] == ["claude", "goose", "ollama"]
    supported = parse_runtime_selection(runtimes, "all", supported_only=True)
    assert {runtime["runtime_id"] for runtime in supported} == {"claude", "goose"}
    for raw in ("0", "4", "1,4", "goose"):
        try:
            parse_runtime_selection(runtimes, raw)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid selection to fail: {raw!r}")


def test_config_merge(runtimes: list[dict]) -> None:
    existing = {
        "adapters": {
            "goose": {
                "type": "goose",
                "enabled": True,
                "command": ["/custom/goose"],
                "timeout_seconds": 300,
            }
        }
    }
    merged, summary = merge_discovered_config(existing, runtimes, behaviour="merge")
    assert merged["adapters"]["goose"]["command"] == ["/custom/goose"]
    assert merged["adapters"]["goose"]["timeout_seconds"] == 300
    assert "claude" in merged["adapters"]
    assert "ollama" not in merged["adapters"]
    assert merged["runtime_registry"]["ollama"]["adapter_type"] == "unsupported"
    assert merged["runtime_registry"]["ollama"]["enabled"] is False
    assert summary["behaviour"] == "merge"

    replaced, replace_summary = merge_discovered_config(existing, runtimes, behaviour="replace")
    assert replaced["adapters"]["goose"]["command"][0].endswith("/goose")
    assert replace_summary["adapters_replaced"] == ["goose"]
    assert set(replaced["adapters"]) == {"claude", "goose"}

    skipped, skip_summary = merge_discovered_config(existing, runtimes, behaviour="skip")
    assert skipped is existing
    assert skip_summary["behaviour"] == "skip"


def test_remote_discovery_preserves_ssh_config(tmp: Path) -> None:
    calls: list[list[str]] = []

    def _fake_run(command, **kwargs):
        calls.append(command)
        assert command[:4] == ["ssh", "-p", "2222", "-i"]
        assert command[4] == str(tmp / "synkraken_worker")
        assert "-o" in command
        assert "BatchMode=yes" in command
        assert command[-2] == "operator@agent-box.local"
        return subprocess.CompletedProcess(
            command,
            0,
            "claude\t/home/operator/.local/bin/claude\n"
            "goose\t/home/operator/.local/bin/goose\n"
            "openclaw\t/home/operator/.nvm/versions/node/v24.15.0/bin/openclaw\n",
            "",
        )

    with patch("synkraken.discovery.subprocess.run", _fake_run):
        runtimes = discover_remote_runtimes(
            remote_host="agent-box.local",
            remote_user="operator",
            remote_port=2222,
            ssh_identity_file=str(tmp / "synkraken_worker"),
            remote_working_dir="/workspace/project",
            remote_path=["/opt/agents/bin"],
            ssh_options=["-o", "BatchMode=yes"],
            include_version=False,
        )

    by_id = {runtime["runtime_id"]: runtime for runtime in runtimes}
    assert set(by_id) == {"claude", "goose", "openclaw-main"}
    assert by_id["openclaw-main"]["command"] == ["/home/operator/.nvm/versions/node/v24.15.0/bin/openclaw"]
    assert by_id["goose"]["remote_host"] == "agent-box.local"
    assert by_id["goose"]["remote_user"] == "operator"
    assert by_id["goose"]["remote_port"] == 2222
    assert by_id["goose"]["ssh_identity_file"] == str(tmp / "synkraken_worker")
    assert by_id["goose"]["remote_working_dir"] == "/workspace/project"
    assert by_id["goose"]["remote_path"][0] == "/opt/agents/bin"
    assert "/home/operator/.local/bin" in by_id["goose"]["remote_path"]
    assert "/home/operator/.nvm/versions/node/v24.15.0/bin" in by_id["goose"]["remote_path"]

    merged, _summary = merge_discovered_config({"adapters": {}, "runtime_registry": {}}, runtimes, behaviour="replace")
    goose = merged["adapters"]["goose"]
    openclaw = merged["adapters"]["openclaw-main"]
    assert goose["remote_host"] == "agent-box.local"
    assert goose["remote_user"] == "operator"
    assert goose["remote_working_dir"] == "/workspace/project"
    assert goose["remote_path"][0] == "/opt/agents/bin"
    assert goose["ssh_options"] == ["-o", "BatchMode=yes"]
    assert openclaw["remote_host"] == "agent-box.local"
    assert merged["runtime_registry"]["goose"]["remote_host"] == "agent-box.local"


def test_fake_agy_detected(tmp: Path) -> None:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "agy", "agy 0.1.0")

    runtimes = discover_local_runtimes(search_path=str(bin_dir), home=tmp, include_common_dirs=False)
    by_id = {runtime["runtime_id"]: runtime for runtime in runtimes}
    assert "google-antigravity" in by_id, by_id
    assert by_id["google-antigravity"]["label"] == "Google Antigravity"
    assert by_id["google-antigravity"]["command"][0] == str(bin_dir / "agy")
    assert by_id["google-antigravity"]["version"] == "agy 0.1.0"


def test_fake_ag_requires_antigravity_probe(tmp: Path) -> None:
    silver_bin = tmp / "silver" / "bin"
    silver_bin.mkdir(parents=True)
    _fake_binary(silver_bin, "ag", "ag version 2.2.0")
    silver_runtimes = discover_local_runtimes(search_path=str(silver_bin), home=tmp, include_common_dirs=False)
    silver_by_id = {runtime["runtime_id"]: runtime for runtime in silver_runtimes}
    assert "google-antigravity" not in silver_by_id, silver_by_id

    antigravity_bin = tmp / "antigravity" / "bin"
    antigravity_bin.mkdir(parents=True)
    _fake_binary(antigravity_bin, "ag", "Google Antigravity 0.2.0")
    antigravity_runtimes = discover_local_runtimes(
        search_path=str(antigravity_bin),
        home=tmp,
        include_common_dirs=False,
    )
    antigravity_by_id = {runtime["runtime_id"]: runtime for runtime in antigravity_runtimes}
    assert "google-antigravity" in antigravity_by_id, antigravity_by_id
    assert antigravity_by_id["google-antigravity"]["command"][0] == str(antigravity_bin / "ag")
    assert antigravity_by_id["google-antigravity"]["version"] == "Google Antigravity 0.2.0"


def test_cli_json_output(tmp: Path) -> None:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    _fake_binary(bin_dir, "goose", "goose smoke")
    _fake_binary(bin_dir, "agy", "Google Antigravity smoke")
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env["PYTHONPATH"] = str(ROOT)
    output = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "discover", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
    )
    data = json.loads(output)
    by_id = {runtime["runtime_id"]: runtime for runtime in data["runtimes"]}
    assert by_id["goose"]["version"] == "goose smoke"
    assert by_id["google-antigravity"]["command"][0] == str(bin_dir / "agy")
    assert by_id["google-antigravity"]["version"] == "Google Antigravity smoke"


def test_cli_formatting_with_long_command(tmp: Path) -> None:
    long_dir = tmp / ("very-long-command-path-" + ("nested-" * 8)) / "bin"
    long_dir.mkdir(parents=True)
    long_version = (
        "goose "
        + ("version segment " * 12)
        + "\n"
        "probe detail with enough separate words to wrap cleanly in a normal terminal "
        "while still remaining readable after indentation\n"
        "update available with a long diagnostic sentence that should stay in the probes list"
    )
    _fake_binary(long_dir, "goose", long_version)
    _fake_binary(long_dir, "agy", "Google Antigravity smoke")
    env = os.environ.copy()
    env["COLUMNS"] = "80"
    env["PATH"] = str(long_dir)
    env["PYTHONPATH"] = str(ROOT)

    plain = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "discover"],
        cwd=ROOT,
        env=env,
        text=True,
    )
    lines = plain.splitlines()
    assert lines[0] == "Discovered AI workers:", plain
    assert lines[1] == "", plain
    worker_lines = [line for line in lines if line.startswith("- ")]
    assert "- Goose" in worker_lines, plain
    assert "- Antigravity" in worker_lines, plain
    assert lines[-1] == f"Total found: {len(worker_lines)}", plain
    assert not ANSI_ESCAPE_RE.search(plain), plain
    assert str(long_dir / "goose") not in plain, plain
    assert "version" not in plain.lower(), plain
    assert "command:" not in plain, plain
    assert "detection:" not in plain, plain
    assert "capabilities:" not in plain, plain
    assert "adapter_type" not in plain, plain
    assert "runtime_type" not in plain, plain

    raw = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "discover", "--json"],
        cwd=ROOT,
        env=env,
        text=True,
    )
    raw_verbose = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "discover", "--json", "--verbose"],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert json.loads(raw) == json.loads(raw_verbose)
    by_id = {runtime["runtime_id"]: runtime for runtime in json.loads(raw)["runtimes"]}
    assert by_id["goose"]["command"][0] == str(long_dir / "goose")
    assert "probe_output" not in by_id["goose"]

    verbose = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "discover", "--verbose"],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert str(long_dir / "goose") in verbose
    verbose_lines = verbose.splitlines()
    goose_start = verbose_lines.index("Goose")
    goose_end = next(
        (idx for idx in range(goose_start + 1, len(verbose_lines)) if verbose_lines[idx] and not verbose_lines[idx].startswith("  ")),
        len(verbose_lines),
    )
    goose_block = "\n".join(verbose_lines[goose_start:goose_end])
    assert "  command: " in goose_block
    assert "  version: goose version segment" in goose_block
    assert "  detection: path" in goose_block
    assert "  capabilities: coding, review, files, shell" in goose_block
    assert "probes:" not in verbose
    assert "diagnostics:" not in verbose
    assert "adapter_type" not in verbose
    assert "runtime_type" not in verbose


def test_config_numbered_prompt() -> None:
    runtimes = [
        {"runtime_id": "claude", "label": "Claude Code"},
        {"runtime_id": "codex", "label": "Codex"},
        {"runtime_id": "goose", "label": "Goose"},
        {"runtime_id": "hermes", "label": "Hermes"},
        {"runtime_id": "openclaw", "label": "OpenClaw"},
        {"runtime_id": "crush", "label": "Crush"},
        {"runtime_id": "google-antigravity", "label": "Google Antigravity"},
        {"runtime_id": "ollama", "label": "Ollama"},
    ]
    selected = parse_runtime_selection(runtimes, "1,3,5")
    assert [runtime["runtime_id"] for runtime in selected] == ["claude", "goose", "openclaw"]
    expected = (
        "Discovered AI workers:\n"
        "\n"
        "1. Claude Code\n"
        "2. Codex\n"
        "3. Goose\n"
        "4. Hermes\n"
        "5. OpenClaw\n"
        "6. Crush\n"
        "7. Antigravity\n"
        "8. Ollama\n"
        "\n"
        "Enter numbers to enable, or press Enter for all:\n"
    )
    assert not hasattr(setup_mode, "_interactive_selection")
    assert not hasattr(setup_mode, "_render_checklist")

    out = io.StringIO()
    with patch("builtins.input", _input_returning("")), contextlib.redirect_stdout(out):
        selected = setup_mode._select_runtimes_for_config(runtimes)
    rendered = out.getvalue()
    assert rendered == expected, rendered
    assert selected == runtimes
    assert "[ ]" not in rendered
    assert "[x]" not in rendered
    assert "(space=toggle" not in rendered
    assert not ANSI_ESCAPE_RE.search(rendered), rendered

    out = io.StringIO()
    with patch("builtins.input", _input_sequence(["9", "1, 3, 5"])), contextlib.redirect_stdout(out):
        selected = setup_mode._select_runtimes_for_config(runtimes)
    rendered = out.getvalue()
    assert "Invalid selection: 9 is outside the range 1-8" in rendered
    assert [runtime["runtime_id"] for runtime in selected] == ["claude", "goose", "openclaw"]


def test_selected_bridge_skill_install_and_skips(tmp: Path) -> None:
    runtimes = [
        {
            "runtime_id": "claude",
            "label": "Claude Code",
            "adapter_type": "claude",
            "adapter_supported": True,
            "skill_path": str(tmp / "claude" / "skills" / "synkraken-bridge"),
            "skill_format": "folder",
        },
        {
            "runtime_id": "codex",
            "label": "Codex",
            "adapter_type": "unsupported",
            "adapter_supported": False,
            "skill_path": str(tmp / "codex" / "skills" / "synkraken-bridge"),
            "skill_format": "folder",
        },
        {
            "runtime_id": "ollama",
            "label": "Ollama",
            "adapter_type": "unsupported",
            "adapter_supported": False,
            "capabilities": ["local_model", "chat"],
        },
    ]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        results = setup_mode._install_bridge_skills_for_runtimes(runtimes)
        setup_mode._print_bridge_skill_results(results)
    rendered = out.getvalue()
    assert (tmp / "claude" / "skills" / "synkraken-bridge" / "SKILL.md").exists()
    assert results[0]["status"] == "installed"
    assert results[1] == {
        "status": "skipped",
        "label": "Codex",
        "detail": "bridge skill installer not implemented for this runtime yet",
    }
    assert results[2] == {
        "status": "skipped",
        "label": "Ollama",
        "detail": "local model runtime; bridge skill not applicable",
    }
    assert "✓ Claude Code" in rendered
    assert "- Codex" in rendered
    assert "skipped: bridge skill installer not implemented for this runtime yet" in rendered
    assert "- Ollama" in rendered
    assert "skipped: local model runtime; bridge skill not applicable" in rendered


def test_declined_bridge_skill_install_skips_cleanly(tmp: Path) -> None:
    runtime = {
        "runtime_id": "claude",
        "label": "Claude Code",
        "runtime_type": "claude",
        "command": [str(tmp / "bin" / "claude")],
        "capabilities": ["coding"],
        "cost_tier": "premium",
        "adapter_type": "claude",
        "adapter_supported": True,
        "supported_modes": ["direct"],
        "timeout_seconds": 120,
        "skill_path": str(tmp / "claude" / "skills" / "synkraken-bridge"),
        "skill_format": "folder",
    }
    config_path = tmp / "config.local.json"
    out = io.StringIO()
    with (
        patch("synkraken.setup_mode.discover_local_runtimes", return_value=[runtime]),
        patch("synkraken.setup_mode.DEFAULT_CONFIG_PATH", config_path),
        patch("builtins.input", _input_sequence(["1", "n"])),
        contextlib.redirect_stdout(out),
    ):
        setup_mode.run_setup(rediscover=False)
    rendered = out.getvalue()
    assert "Bridge skill installation skipped." in rendered
    assert "You can run `synkraken config --install-skills` later." in rendered
    assert not (tmp / "claude" / "skills" / "synkraken-bridge" / "SKILL.md").exists()
    assert config_path.exists()


def test_setup_prompts_for_remote_discovery(tmp: Path) -> None:
    runtime = {
        "runtime_id": "goose",
        "label": "Goose",
        "runtime_type": "goose",
        "command": ["/home/operator/.local/bin/goose"],
        "capabilities": ["coding"],
        "cost_tier": "medium",
        "adapter_type": "goose",
        "adapter_supported": True,
        "supported_modes": ["direct"],
        "timeout_seconds": 90,
        "remote_host": "agent-box.local",
        "remote_user": "operator",
        "remote_port": 2222,
        "ssh_identity_file": str(tmp / "synkraken_worker"),
        "remote_working_dir": "/workspace/project",
        "remote_path": ["/opt/agents/bin"],
        "ssh_options": ["-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes"],
    }
    config_path = tmp / "config.local.json"
    out = io.StringIO()
    with (
        patch("synkraken.setup_mode.discover_remote_runtimes", return_value=[runtime]) as remote_discover,
        patch("synkraken.setup_mode.DEFAULT_CONFIG_PATH", config_path),
        patch("builtins.input", _input_sequence([
            "2",
            "agent-box.local",
            "operator",
            "2222",
            str(tmp / "synkraken_worker"),
            "/workspace/project",
            "/opt/agents/bin",
            "",
            "1",
        ])),
        contextlib.redirect_stdout(out),
    ):
        setup_mode.run_setup(rediscover=False, prompt_discovery=True)

    rendered = out.getvalue()
    assert "Worker location" in rendered
    assert "Remote workers are ready to receive work over SSH." in rendered
    remote_discover.assert_called_once()
    kwargs = remote_discover.call_args.kwargs
    assert kwargs["remote_host"] == "agent-box.local"
    assert kwargs["remote_user"] == "operator"
    assert kwargs["remote_port"] == 2222
    assert kwargs["ssh_identity_file"] == str(tmp / "synkraken_worker")
    assert kwargs["remote_working_dir"] == "/workspace/project"
    assert kwargs["remote_path"] == ["/opt/agents/bin"]

    config = json.loads(config_path.read_text(encoding="utf-8"))
    goose = config["adapters"]["goose"]
    assert goose["remote_host"] == "agent-box.local"
    assert goose["ssh_identity_file"] == str(tmp / "synkraken_worker")
    assert goose["remote_path"] == ["/opt/agents/bin"]


def test_install_skills_command_from_existing_config(tmp: Path) -> None:
    config = {
        "adapters": {
            "claude": {
                "type": "claude",
                "runtime_type": "claude",
                "runtime_name": "Claude Code",
                "enabled": True,
                "command": ["claude"],
            }
        },
        "runtime_registry": {
            "codex": {
                "runtime_id": "codex",
                "runtime_type": "codex",
                "adapter_type": "unsupported",
                "enabled": False,
            }
        },
    }
    (tmp / "config.local.json").write_text(json.dumps(config), encoding="utf-8")
    env = os.environ.copy()
    env["HOME"] = str(tmp)
    env["PYTHONPATH"] = str(ROOT)
    output = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "config", "--install-skills"],
        cwd=tmp,
        env=env,
        text=True,
    )
    assert (tmp / ".claude" / "skills" / "synkraken-bridge" / "SKILL.md").exists()
    assert "✓ Claude Code" in output
    assert "installed at: ~/.claude/skills/synkraken-bridge" in output
    assert "- Codex" in output
    assert "skipped: bridge skill installer not implemented for this runtime yet" in output


def test_bridge_skill_install_failure_reports_failed(tmp: Path) -> None:
    runtime = {
        "runtime_id": "claude",
        "label": "Claude Code",
        "adapter_type": "claude",
        "adapter_supported": True,
        "skill_path": str(tmp / "claude" / "skills" / "synkraken-bridge"),
        "skill_format": "folder",
    }
    out = io.StringIO()
    with (
        patch("synkraken.setup_mode._copy_skill_folder", side_effect=RuntimeError("copy denied")),
        contextlib.redirect_stdout(out),
    ):
        results = setup_mode._install_bridge_skills_for_runtimes([runtime])
        setup_mode._print_bridge_skill_results(results)
    assert results == [{"status": "failed", "label": "Claude Code", "detail": "copy denied"}]
    rendered = out.getvalue()
    assert "✗ Claude Code" in rendered
    assert "failed: copy denied" in rendered


def test_setup_debug_line_output() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        setup_mode._debug_setup_line_output()
    assert out.getvalue() == "A\nB\nC\n"


def test_probe_restores_terminal_output_flags() -> None:
    import pty
    import termios

    master_fd, slave_fd = pty.openpty()
    saved_stdin, saved_stdout, saved_stderr = sys.stdin, sys.stdout, sys.stderr
    slave = os.fdopen(slave_fd, "r", buffering=1)
    try:
        sys.stdin = slave
        sys.stdout = slave
        sys.stderr = slave

        original_attrs = termios.tcgetattr(slave_fd)
        original_attrs[1] |= termios.ONLCR
        termios.tcsetattr(slave_fd, termios.TCSADRAIN, original_attrs)

        def _fake_run(*args, **kwargs):
            assert kwargs["stdin"] is subprocess.DEVNULL
            changed = termios.tcgetattr(slave_fd)
            changed[1] &= ~termios.ONLCR
            termios.tcsetattr(slave_fd, termios.TCSADRAIN, changed)
            return subprocess.CompletedProcess(args[0], 0, "ok\n", "")

        with patch("synkraken.discovery.subprocess.run", _fake_run):
            result = discovery._run_probe_command("fake-runtime", ("--version",), 2.0)

        restored_attrs = termios.tcgetattr(slave_fd)
        assert result.stdout == "ok\n"
        assert restored_attrs[1] & termios.ONLCR
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved_stdin, saved_stdout, saved_stderr
        slave.close()
        os.close(master_fd)


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        runtimes = test_fake_path_and_versions(tmp)
        test_selection_parser(runtimes)
        test_config_merge(runtimes)
    with tempfile.TemporaryDirectory() as raw:
        test_remote_discovery_preserves_ssh_config(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_fake_agy_detected(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_fake_ag_requires_antigravity_probe(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_cli_json_output(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_cli_formatting_with_long_command(Path(raw))
    test_config_numbered_prompt()
    with tempfile.TemporaryDirectory() as raw:
        test_selected_bridge_skill_install_and_skips(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_declined_bridge_skill_install_skips_cleanly(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_setup_prompts_for_remote_discovery(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_install_skills_command_from_existing_config(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_bridge_skill_install_failure_reports_failed(Path(raw))
    test_setup_debug_line_output()
    test_probe_restores_terminal_output_flags()
    print("runtime discovery smoke test passed")


if __name__ == "__main__":
    main()
