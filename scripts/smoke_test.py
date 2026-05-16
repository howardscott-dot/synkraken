#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.request


BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9460"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


if __name__ == "__main__":
    print("# health")
    print(json.dumps(get_json(f"{BASE}/health"), indent=2))
    print("\n# agents")
    print(json.dumps(get_json(f"{BASE}/v1/agents"), indent=2))
    print("\n# broadcast")
    payload = {
        "source": "smoke-test",
        "target": "broadcast",
        "body": "Reply with exactly one line in the format ADAPTER_OK: <your runtime name>. No extra text."
    }
    result = post_json(f"{BASE}/v1/messages", payload)
    print(json.dumps(result, indent=2))
