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
    api = _read("apps/console/src/lib/api.ts")
    css = _read("apps/console/src/styles.css")
    prd = _read("docs/prds/2026-06-01-v11-workforce-assignment-and-handoffs.md")

    _require("## Acceptance Criteria" in prd and "## Out Of Scope" in prd, "PRD acceptance/out-of-scope sections missing")
    _require('{ id: "assignments", label: "Assignments" }' in app, "Assignments nav item missing")
    _require(app.index('{ id: "outcomes", label: "Outcomes" }') < app.index('{ id: "assignments", label: "Assignments" }') < app.index('{ id: "activity", label: "Activity" }'), "Assignments nav order incorrect")
    for needle in (
        "Assignment Centre",
        "My Workforce Assignments",
        "Create Assignment",
        "Assign Worker",
        "Add Contributor",
        "Mark Waiting",
        "Mark Blocked",
        "Request Review",
        "Complete Assignment",
        "Assignment Detail",
        "Current Assignment Count",
        "owned assignments",
        "contributor assignments",
        "assignments waiting",
        "assignments blocked",
        "assignments in review",
        "Current Assignments",
        "Blocked Assignments",
        "Mission Centre",
        "Outcome Centre",
    ):
        _require(needle in app, f"assignment console wiring missing: {needle}")
    for needle in (
        "Assignment",
        "AssignmentSummary",
        "HandoffRecord",
        "getAssignments",
        "getAssignmentSummary",
        "createAssignment",
        "updateAssignment",
        "addAssignmentContributor",
        "removeAssignmentContributor",
        "handoffAssignment",
        "getMissionAssignments",
        "getOutcomeAssignments",
        "getRoomAssignments",
        "getWorkerAssignments",
    ):
        _require(needle in api, f"assignment API client missing: {needle}")
    for needle in ("assignment-card", "handoff-timeline", "handoff-step"):
        _require(needle in css, f"assignment CSS missing: {needle}")

    print("console assignment centre smoke test passed")


if __name__ == "__main__":
    main()
