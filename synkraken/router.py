from __future__ import annotations

from typing import Iterable, Protocol


class _MembersResolver(Protocol):
    def get_room_members(self, name: str) -> list[str]: ...
    def room_exists(self, name: str) -> bool: ...


def resolve_targets(
    source: str,
    target: str,
    available: Iterable[str],
    storage: _MembersResolver | None = None,
) -> list[str]:
    available_ids = list(available)

    if target == "broadcast":
        return [agent_id for agent_id in available_ids if agent_id != source]

    if target.startswith("room:"):
        if storage is None:
            raise ValueError("room targets require storage to resolve members")
        room_name = target[len("room:"):]
        if not storage.room_exists(room_name):
            raise ValueError(f"Unknown room: {room_name}")
        members = storage.get_room_members(room_name)
        return [m for m in members if m != source and m in available_ids]

    if target not in available_ids:
        raise ValueError(f"Unknown target adapter: {target}")
    return [target]
