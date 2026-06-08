from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(slots=True)
class Config:
    raw: dict
    path: Path

    @property
    def server(self) -> dict:
        return self.raw.get("server", {})

    @property
    def storage(self) -> dict:
        return self.raw.get("storage", {})

    @property
    def routing(self) -> dict:
        return self.raw.get("routing", {})

    @property
    def adapters(self) -> dict:
        return self.raw.get("adapters", {})


def _validate_server(raw: dict) -> None:
    server = raw.setdefault("server", {})
    host = server.setdefault("host", "127.0.0.1")
    port = server.setdefault("port", 9460)
    if not isinstance(host, str) or not host:
        raise ValueError("server.host must be a non-empty string")
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError("server.port must be an integer between 1 and 65535")


def _validate_storage(raw: dict) -> None:
    storage = raw.setdefault("storage", {})
    sqlite_path = storage.setdefault("sqlite_path", "./data/synkraken.db")
    if not isinstance(sqlite_path, str) or not sqlite_path:
        raise ValueError("storage.sqlite_path must be a non-empty string")
    instance_name = raw.get("instance", {}).get("instance_name", "")
    if instance_name:
        sqlite_path = sqlite_path.replace(".db", f"-{instance_name}.db")
        storage["sqlite_path"] = sqlite_path


def _validate_instance(raw: dict) -> None:
    instance = raw.setdefault("instance", {})
    for key in ("instance_name", "organisation_name", "organization_name", "default_workspace"):
        value = instance.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"instance.{key} must be a string when set")
    for legacy_key in ("instance_name", "organisation_name", "organization_name", "default_workspace"):
        value = raw.get(legacy_key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{legacy_key} must be a string when set")


def _validate_routing(raw: dict) -> None:
    routing = raw.setdefault("routing", {})
    max_hops = routing.setdefault("max_hops", 4)
    timeout = routing.setdefault("default_timeout_seconds", 90)
    retry_limit = routing.setdefault("retry_limit", 1)
    retry_backoff_seconds = routing.setdefault("retry_backoff_seconds", 1)
    if not isinstance(max_hops, int) or max_hops < 0:
        raise ValueError("routing.max_hops must be a non-negative integer")
    if not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("routing.default_timeout_seconds must be a positive integer")
    if not isinstance(retry_limit, int) or retry_limit < 0:
        raise ValueError("routing.retry_limit must be a non-negative integer")
    if not isinstance(retry_backoff_seconds, int) or retry_backoff_seconds < 0:
        raise ValueError("routing.retry_backoff_seconds must be a non-negative integer")


def _validate_memory(raw: dict) -> None:
    memory = raw.setdefault("memory", {})
    defaults = {
        "max_items_injected": 5,
        "max_chars_injected": 1200,
        "max_memory_chars": 500,
        "min_confidence": 70,
    }
    for key, default in defaults.items():
        value = memory.setdefault(key, default)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"memory.{key} must be a positive integer")


def _validate_goal(raw: dict) -> None:
    goal = raw.setdefault("goal", {})
    defaults = {
        "max_rounds": 3,
        "threshold": 80,
        "max_reviewers": 3,
        "max_context_chars": 4000,
        "max_revision_chars": 1500,
        "max_agents": 4,
    }
    for key, default in defaults.items():
        value = goal.setdefault(key, default)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"goal.{key} must be a positive integer")


def _validate_adapters(raw: dict) -> None:
    adapters = raw.setdefault("adapters", {})
    if not isinstance(adapters, dict) or not adapters:
        raise ValueError("adapters must be a non-empty object")
    for adapter_id, adapter in adapters.items():
        if not isinstance(adapter, dict):
            raise ValueError(f"adapter '{adapter_id}' must be an object")
        adapter_type = adapter.get("type")
        if not isinstance(adapter_type, str) or not adapter_type:
            raise ValueError(f"adapter '{adapter_id}' must define a non-empty type")
        command = adapter.get("command")
        if command is not None:
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError(f"adapter '{adapter_id}' command must be a non-empty list of strings")
        timeout = adapter.setdefault("timeout_seconds", raw["routing"]["default_timeout_seconds"])
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"adapter '{adapter_id}' timeout_seconds must be a positive integer")
        cost_tier = str(adapter.setdefault("cost_tier", adapter.get("cost_profile", "medium"))).strip().lower()
        if cost_tier not in {"local", "cheap", "medium", "premium"}:
            raise ValueError(f"adapter '{adapter_id}' cost_tier must be local, cheap, medium, or premium")
        adapter["cost_tier"] = cost_tier
        usage_risk = str(adapter.setdefault("usage_risk", "medium")).strip().lower()
        if usage_risk not in {"low", "medium", "high"}:
            raise ValueError(f"adapter '{adapter_id}' usage_risk must be low, medium, or high")
        adapter["usage_risk"] = usage_risk
        for key in ("preferred_roles", "avoid_roles"):
            roles = adapter.setdefault(key, [])
            if not isinstance(roles, list) or not all(isinstance(role, str) and role for role in roles):
                raise ValueError(f"adapter '{adapter_id}' {key} must be a list of strings")
        adapter.setdefault("enabled", True)


def _validate(raw: dict) -> None:
    _validate_server(raw)
    _validate_storage(raw)
    _validate_instance(raw)
    _validate_routing(raw)
    _validate_memory(raw)
    _validate_goal(raw)
    _validate_adapters(raw)


def load_config(path: str | Path) -> Config:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    _validate(raw)
    return Config(raw=raw, path=config_path)
