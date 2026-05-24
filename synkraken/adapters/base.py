from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import AdapterReply, FabricMessage


class AdapterError(RuntimeError):
    pass


class BaseAdapter(ABC):
    def __init__(self, adapter_id: str, config: dict[str, Any]) -> None:
        self.adapter_id = adapter_id
        self.config = config

    @abstractmethod
    def send(self, message: FabricMessage) -> AdapterReply:
        raise NotImplementedError

    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or self.adapter_id

    def runtime_kind(self) -> str:
        return self.config.get("type", "unknown")

    def health(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "adapter_id": self.adapter_id,
            "type": self.runtime_kind(),
            "runtime_name": self.runtime_name(),
            "enabled": bool(self.config.get("enabled", True)),
        }
        for key in ("cost_tier", "usage_risk", "preferred_roles", "avoid_roles", "capabilities", "speed", "trust"):
            if key in self.config:
                data[key] = self.config[key]
        return data
