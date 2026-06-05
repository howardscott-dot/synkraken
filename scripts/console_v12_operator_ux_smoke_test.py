#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "console" / "src" / "App.tsx"
CSS = ROOT / "apps" / "console" / "src" / "styles.css"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    app = APP.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    require("rooms-layout" in app and ".rooms-layout" in css and "h-[calc(100vh-154px)]" in css, "Rooms must use a fixed-height three-column layout.")
    require('data-fixed-height="room-transcript-scroll"' in app and ".room-chat-transcript" in css and "overflow-auto" in css, "Room transcript must have an independent scroll container.")
    require('data-sticky-composer="true"' in app and ".room-chat-composer" in css and "sticky bottom-0" in css, "Room composer must stay visible.")
    require('data-independent-scroll="members"' in app and ".room-member-list" in css and "flex-1" in css and "overflow-auto" in css, "Members list must scroll independently.")

    for label in ["Available", "Monitor", "Avoid for now", "Unavailable"]:
        require(label in app, f"Missing workforce display category: {label}")

    require("Recommended action" in app and "operatorWorkerImpact" in app and "suggestedRuntimeAction" in app, "Worker rows must include recommended action and impact copy.")
    require("targets" in app and "replied" in app and "empty reply" in app and "failed" in app and "deliverySummary" in app, "Delivery summary rendering must include target/reply/empty/failure counts.")
    require("Use @everyone or @worker-id to dispatch. Plain text records a room note." in app, "Composer hint text is missing.")
    require("max-h-48" in css and "overflow-auto" in css and "resize-none" in css, "Composer must constrain large pasted text.")
    require("raw health" in app and "Raw runtime data" in app and "Raw details" in app, "Raw technical health and delivery details must remain accessible.")

    red_tokens = [line.strip() for line in css.splitlines() if "danger" in line or "#ff5252" in line]
    allowed_markers = ("btn-danger", "status-danger", "operator-summary-critical", "incident-card-critical", "relationship-failing", "canvas-node-failing", "canvas-node-error", "timeline-incident", "text-danger", "border-danger", "bg-danger", "danger:", "#ff5252")
    unexpected = [line for line in red_tokens if not any(marker in line for marker in allowed_markers)]
    require(not unexpected, "Red/danger styling must be reserved for critical, offline, or dangerous classes: " + "; ".join(unexpected[:5]))

    print("Console v1.2 Operator UX source smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
