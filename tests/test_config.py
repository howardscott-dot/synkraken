"""Config validation behaviour."""
from __future__ import annotations

import json

import pytest

from synkraken.config import load_config


def _write(tmp_path, data: dict) -> str:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _base(**server) -> dict:
    return {
        "server": {"host": "127.0.0.1", "port": 9460, **server},
        "adapters": {"echo": {"type": "claude", "command": ["true"]}},
    }


def test_defaults_are_filled(tmp_path):
    cfg = load_config(_write(tmp_path, _base()))
    assert cfg.server["host"] == "127.0.0.1"
    assert cfg.server["port"] == 9460
    assert cfg.routing["max_hops"] == 4


def test_invalid_port_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, _base(port=70000)))


def test_auth_token_must_be_non_empty_string(tmp_path):
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, _base(auth_token="")))
    cfg = load_config(_write(tmp_path, _base(auth_token="secret")))
    assert cfg.server["auth_token"] == "secret"


def test_instance_name_suffix_only_rewrites_db_extension(tmp_path):
    data = _base()
    data["storage"] = {"sqlite_path": "/srv/foo.db/synkraken.db"}
    data["instance"] = {"instance_name": "dev"}
    cfg = load_config(_write(tmp_path, data))
    # Only the trailing .db is rewritten, not the directory component.
    assert cfg.storage["sqlite_path"] == "/srv/foo.db/synkraken-dev.db"


def test_native_engine_can_start_without_cli_adapters(tmp_path):
    data = {"server": {"host": "127.0.0.1", "port": 9460}, "adapters": {}}
    assert load_config(_write(tmp_path, data)).adapters == {}
