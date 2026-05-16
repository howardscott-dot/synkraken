from __future__ import annotations

from typing import Iterable


def resolve_targets(source: str, target: str, available: Iterable[str]) -> list[str]:
    available_ids = list(available)
    if target == "broadcast":
        return [agent_id for agent_id in available_ids if agent_id != source]
    if target not in available_ids:
        raise ValueError(f"Unknown target adapter: {target}")
    return [target]
