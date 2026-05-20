#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters.crush import CrushAdapter
from synkraken.discovery import discover_local_runtimes, merge_discovered_config
from synkraken.fabric import AgentFabric
from synkraken.models import FabricMessage
from synkraken.storage import Storage


_FAKE_CRUSH_SCRIPT = """\
#!/usr/bin/env python3
import sys

args = sys.argv[1:]

if "run" not in args:
    print("Crush mock 1.0.0")
    sys.exit(0)

prompt = ""
done = False
for i, arg in enumerate(args):
    if arg == "--":
        prompt = args[i+1]
        done = True
        break

if not done:
    for arg in args:
        if not arg.startswith("-") and arg != "run" and arg != "--quiet":
            prompt = arg
            break

prompt = prompt.strip()

if "TRIGGER_FAILURE" in prompt:
    print("Mock stderr failure", file=sys.stderr)
    sys.exit(1)
elif "TRIGGER_TIMEOUT" in prompt:
    import time
    time.sleep(5)
    print("Late output after timeout")
    sys.exit(0)
else:
    inner = prompt
    marker = "<<<"
    if marker in prompt:
        idx = prompt.find(marker)
        rest = prompt[idx + 3:]
        end_idx = rest.find(">>>")
        if end_idx != -1:
            inner = rest[:end_idx].strip()
    print("MOCK_RESPONSE: " + inner)
    sys.exit(0)
"""


def create_fake_crush(tmp_dir: Path) -> Path:
    bin_path = tmp_dir / "crush"
    bin_path.write_text(_FAKE_CRUSH_SCRIPT, encoding="utf-8")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR)
    return bin_path


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_crush = create_fake_crush(tmp_path)

        config = {
            "type": "crush",
            "command": [str(fake_crush)],
            "timeout_seconds": 2,
        }
        adapter = CrushAdapter("crush", config)

        msg = FabricMessage(
            source="operator",
            target="crush",
            body="Hello world",
            conversation_id="conv-1",
        )
        reply = adapter.send(msg)
        assert reply.ok is True, f"Expected successful reply, got: {reply}"
        assert "MOCK_RESPONSE: Hello world" in reply.body, f"Got: {reply.body!r}"
        assert reply.duration_ms is not None and reply.duration_ms > 0

        cmd_arg = reply.raw.get("command", [])
        cmd_str = cmd_arg[-1] if cmd_arg else ""
        assert "<<<\n" in cmd_str, f"Boundary missing from command: {cmd_str[:100]}"
        assert "You are receiving a direct message from SynKraken" in cmd_str, \
            f"SynKraken instruction missing from command: {cmd_str[:100]}"
        assert "Respond only to the user message below" in cmd_str, \
            f"Response instruction missing from command: {cmd_str[:100]}"

        msg_fail = FabricMessage(
            source="operator",
            target="crush",
            body="TRIGGER_FAILURE",
            conversation_id="conv-1",
        )
        reply_fail = adapter.send(msg_fail)
        assert reply_fail.ok is False
        assert "Mock stderr failure" in (reply_fail.error or "") or \
               "Mock stderr failure" in reply_fail.body

        config_timeout = {
            "type": "crush",
            "command": [str(fake_crush)],
            "timeout_seconds": 1,
        }
        adapter_timeout = CrushAdapter("crush", config_timeout)
        msg_timeout = FabricMessage(
            source="operator",
            target="crush",
            body="TRIGGER_TIMEOUT",
            conversation_id="conv-1",
        )
        reply_timeout = adapter_timeout.send(msg_timeout)
        assert reply_timeout.ok is False
        assert reply_timeout.error is not None
        assert "timed out" in reply_timeout.error.lower()

        discovered = discover_local_runtimes(search_path=tmp, home=tmp_path, include_common_dirs=False)
        by_id = {r["runtime_id"]: r for r in discovered}
        assert "crush" in by_id, f"Expected crush in discovered runtimes, got: {list(by_id.keys())}"
        rt = by_id["crush"]
        assert rt["adapter_supported"] is True, f"Expected adapter_supported=True for crush, got: {rt}"
        assert rt["adapter_type"] == "crush"

        existing_config = {
            "adapters": {},
            "runtime_registry": {}
        }
        merged, summary = merge_discovered_config(existing_config, [rt], behaviour="merge")
        assert "crush" in merged["adapters"], f"Expected crush in adapters, got: {list(merged['adapters'].keys())}"
        assert merged["adapters"]["crush"]["type"] == "crush"
        assert merged["adapters"]["crush"]["enabled"] is True
        assert "crush" in merged["runtime_registry"]
        assert merged["runtime_registry"]["crush"]["enabled"] is True
        assert "crush" in summary["adapters_added"]

        storage = Storage(tmp_path / "test_db.sqlite3")
        fabric = AgentFabric(merged, storage)
        storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
        fabric._sync_runtime_registry()

        doctor = fabric.runtime_doctor()
        rt_doc = None
        for item in doctor["runtimes"]:
            if item["runtime_id"] == "crush":
                rt_doc = item
                break
        assert rt_doc is not None, f"Expected crush in runtime doctor, got: {[r['runtime_id'] for r in doctor['runtimes']]}"
        assert rt_doc["registered"] is True
        assert rt_doc["ok"] is True
        assert rt_doc["health"]["type"] == "crush"
        assert rt_doc["health"]["enabled"] is True

        alt_home = tmp_path / "home"
        alt_home.mkdir()
        config_with_home = {
            "type": "crush",
            "command": [str(fake_crush)],
            "timeout_seconds": 2,
            "working_dir": str(alt_home),
        }
        adapter_alt = CrushAdapter("crush", config_with_home)
        msg2 = FabricMessage(source="operator", target="crush", body="pwd check", conversation_id="c2")
        reply2 = adapter_alt.send(msg2)
        assert reply2.ok is True

        prompt_boundary = adapter._prompt_boundary("Reply with exactly: XYZ")
        assert "If the user asks for exact output, return only that exact output" in prompt_boundary
        assert "<<<\n" in prompt_boundary
        assert "\n>>>" in prompt_boundary

    print("crush_adapter_smoke_test: PASS")


if __name__ == "__main__":
    main()