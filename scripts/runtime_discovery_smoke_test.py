#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synkraken.discovery import (  # noqa: E402
    discover_local_runtimes,
    merge_discovered_config,
    parse_runtime_selection,
)


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
    selected = parse_runtime_selection(runtimes, "1,ollama")
    assert [runtime["runtime_id"] for runtime in selected] == ["claude", "ollama"]
    supported = parse_runtime_selection(runtimes, "all", supported_only=True)
    assert {runtime["runtime_id"] for runtime in supported} == {"claude", "goose"}


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
    long_version = "goose " + ("version-segment-" * 12)
    _fake_binary(long_dir, "goose", long_version)
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
    assert lines[0].startswith("Runtime"), plain
    assert "Command" in lines[0], plain
    assert lines[1].startswith("─"), plain
    runtime_line = next(line for line in lines if line.startswith("Goose"))
    version_line = next(line for line in lines if line.strip().startswith("version:"))
    assert "..." in runtime_line, plain
    assert str(long_dir / "goose") not in runtime_line, plain
    assert len(runtime_line) <= 80, plain
    assert len(version_line) <= 80, plain

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

    verbose = subprocess.check_output(
        [sys.executable, "-m", "synkraken.cli_main", "discover", "--verbose"],
        cwd=ROOT,
        env=env,
        text=True,
    )
    assert str(long_dir / "goose") in verbose
    assert f"probe: {long_version}" in verbose


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        runtimes = test_fake_path_and_versions(tmp)
        test_selection_parser(runtimes)
        test_config_merge(runtimes)
    with tempfile.TemporaryDirectory() as raw:
        test_fake_agy_detected(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_fake_ag_requires_antigravity_probe(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_cli_json_output(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_cli_formatting_with_long_command(Path(raw))
    print("runtime discovery smoke test passed")


if __name__ == "__main__":
    main()
