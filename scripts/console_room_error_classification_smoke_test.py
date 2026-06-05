from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _require(text: str, needles: list[str], label: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{label} missing: {', '.join(missing)}")


def _block_after(text: str, marker: str, length: int = 900) -> str:
    index = text.find(marker)
    if index < 0:
        raise AssertionError(f"marker missing: {marker}")
    return text[index:index + length]


def main() -> None:
    app = _read("apps/console/src/App.tsx")

    _require(
        app,
        [
            "const [daemonStatus, setDaemonStatus]",
            "const [globalError, setGlobalError]",
            "const [viewError, setViewError]",
            "const [nodeErrors, setNodeErrors]",
            "function isRoomNotFoundError",
            "function roomMissingWarning",
        ],
        "separate daemon and room error state",
    )

    health_block = _block_after(app, "const health = await api.getHealth().catch", 700)
    _require(
        health_block,
        [
            'setDaemonStatus("offline")',
            "setGlobalError(health.message || \"Daemon unavailable\")",
            'setDaemonStatus("online")',
            "setGlobalError(null)",
        ],
        "health controls daemon availability",
    )

    room_block = _block_after(app, "const loadRoom = useCallback", 1600)
    _require(
        room_block,
        [
            "api.getRoom(name)",
            "api.getRoomMessages(name, 100)",
            "api.getRoomMemory(name)",
            "isRoomNotFoundError(roomError)",
            "const roomMissing = isRoomNotFoundError(roomError)",
            "roomMissingWarning(name)",
            "setViewError(roomMissing ? `${message}. Create room or select another room` : message)",
            "setNodeErrors((current) => ({ ...current, [`room:${name}`]",
        ],
        "room failures stay local",
    )

    _require(
        app,
        [
            'error?.startsWith("Room not found:")',
            "Create room or select another room",
            "const localRoomWarning = roomError || (!selectedRoomExists ? roomMissingWarning(selectedRoom) : \"\")",
            "if (selectedRoom === \"ops\" && data.rooms.length && !data.rooms.some((room) => room.name === selectedRoom))",
            "if (firstRoom) setSelectedRoom(firstRoom)",
        ],
        "default room fallback or local warning",
    )

    if "Room not found" in _block_after(app, "function OfflineState", 400):
        raise AssertionError("room not found is still rendered as daemon unavailable")
    if 'setDaemonStatus("offline")' in room_block:
        raise AssertionError("room loading can mark daemon offline")
    if "setGlobalError" in room_block:
        raise AssertionError("room loading can set global daemon error")

    health_marker = app.find("const health = await api.getHealth().catch")
    for marker in ('setDaemonStatus("offline")', 'setDaemonStatus("online")'):
        marker_index = app.find(marker)
        if marker_index < health_marker or marker_index > health_marker + 900:
            raise AssertionError(f"{marker} appears outside health handling")

    print("console room error classification smoke test: ok")


if __name__ == "__main__":
    main()
