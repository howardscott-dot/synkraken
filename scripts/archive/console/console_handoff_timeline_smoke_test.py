from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app = _read("apps/console/src/App.tsx")
    storage = _read("synkraken/storage.py")
    api = _read("synkraken/api.py")

    for needle in (
        "Handoff Timeline",
        "handoff-timeline",
        "handoff-step",
        "Recent Handoffs",
        "Focus Assignment",
        "View Handoffs",
        'type === "assignment"',
        "AssignmentNode",
        'value="assignment"',
        "Open Assignment Centre",
    ):
        _require(needle in app, f"handoff timeline or canvas wiring missing: {needle}")
    for needle in (
        '"has_assignment"',
        '"contributes_assignment"',
        '"owned_by"',
        '"assisted_by"',
        "create_assignment_handoff",
        "recent_assignment_handoffs",
    ):
        _require(needle in storage, f"assignment canvas/handoff storage missing: {needle}")
    for needle in (
        '"/v1/handoffs/recent"',
        '"/v1/assignments/([^/]+)/handoff"',
        '"/v1/assignments/([^/]+)/handoffs"',
    ):
        _require(needle in api, f"handoff API route missing: {needle}")

    print("console handoff timeline smoke test passed")


if __name__ == "__main__":
    main()
