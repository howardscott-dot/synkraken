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
    prd = _read("docs/prds/2026-05-29-console-v0-2-operator-command-centre.md")

    _require(
        app,
        [
            "Workforce Command Centre",
            "Runtime Operations Table",
            "Rooms",
            "Flight Recorder",
            "Proposal Governance",
            "Proposal Detail",
            "Incident Centre",
            "Command Palette",
            "live polling 4s",
        ],
        "console screens",
    )
    _require(
        app,
        [
            '"health", "trust", "latency", "incidents"',
            "Broadcast To Room",
            "Raw replay data",
            "Raw proposal data",
            "Raw incident data",
        ],
        "operator interactions",
    )
    _require(
        api,
        [
            '"/v1/rooms"',
            '"/v1/messages"',
            '"/v1/proposals/pending"',
            '"/v1/proposal/approve"',
            '"/v1/proposal/reject"',
            '"/v1/proposal/execute"',
            "`/v1/replay/",
            '"/v1/incident/latest"',
            "`/v1/dead-letters?limit=",
        ],
        "daemon API client",
    )
    _require(
        prd,
        [
            "## Objective",
            "## Acceptance Criteria",
            "## Explicit Out Of Scope",
            "## Completion Update",
        ],
        "PRD contract",
    )
    print("console v0.2 smoke test: ok")


if __name__ == "__main__":
    main()
