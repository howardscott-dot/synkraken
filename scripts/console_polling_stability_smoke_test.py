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

    _require(
        app,
        [
            'type DaemonStatus = "unknown" | "online" | "offline"',
            "const [daemonStatus, setDaemonStatus]",
            "const [globalError, setGlobalError]",
            "const [viewError, setViewError]",
            "const [nodeErrors, setNodeErrors]",
            'const daemonOnline = daemonStatus === "online"',
            "api.getHealth().catch",
            'setDaemonStatus("offline")',
            "Promise.allSettled",
            "setViewError(endpointErrors[0] || null)",
        ],
        "separate daemon and endpoint error state",
    )
    _require(
        app,
        [
            "setData((current) =>",
            "agents.status === \"fulfilled\" ? agents.value.agents || [] : current.agents",
            "rooms.status === \"fulfilled\" ? rooms.value.rooms || [] : current.rooms",
            "canvasRelationships: sameCanvasRelationships(current.canvasRelationships, nextRelationships) ? current.canvasRelationships : nextRelationships",
            "setRefreshing(true)",
            "!loading && refreshing",
        ],
        "background refresh keeps existing data",
    )
    _require(
        app,
        [
            "layoutDirtyRef",
            "saveTimerRef",
            "setLayoutInitialized(true)",
            "!layoutRestored && !layoutInitialized",
            "markLayoutDirty",
            "saveLayoutNow",
        ],
        "canvas layout stability",
    )
    _require(
        app,
        [
            "setSelectedNode(id)",
            'key={node.id}',
            "nodeErrors[node.id]",
            "roomMissingWarning",
            "isRoomNotFoundError(roomError)",
        ],
        "node identity and local room errors",
    )
    _require(
        app,
        [
            "sameCanvasRelationships",
            "buildRelationships(nodes, data.canvasRelationships)",
            "useMemo(() => buildRelationships",
        ],
        "relationship rendering stability",
    )
    _require(
        api,
        [
            "class ApiError extends Error",
            "status?: number",
            "throw new ApiError(detail, response.status)",
        ],
        "endpoint status preservation",
    )

    if "setError(" in app or "const [error, setError]" in app:
        raise AssertionError("single global error state remains")
    if "setLoading(true)" in app:
        raise AssertionError("global loading is still toggled for every refresh")
    if 'daemonOnline = !error' in app:
        raise AssertionError("endpoint error still controls daemon online state")
    if 'setRoomDetail({ messages: [] })' in app:
        raise AssertionError("room errors still clear existing room data")
    if 'loading ? "loading" : error ? "error"' in app:
        raise AssertionError("canvas node header still flips through loading/error labels on poll")

    print("console polling stability smoke test: ok")


if __name__ == "__main__":
    main()
