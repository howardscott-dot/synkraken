#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_in(text: str, needle: str, message: str) -> None:
    require(needle in text, message)


def main() -> None:
    prd = read("docs/prds/2026-06-01-console-v095-workforce-operations.md")
    app = read("apps/console/src/App.tsx")
    api_client = read("apps/console/src/lib/api.ts")
    styles = read("apps/console/src/styles.css")
    daemon_api = read("synkraken/api.py")
    doctrine = read("docs/PRODUCT_DOCTRINE.md")

    matrix_headers = ["Capability", "CLI", "TUI", "API", "Console Before v0.95"]
    for header in matrix_headers:
        require_in(prd, header, f"PRD gap matrix missing {header}")
    for capability in [
        "Create room",
        "Delete room",
        "Send `@everyone`",
        "Send `@worker-id`",
        "View delivery results",
        "Search room history if available",
        "Summarise room if available",
    ]:
        require_in(prd, capability, f"PRD gap matrix missing {capability}")

    require_in(doctrine, "Operations Before Observability", "product doctrine missing Operations Before Observability")

    for route in [
        'if path == "/v1/rooms"',
        '"/v1/rooms/preset"',
        'r"/v1/rooms/([^/]+)/members"',
        'r"/v1/rooms/([^/]+)/messages"',
        'r"/v1/rooms/([^/]+)/summary"',
        'def do_DELETE',
    ]:
        require_in(daemon_api, route, f"daemon API route missing {route}")

    for client_symbol in [
        "createRoom:",
        "createRoomPreset:",
        "deleteRoom:",
        "recordRoomNote:",
        "sendRoomScopedMessage:",
        "searchRoomMessages:",
        "summarizeRoom:",
        "addRoomMember:",
        "removeRoomMember:",
    ]:
        require_in(api_client, client_symbol, f"Console API client missing {client_symbol}")

    for app_symbol in [
        "Workforce Operations",
        "Create Room",
        "Delete Room",
        "Open Room Chat",
        "Add Worker to Room",
        "Add All Workers to Room",
        "Broadcast @everyone",
        "Message Worker",
        "Refresh Room",
        "Search Room History",
        "roomTargetFromComposer",
        "@everyone Who is available?",
        "sendRoomScopedMessage",
        "recordRoomNote",
        "DeliverySummaryPanel",
        "DeliveryRow",
        "empty reply",
        "Failed - adapter or runtime could not complete the request.",
        "Timeout - worker did not complete before the runtime limit.",
        "Rename unavailable",
        "Remove all unavailable",
        "Mission Centre",
        "Outcome Centre",
    ]:
        require_in(app, app_symbol, f"Console source missing {app_symbol}")

    for style_symbol in [
        ".workforce-operations-grid",
        ".room-chat-transcript",
        ".room-chat-input",
        ".delivery-summary",
        ".delivery-row",
        ".chat-row-worker",
    ]:
        require_in(styles, style_symbol, f"Console CSS missing {style_symbol}")

    print("console v0.95 workforce operations smoke test: ok")


if __name__ == "__main__":
    main()
