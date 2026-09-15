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
    prd = read("docs/prds/2026-06-02-v20-project-centric-company-os.md")

    require_order(
        app,
        [
            '{ id: "home", label: "Home" }',
            '{ id: "projects", label: "Projects" }',
            '{ id: "conversations", label: "Conversations" }',
            '{ id: "knowledge", label: "Knowledge" }',
            '{ id: "workforce", label: "Workforce" }',
            '{ id: "advanced", label: "Advanced" }',
        ],
        "v2.0 primary navigation missing",
    )
    require("ProjectRecord" in app and "deriveProjects" in app and "projectStorageKey" in app, "Project model missing")
    require("createProject" in app and "api.createRoom" in app, "Project creation must create a project conversation")
    for tab in ("overview", "conversations", "knowledge", "deliverables", "team", "decisions"):
        require(f'"{tab}"' in app, f"Project tab missing: {tab}")
    require("ProjectOverview" in app and "ProjectConversations" in app and "ProjectKnowledge" in app, "Project workspace surfaces missing")
    require("ProjectDeliverables" in app and "PRD, Research, Proposal, Architecture, Code Review, Article, Specification, Report" in app, "Deliverables surface missing")
    require("ProjectDecisions" in app and "Needs a decision" in app and "Approved" in app and "Rejected" in app and "decisionTitle" in app, "Decisions surface missing")
    require("Project Narrative" in app and "projectCurrentFocus" in app and "projectRecommendedAction" in app, "Project narrative missing")
    require("projectActivitySentence" in app and "Activity timeline" in app, "Human-readable project activity missing")
    require("project-note-editor" in css and "Save Knowledge" in app and "Revise" in app, "Inline project knowledge editing missing")
    require("AdvancedView" in app and "Governance, Assignments, Outcomes, Missions, Traces, Canvas, Incidents, Runtime Diagnostics, Proposal Internals, Dead Letters, Memory Internals" in app, "Advanced mapping missing")
    require("Company Briefing" in prd and "Company Operating System" in prd, "v2.0 PRD framing missing")
    require("project-workspace" in css and "deliverable-card" in css and "advanced-card" in css, "v2.0 project styles missing")
    nav_slice = app[app.find("const navItems"):app.find("const workspacePresets")]
    for hidden in ("governance", "search", "work", "activity", "canvas", "settings"):
        require(f'label: "{hidden.title()}"' not in nav_slice, f"{hidden} should not be primary nav")
    print("console v2.0 project company os smoke test passed")


if __name__ == "__main__":
    main()
