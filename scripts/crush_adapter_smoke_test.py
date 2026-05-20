#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters.crush import CrushAdapter
from synkraken.discovery import (
    _find_node_bin,
    _nvm_node_bin_dirs,
    discover_local_runtimes,
    merge_discovered_config,
)
from synkraken.fabric import AgentFabric
from synkraken.models import FabricMessage
from synkraken.storage import Storage


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_node_dir = tmp_path / "node_bin"
        fake_node_dir.mkdir()
        fake_crush = tmp_path / "crush"

        config_with_node = {
            "type": "crush",
            "command": [str(fake_crush)],
            "timeout_seconds": 2,
            "node_bin_dir": str(fake_node_dir),
        }
        adapter_with_node = CrushAdapter("crush", config_with_node)

        built_env = adapter_with_node._build_env()
        assert "PATH" in built_env
        path_entries = built_env["PATH"].split(os.pathsep)
        node_in_path = any(str(fake_node_dir) in p for p in path_entries)
        assert node_in_path, f"fake_node_dir not in PATH: {path_entries[:5]}"

        config_without_node = {
            "type": "crush",
            "command": [str(fake_crush)],
            "timeout_seconds": 2,
        }
        adapter_without_node = CrushAdapter("crush", config_without_node)
        built_env2 = adapter_without_node._build_env()
        assert "PATH" in built_env2

        fake_node_script = fake_node_dir / "node"
        fake_node_script.write_text("#!/bin/sh\necho fake-node-v99\n", encoding="utf-8")
        fake_node_script.chmod(0o755 | stat.S_IXUSR)

        node_path, node_bin = _find_node_bin(tmp, [fake_node_dir])
        assert node_path is not None, "_find_node_bin should find node in extra_dirs"
        assert node_bin == str(fake_node_dir)

        fake_crush.write_text("#!/bin/sh\necho crush-ok\n", encoding="utf-8")
        fake_crush.chmod(0o755 | stat.S_IXUSR)

        fake_crush_env = os.environ.copy()
        fake_crush_env["PATH"] = str(fake_node_dir) + os.pathsep + fake_crush_env.get("PATH", "")
        r = subprocess.run(
            [str(fake_crush)],
            capture_output=True, text=True, env=fake_crush_env, timeout=5
        )
        assert r.returncode == 0, f"fake crush failed: {r.stderr}"
        assert "crush-ok" in r.stdout

        nvm_dirs = _nvm_node_bin_dirs(tmp_path)
        assert isinstance(nvm_dirs, list)

        fake_nvm_dir = tmp_path / ".nvm" / "versions" / "node"
        fake_nvm_dir.mkdir(parents=True)
        nvm_node = fake_nvm_dir / "v99.88.77" / "bin" / "node"
        nvm_node.parent.mkdir(parents=True)
        nvm_node.write_text("#!/bin/sh\necho nvm-node-v99\n", encoding="utf-8")
        nvm_node.chmod(0o755 | stat.S_IXUSR)

        found_nvm_dirs = _nvm_node_bin_dirs(tmp_path)
        assert any("v99.88.77" in str(d) for d in found_nvm_dirs), \
            f"Expected v99.88.77 in nvm dirs, got: {found_nvm_dirs}"

        fake_crush_with_env = fake_nvm_dir / "crush"
        fake_crush_with_env.write_text("#!/bin/sh\necho crush-nvm-ok\n", encoding="utf-8")
        fake_crush_with_env.chmod(0o755 | stat.S_IXUSR)
        fake_nvm_bin_dir = str(fake_nvm_dir / "v99.88.77" / "bin")
        config_nvm = {
            "type": "crush",
            "command": [str(fake_crush_with_env)],
            "timeout_seconds": 2,
            "node_bin_dir": fake_nvm_bin_dir,
        }
        adapter_nvm = CrushAdapter("crush", config_nvm)
        nvm_built_env = adapter_nvm._build_env()
        nvm_path_entries = nvm_built_env["PATH"].split(os.pathsep)
        nvm_in_path = any("v99.88.77" in p for p in nvm_path_entries)
        assert nvm_in_path, f"nvm v99.88.77 not in PATH: {nvm_path_entries[:5]}"

        prompt_boundary = adapter_with_node._prompt_boundary("Reply with exactly: XYZ")
        assert "If the user asks for exact output, return only that exact output" in prompt_boundary
        assert "<<<\n" in prompt_boundary
        assert "\n>>>" in prompt_boundary

        discovered = discover_local_runtimes(
            search_path=tmp, home=tmp_path, include_common_dirs=False
        )
        by_id = {r["runtime_id"]: r for r in discovered}
        assert "crush" in by_id, f"Expected crush in discovered: {list(by_id.keys())}"
        rt = by_id["crush"]
        assert rt["adapter_supported"] is True
        assert rt["adapter_type"] == "crush"

        merged, summary = merge_discovered_config(
            {"adapters": {}, "runtime_registry": {}}, [rt], behaviour="merge"
        )
        assert "crush" in merged["adapters"]
        assert merged["adapters"]["crush"]["type"] == "crush"
        assert merged["adapters"]["crush"]["enabled"] is True
        assert "crush" in summary["adapters_added"]

        fake_crush_js = tmp_path / "crush_js"
        fake_crush_js.write_text("#!/bin/sh\necho crush-js-ok\n", encoding="utf-8")
        fake_crush_js.chmod(0o755 | stat.S_IXUSR)
        config_for_discovery = {
            "type": "crush",
            "command": [str(fake_crush_js)],
            "timeout_seconds": 2,
            "node_bin_dir": str(fake_node_dir),
        }
        config_for_fabric = {
            "adapters": {
                "crush": config_for_discovery
            },
            "runtime_registry": {
                "crush": {
                    "runtime_id": "crush",
                    "runtime_type": "crush",
                    "command": [str(fake_crush_js)],
                    "capabilities": ["coding"],
                    "cost_tier": "local",
                    "adapter_type": "crush",
                    "supported_modes": ["direct"],
                    "enabled": True,
                    "node_bin_dir": str(fake_node_dir),
                }
            },
        }
        storage = Storage(tmp_path / "test_db.sqlite3")
        fabric = AgentFabric(config_for_fabric, storage)
        storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
        fabric._sync_runtime_registry()

        doctor = fabric.runtime_doctor()
        rt_doc = next((r for r in doctor["runtimes"] if r["runtime_id"] == "crush"), None)
        assert rt_doc is not None, "crush not in doctor"
        assert rt_doc["registered"] is True
        assert rt_doc["ok"] is True
        assert rt_doc["health"]["type"] == "crush"
        assert rt_doc["health"]["enabled"] is True

    print("crush_adapter_smoke_test: PASS")


if __name__ == "__main__":
    main()