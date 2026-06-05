from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(text: str, needles: list[str], label: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{label} missing: {', '.join(missing)}")


def _block_after(text: str, marker: str, length: int = 1200) -> str:
    index = text.find(marker)
    if index < 0:
        raise AssertionError(f"marker missing: {marker}")
    return text[index:index + length]


def main() -> None:
    app = _read("apps/console/src/App.tsx")
    styles = _read("apps/console/src/styles.css")
    ui_doctrine = _read("docs/UI_CONSOLE_DOCTRINE.md")
    product_doctrine = _read("docs/PRODUCT_DOCTRINE.md")

    _require(
        app,
        [
            'type DisplaySeverity = "Operational" | "Needs attention" | "Degraded" | "Blocked" | "Critical"',
            "function displaySeverityForRuntime",
            'if (rawHealth === "failing") return "Needs attention"',
            "function explainRuntimeIssue",
            "function suggestedRuntimeAction",
            "function displayImpactForIncident",
            "function summariseWorkforceState",
        ],
        "display severity mapping",
    )

    node_tone = _block_after(app, "function nodeTone", 900)
    _require(
        node_tone,
        [
            '["failing", "unstable", "degraded"].includes(health)',
            'return "degraded"',
        ],
        "raw failing is softened on canvas",
    )
    if 'health === "failing" || health === "unstable") return "failing"' in node_tone:
        raise AssertionError("raw failing still always renders as failing canvas tone")

    _require(
        app,
        [
            'type OperatorPriority = "Needs action now" | "Watch list" | "Historical / low impact"',
            '"Needs action now": []',
            '"Watch list": []',
            '"Historical / low impact": []',
            "function IncidentCard",
        ],
        "incident centre priority groups",
    )

    _require(
        app,
        [
            "function OperatorSummary",
            "AI Workforce Summary",
            "Incident Operator Summary",
            "highest priority",
            "suggested action",
            "Usable with issues",
        ],
        "operator summary",
    )

    _require(
        app,
        [
            "Empty replies detected.",
            "Identity mismatch in recent replies.",
            "Ignore if unused, or remove from rooms if noisy.",
            "Inspect latest trace or remove from active room.",
            "No active room dependency detected",
        ],
        "suggested action copy",
    )

    topbar = _block_after(app, "function TopBar", 2200)
    _require(
        topbar,
        [
            'StatusMetric label="Workforce"',
            "workforceState",
            "Usable with issues",
            'StatusMetric label="Active"',
            'StatusMetric label="Idle"',
            'StatusMetric label="Needs attention"',
            'StatusMetric label="Dead letters"',
        ],
        "human-friendly global status bar",
    )
    if 'label="failing"' in topbar or 'label="incidents"' in topbar:
        raise AssertionError("global status bar still uses scary failing/incidents labels")

    _require(
        app,
        [
            'Field label="raw health"',
            "Raw runtime data",
            "Raw incident data",
        ],
        "raw health remains accessible",
    )

    _require(
        app,
        [
            'daemonStatus === "offline"',
            'setDaemonStatus("offline")',
            "operator-summary-critical",
            "Daemon unavailable",
        ],
        "daemon offline remains critical",
    )
    _require(
        styles,
        [
            ".incident-card-critical",
            ".incident-card-watch",
            ".incident-card-muted",
            ".operator-summary-critical",
        ],
        "softened visual classes",
    )
    _require(
        product_doctrine + ui_doctrine,
        [
            "Calm Truth",
            "expose real failures without exaggerating",
            "Raw health must remain visible",
        ],
        "Calm Truth doctrine",
    )

    print("console operator friendly status smoke test: ok")


if __name__ == "__main__":
    main()
