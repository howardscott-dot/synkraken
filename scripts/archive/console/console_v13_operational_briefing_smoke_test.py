#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "console" / "src" / "App.tsx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    source = APP.read_text(encoding="utf-8")

    require('"briefing"' in source and "BriefingView" in source and "Operational Briefing" in source, "briefing screen exists")
    require("recommendedNextActions" in source and "BriefingAction" in source and ".slice(0, 5)" in source, "recommendation engine exists")
    require("MissionHealth" in source and "missionHealth" in source and '"Healthy" | "Watching" | "At Risk"' in source, "mission health exists")
    require("OutcomeHealth" in source and "outcomeHealth" in source and '"On Track" | "Watching" | "Blocked"' in source, "outcome health exists")
    require("AssignmentHealth" in source and "assignmentHealth" in source and '"Assigned" | "In Progress" | "Waiting" | "Blocked"' in source, "assignment health exists")
    require('type CanvasNodeType = "workforce-summary" | "briefing"' in source, "briefing canvas node type exists")
    require('createNode("briefing"' in source and "BriefingNode" in source and "Open Briefing" in source, "briefing node exists")
    require('{ id: "briefing", label: "Briefing" }' in source, "briefing nav item exists")
    recommendation_body = source.split("function recommendedNextActions", 1)[1].split("function", 1)[0]
    require("api." not in recommendation_body and "fetch(" not in recommendation_body, "recommendations must be local deterministic rules")

    print("Console v1.3 Operational Briefing source smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
