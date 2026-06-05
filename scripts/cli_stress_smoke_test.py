#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.cli_stress_test as stress


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return self.payload


def main() -> None:
    original_urlopen = stress.urlopen
    calls: list[tuple[str, int | None]] = []

    def fake_urlopen(url: object, timeout: int | None = None) -> _Response:
        calls.append((str(url), timeout))
        agents = [
            {
                "adapter_id": f"agent-{index}",
                "agent_id": f"agent-{index}",
                "runtime_name": f"Agent {index}",
                "type": "fake",
                "enabled": True,
                "status": "online",
            }
            for index in range(6)
        ]
        return _Response({"agents": agents})

    try:
        stress.urlopen = fake_urlopen
        agents = stress._enabled_agents("http://daemon")
    finally:
        stress.urlopen = original_urlopen

    assert len(agents) == 6, agents
    assert [agent["adapter_id"] for agent in agents] == [f"agent-{index}" for index in range(6)]
    assert calls == [("http://daemon/v1/agents", stress.DISCOVERY_TIMEOUT)], calls
    print("cli stress smoke test: ok")


if __name__ == "__main__":
    main()
