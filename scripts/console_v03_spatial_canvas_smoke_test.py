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
    api = _read("apps/console/src/lib/api.ts")
    styles = _read("apps/console/src/styles.css")
    prd = _read("docs/prds/2026-05-30-console-v0-3-spatial-operations-canvas.md")

    _require(
        app,
        [
            'type View = "canvas"',
            "Operations Canvas",
            "CanvasNodeType",
            '"workforce-summary" | "runtime" | "room" | "proposal-queue" | "proposal-detail" | "incident" | "trace" | "dead-letter"',
            "createPresetNodes",
            '"Coding", "Operations", "Research", "Incident Response"',
            "window.localStorage",
            "relationship-layer",
            "buildRelationships",
            "Open Operations Canvas",
            "Switch workspace: Coding",
            "Focus Runtime",
            "Focus Proposal",
            "Focus Trace",
        ],
        "operations canvas source",
    )
    _require(
        app,
        [
            '{ id: "canvas", label: "Canvas" }',
            '{ id: "workforce", label: "Workforce" }',
            '{ id: "rooms", label: "Rooms" }',
            '{ id: "proposals", label: "Proposals" }',
            '{ id: "flight", label: "Trace" }',
            '{ id: "incidents", label: "Incidents" }',
        ],
        "v0.2 route preservation",
    )
    _require(
        api,
        [
            '"/health"',
            '"/v1/agents"',
            '"/v1/workforce"',
            '"/v1/workforce/health"',
            '"/v1/rooms"',
            '"/v1/proposals/pending"',
            "`/v1/proposal/",
            "`/v1/trace/",
            "`/v1/replay/",
            '"/v1/incident/latest"',
            "`/v1/dead-letters?limit=",
        ],
        "daemon API usage",
    )
    _require(
        styles,
        [
            ".canvas-viewport",
            "background-size: 24px 24px",
            ".canvas-node-header",
            ".relationship-line",
            ".relationship-pending",
            ".relationship-failing",
        ],
        "canvas styling",
    )
    _require(
        prd,
        [
            "## Objective",
            "## Acceptance Criteria",
            "## Explicit Out Of Scope",
            "Business logic remains in the daemon and APIs; UI logic remains in React/TypeScript.",
        ],
        "PRD contract",
    )
    forbidden = ["stitch mock", "mockRuntime", "mockProposal", "mockDeadLetter"]
    found = [needle for needle in forbidden if needle in app]
    if found:
        raise AssertionError(f"production mock data found: {', '.join(found)}")
    print("console v0.3 spatial canvas smoke test: ok")


if __name__ == "__main__":
    main()
