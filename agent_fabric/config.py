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
    sqlite_path = storage.setdefault("sqlite_path", "./data/agent_fabric.db")
    if not isinstance(sqlite_path, str) or not sqlite_path:
        raise ValueError("storage.sqlite_path must be a non-empty string")


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
        adapter.setdefault("enabled", True)


def _validate(raw: dict) -> None:
    _validate_server(raw)
    _validate_storage(raw)
    _validate_routing(raw)
    _validate_adapters(raw)


def load_config(path: str | Path) -> Config:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    _validate(raw)
    return Config(raw=raw, path=config_path)
