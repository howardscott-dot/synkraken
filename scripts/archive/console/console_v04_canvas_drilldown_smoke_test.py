from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(text: str, needles: list[str], label: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{label} missing: {', '.join(missing)}")


def main() -> None:
    app = _read("apps/console/src/App.tsx")
    styles = _read("apps/console/src/styles.css")
    prd = _read("docs/prds/2026-05-30-console-v0-4-canvas-drilldown-and-focus.md")

    _require(
        app,
        [
            "CanvasInspector",
            "inferCanvasTarget",
            "focusOrCreateNode",
            "canvas-focus-input",
            "canvas-add-select",
            "Clear Saved",
            "Clear Saved Layout",
            "Add Runtime Node",
            "Add Room Node",
            "Add Proposal Detail Node",
            "Add Dead Letter Node",
            "Focus Room",
            "node type",
            "relationships",
        ],
        "v0.4 canvas drilldown source",
    )
    _require(
        app,
        [
            "RelationshipJumpRow",
            "target_type",
            "target_id",
            'onView("workforce")',
            'onView("rooms")',
            'onView("proposals")',
            'onView("incidents")',
        ],
        "inspector object actions",
    )
    _require(
        styles,
        [
            ".canvas-main",
            ".canvas-inspector",
            ".canvas-inspector-title",
            ".canvas-inspector-section",
            ".canvas-focus-input",
            ".canvas-add-select",
        ],
        "inspector styling",
    )
    _require(
        prd,
        [
            "## Objective",
            "## Acceptance Criteria",
            "Canvas Inspector",
            "No Rust business logic is added.",
            "## Explicit Out Of Scope",
        ],
        "v0.4 PRD contract",
    )
    forbidden = ["mockRuntime", "mockProposal", "mockDeadLetter", "stitch mock"]
    found = [needle for needle in forbidden if needle in app]
    if found:
        raise AssertionError(f"production mock data found: {', '.join(found)}")
    print("console v0.4 canvas drilldown smoke test: ok")


if __name__ == "__main__":
    main()
