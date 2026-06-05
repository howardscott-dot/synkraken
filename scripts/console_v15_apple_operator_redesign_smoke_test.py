#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_order(source: str, needles: list[str], message: str) -> None:
    index = -1
    for needle in needles:
        next_index = source.find(needle)
        require(next_index > index, f"{message}: {needle}")
        index = next_index


def main() -> None:
    app = read("apps/console/src/App.tsx")
    css = read("apps/console/src/styles.css")
    tailwind = read("apps/console/tailwind.config.js")
    combined = f"{app}\n{css}\n{tailwind}".lower()

    require('const [view, setView] = useState<View>("home")' in app, "Home must be the default Console view")
    require_order(
        app,
        [
            '{ id: "home", label: "Home" }',
            '{ id: "rooms", label: "Rooms" }',
            '{ id: "work", label: "Work" }',
            '{ id: "memory", label: "Memory" }',
            '{ id: "activity", label: "Activity" }',
            '{ id: "workforce", label: "Workforce" }',
            '{ id: "governance", label: "Governance" }',
            '{ id: "incidents", label: "Incidents" }',
            '{ id: "canvas", label: "Canvas" }',
            '{ id: "settings", label: "Settings" }',
        ],
        "New operator-first navigation order missing",
    )

    for needle in ("function HomeView", "Today", "Recommended", "Active work", "Workers to monitor"):
        require(needle in app, f"Home operator briefing missing: {needle}")

    for needle in ("function WorkView", '"missions" | "outcomes" | "assignments"', "MissionsView", "OutcomesView", "AssignmentsView"):
        require(needle in app, f"Work area does not combine work objects: {needle}")

    for needle in (
        "Workforce Memory",
        "What the workforce remembers.",
        "Teach Workforce",
        "What should the workforce remember?",
        "Important rules",
        "Room context",
        "Mission context",
        "Worker notes",
        "Pending review",
        "Archived",
    ):
        require(needle in app, f"Memory screen language/grouping missing: {needle}")

    for needle in ("rooms-layout", "room-chat-transcript", "room-chat-composer", "data-sticky-composer", "Use @everyone or @worker-id"):
        require(needle in app, f"Rooms chat-first layout missing: {needle}")
    require(".room-chat-transcript" in css and ("overflow-auto" in css or "overflow-y: auto" in css), "Room transcript must be scroll-safe")
    require(".room-chat-composer" in css and ("position: sticky" in css or "bottom: 0" in css), "Room composer must remain usable at bottom")

    for needle in ("Available", "Monitor", "Avoid for now", "Unavailable", "Safe for normal work.", "May block or miss replies"):
        require(needle in app, f"Workforce operator category/copy missing: {needle}")

    for needle in ("function GovernanceView", "What needs approval?", "Recent handoffs", "Recent decisions", "Executed proposals"):
        require(needle in app, f"Governance screen missing: {needle}")

    require("Advanced Canvas" in app, "Canvas must be framed as advanced mode")
    require('setView("canvas")' in app and 'useState<View>("home")' in app, "Canvas must exist without being default")

    for needle in ("--apple-bg", "--apple-surface", "--apple-blue", "--apple-red", "#2997ff", "-apple-system", "BlinkMacSystemFont"):
        require(needle in css or needle in tailwind, f"Apple-style visual token missing: {needle}")
    require("border-radius: 24px" in css or "border-radius: 22px" in css, "Premium rounded surface styling missing")

    require("cyberpunk" not in combined, "Cyberpunk terminology should not remain in Console sources")
    require("neon" not in combined, "Neon terminology should not remain in Console sources")

    require("<details" in app and "raw-details" in app, "Raw technical fields should be behind details")
    require("function CanvasInspector" in app, "Contextual inspector must remain available for details")

    print("console v1.5 apple operator redesign smoke test passed")


if __name__ == "__main__":
    main()
