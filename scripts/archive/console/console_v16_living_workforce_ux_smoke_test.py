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
    position = -1
    for needle in needles:
        next_position = source.find(needle)
        require(next_position > position, f"{message}: {needle}")
        position = next_position


def main() -> None:
    app = read("apps/console/src/App.tsx")
    css = read("apps/console/src/styles.css")
    doctrine = read("docs/UI_CONSOLE_DOCTRINE.md")

    require_order(
        app,
        [
            '{ id: "home", label: "Home" }',
            '{ id: "conversations", label: "Conversations" }',
            '{ id: "work", label: "Work" }',
            '{ id: "knowledge", label: "Knowledge" }',
            '{ id: "workforce", label: "Workforce" }',
            '{ id: "governance", label: "Governance" }',
            '{ id: "search", label: "Search" }',
        ],
        "v1.6 navigation order missing",
    )
    require("Conversation first." in doctrine, "Conversation-first doctrine missing")
    require("What happened?" in app and "What needs me?" in app and "Recommended next action" in app, "Home must answer the briefing questions")
    require("workerBriefingLines" in app and "homeNeeds" in app, "Home briefing must be deterministic from daemon state")
    require("Conversations" in app and "conversation-drawer-stack" in app, "Rooms must be reframed as Conversations with drawers")
    require("knowledge-notes-grid" in app and "Company" in app and "Projects" in app and "Lessons Learned" in app, "Knowledge sections missing")
    require("ExperienceEmptyState" in app and "No active missions." in app and "Nothing is currently assigned." in app, "Educational empty states missing")
    require("worker-card-grid" in app and "Working in" in app and "Watch" in app and "Recommended action" in app, "Worker cards missing")
    require("governance-inbox" in app and "Awaiting Review" in app and "Executed Actions" in app, "Governance inbox missing")
    require("living-timeline" in app and 'data-timeline-first="true"' in app, "Activity must be timeline-first")
    require("function SearchView" in app and "spotlight-search" in app and "data-global-search" in app, "Global Search missing")
    require("canvas" not in app[app.find("const navItems"):app.find("const workspacePresets")], "Canvas must not be a primary nav item")
    require("conversation-drawer-stack" in css and "worker-card" in css and "spotlight-search" in css, "v1.6 layout classes missing")
    require("cyberpunk" not in f"{app}\n{css}".lower() and "neon" not in f"{app}\n{css}".lower(), "Forbidden visual terminology remains")

    print("console v1.6 living workforce ux smoke test passed")


if __name__ == "__main__":
    main()
