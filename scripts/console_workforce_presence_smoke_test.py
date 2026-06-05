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
    api = _read("apps/console/src/lib/api.ts")

    _require(
        api,
        [
            "export type PresenceState",
            "export type WorkforcePresenceWorker",
            "getWorkforcePresence",
            '"/v1/workforce/presence"',
            "getRecentActivity",
            "/v1/activity/recent?limit=",
        ],
        "console presence API bindings",
    )
    _require(
        app,
        [
            "function OperatorSummary",
            "Presence aware",
            "data.workforcePresence?.summary",
            "recentActivity",
            "Usable with issues",
        ],
        "Operator Activity Summary",
    )
    _require(
        app + styles,
        [
            "presenceLabel",
            "presenceClass",
            "presence-active",
            "presence-idle",
            "presence-watching",
            "presence-attention",
            "presence-unavailable",
        ],
        "presence chips/classes",
    )
    _require(
        app,
        [
            "Presence",
            "Last activity",
            "Current room",
            "Idle for",
            "Needs attention",
            "Suggested action",
            "raw health",
        ],
        "workforce presence table",
    )
    _require(
        app,
        [
            "function RuntimeNode",
            "presenceForWorker",
            "latest_activity_summary",
            "idle_for_seconds",
            "current_room",
            "suggested_action",
        ],
        "runtime nodes render presence",
    )
    _require(
        app + styles,
        [
            "activity-feed",
            "Activity Feed",
            "function ActivityFeedNode",
            "activity-feed-node",
            "activity-row",
        ],
        "Activity Feed",
    )
    _require(
        app,
        [
            "Needs action now",
            "Watch list",
            "Historical / low impact",
            "presence_state === \"active\"",
            "Used in #",
        ],
        "presence-aware incident framing",
    )
    _require(
        app,
        [
            "Show Active Workers",
            "Show Workers Needing Attention",
            "Focus Activity Feed",
            "Focus Worker:",
            "Focus Room:",
            "Open Presence Summary",
        ],
        "presence command palette commands",
    )
    _require(
        app,
        [
            'daemonStatus === "offline"',
            "operator-summary-critical",
            "status-danger",
            "Critical",
        ],
        "red remains reserved for daemon offline/blocked/critical",
    )

    if 'if (rawHealth === "failing") return "Critical"' in app:
        raise AssertionError("raw failing still always maps to Critical")
    if "incident-card-critical" not in styles or "presence-attention" not in styles:
        raise AssertionError("incident and presence styles missing")

    print("console workforce presence smoke test: ok")


if __name__ == "__main__":
    main()
