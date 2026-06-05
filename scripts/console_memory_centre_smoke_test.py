#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app = read("apps/console/src/App.tsx")
    api = read("apps/console/src/lib/api.ts")

    require('{ id: "memory", label: "Memory" }' in app, "Memory nav item missing")
    require('type CanvasNodeType = "workforce-summary" | "briefing" | "runtime" | "room" | "mission" | "outcome" | "assignment" | "memory"' in app, "Memory canvas node type missing")
    for needle in (
        "Memory Centre",
        "Create Memory Note",
        "Memory Records",
        "Approved Memory",
        "MemoryScopePanel",
        "MemoryNode",
        "injected memory",
        "Open Memory Centre",
    ):
        require(needle in app, f"Console memory surface missing: {needle}")
    for needle in (
        "getMemory",
        "getMemoryContext",
        "createMemoryNote",
        "approveMemory",
        "rejectMemory",
        "archiveMemory",
        "WorkforceMemory",
    ):
        require(needle in api, f"Console memory API missing: {needle}")
    for scope in ("mission", "outcome", "assignment", "room", "runtime"):
        require(f'scopeType="{scope}"' in app, f"{scope} memory section missing")

    print("console memory centre smoke test passed")


if __name__ == "__main__":
    main()
