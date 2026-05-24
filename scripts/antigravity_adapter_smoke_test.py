#!/usr/bin/env python3
from __future__ import annotations

import stat
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters.antigravity import AntigravityAdapter
from synkraken.discovery import discover_local_runtimes, merge_discovered_config
from synkraken.fabric import AgentFabric
from synkraken.models import FabricMessage
from synkraken.storage import Storage


def create_fake_agy(tmp_dir: Path) -> Path:
    bin_path = tmp_dir / "agy"
    content = """#!/usr/bin/env python3
import sys
import time

args = sys.argv[1:]
if "--print" in args:
    idx = args.index("--print")
    if "--dangerously-skip-permissions" not in args:
        print("Error: missing --dangerously-skip-permissions", file=sys.stderr)
        sys.exit(2)
    # The prompt is the last argument or follows --print
    prompt = args[-1]
    if "TRIGGER_FAILURE" in prompt:
        print("Mock stderr failure", file=sys.stderr)
        sys.exit(1)
    elif "TRIGGER_TIMEOUT" in prompt:
        time.sleep(5)
        print("Late output after timeout")
        sys.exit(0)
    else:
        print(f"MOCK_RESPONSE: {prompt}")
        sys.exit(0)
else:
    print("Google Antigravity mock 1.0.0")
    sys.exit(0)
"""
    bin_path.write_text(content, encoding="utf-8")
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IXUSR)
    return bin_path


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_agy = create_fake_agy(tmp_path)

        # 1. Test Adapter Prompt Delivery - Success
        config = {
            "type": "google_antigravity",
            "command": [str(fake_agy)],
            "timeout_seconds": 2,
        }
        adapter = AntigravityAdapter("google-antigravity", config)

        msg = FabricMessage(
            source="operator",
            target="google-antigravity",
            body="Hello world",
            conversation_id="conv-1",
        )
        reply = adapter.send(msg)
        assert reply.ok is True, f"Expected successful reply, got: {reply}"
        assert "MOCK_RESPONSE: Hello world" in reply.body
        assert reply.duration_ms is not None and reply.duration_ms > 0

        # 2. Test Adapter Prompt Delivery - Failure (non-zero exit)
        msg_fail = FabricMessage(
            source="operator",
            target="google-antigravity",
            body="TRIGGER_FAILURE",
            conversation_id="conv-1",
        )
        reply_fail = adapter.send(msg_fail)
        assert reply_fail.ok is False
        assert "Mock stderr failure" in reply_fail.body or (reply_fail.error and "Mock stderr failure" in reply_fail.error)

        # 3. Test Adapter Prompt Delivery - Timeout
        config_timeout = {
            "type": "google_antigravity",
            "command": [str(fake_agy)],
            "timeout_seconds": 1,
        }
        adapter_timeout = AntigravityAdapter("google-antigravity", config_timeout)
        msg_timeout = FabricMessage(
            source="operator",
            target="google-antigravity",
            body="TRIGGER_TIMEOUT",
            conversation_id="conv-1",
        )
        reply_timeout = adapter_timeout.send(msg_timeout)
        assert reply_timeout.ok is False
        assert reply_timeout.error is not None
        assert "timed out" in reply_timeout.error.lower()

        # 4. Test Discovery
        discovered = discover_local_runtimes(search_path=tmp, home=tmp_path, include_common_dirs=False)
        by_id = {r["runtime_id"]: r for r in discovered}
        assert "google-antigravity" in by_id
        rt = by_id["google-antigravity"]
        assert rt["adapter_supported"] is True
        assert rt["adapter_type"] == "google_antigravity"

        # 5. Test Config Merge
        existing_config = {
            "adapters": {},
            "runtime_registry": {}
        }
        merged, summary = merge_discovered_config(existing_config, [rt], behaviour="merge")
        assert "google-antigravity" in merged["adapters"]
        assert merged["adapters"]["google-antigravity"]["type"] == "google_antigravity"
        assert merged["adapters"]["google-antigravity"]["enabled"] is True
        assert "google-antigravity" in merged["runtime_registry"]
        assert merged["runtime_registry"]["google-antigravity"]["enabled"] is True
        assert "google-antigravity" in summary["adapters_added"]

        # 6. Test Runtime Doctor
        storage = Storage(tmp_path / "test_db.sqlite3")
        fabric = AgentFabric(merged, storage)
        storage.sync_agents([adapter.health() for adapter in fabric.adapters.values()])
        fabric._sync_runtime_registry()

        doctor = fabric.runtime_doctor()
        rt_doc = None
        for item in doctor["runtimes"]:
            if item["runtime_id"] == "google-antigravity":
                rt_doc = item
                break
        assert rt_doc is not None
        assert rt_doc["registered"] is True
        assert rt_doc["ok"] is True
        assert rt_doc["health"]["type"] == "google_antigravity"
        assert rt_doc["health"]["enabled"] is True

    print("antigravity adapter smoke test: ok")


if __name__ == "__main__":
    main()
