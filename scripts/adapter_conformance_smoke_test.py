#!/usr/bin/env python3
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters import ADAPTER_TYPES, build_adapter
from synkraken.adapters.base import BaseAdapter


def main() -> None:
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
