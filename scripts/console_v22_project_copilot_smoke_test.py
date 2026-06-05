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
    css = read("apps/console/src/styles.css")
    prd = read("docs/prds/2026-06-04-v22-project-copilot.md")
    app_lower = app.lower()
    prd_lower = prd.lower()

    require("ProjectCoPilot" in app and "Project Co-Pilot" in app, "Project Co-Pilot surface missing")
    require("projectRecommendations" in app and "Recommended next actions" in app, "Recommended project actions missing")
    require("ProjectInboxItem" in app and "Inbox" in app and "projectInbox" in app, "Project Inbox missing")
    require("type ProjectHealth" in app and "projectHealth" in app and "Healthy" in app and "Needs Review" in app and "Blocked" in app, "Project health model missing")
    require("Open action" in app and "deliverableActionLabel" in app and "Review" in app, "Deliverables must expose open actions")
    require("Current contribution" in app and "Last activity" in app and "Suggested use" in app, "Team contribution context missing")
    require("Project recommendations" in app and "projectBriefingLines" in app and "projectHealth(project, data)" in app, "Home project recommendations missing")
    require("Why:" in app and "Suggested Action:" in app and "human-readable" in prd_lower, "Human-readable action language missing")
    require("no ai generation" in app_lower and "no ai generation" in prd_lower and "llm calls" in prd_lower, "Co-Pilot must not require AI generation")
    require("project-copilot" in css and "project-action-card" in css and "project-inbox-item" in css, "Co-Pilot styles missing")
    require("new backend entities" in prd and "Out of scope" in prd, "v2.2 scope guard missing")

    print("console v2.2 project copilot smoke test passed")


if __name__ == "__main__":
    main()
