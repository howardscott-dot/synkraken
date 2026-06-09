#!/usr/bin/env python3
from __future__ import annotations

import stat
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters.ollama import OllamaAdapter
from synkraken.models import FabricMessage


def fake_ollama(path: Path, *, mode: str = "ok") -> None:
    if mode == "missing":
        body = """#!/bin/sh
printf 'model not found: llama3.2\n' >&2
exit 1
"""
    else:
        body = """#!/bin/sh
if [ "$1" != "run" ]; then
  printf 'unexpected command: %s\n' "$1" >&2
  exit 2
fi
printf 'model=%s\nprompt=%s\n' "$2" "$3"
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_success(tmp: Path) -> None:
    command = tmp / "ollama"
    fake_ollama(command)
    adapter = OllamaAdapter("ollama", {
        "type": "ollama",
        "command": [str(command)],
        "model": "llama3.2:latest",
        "timeout_seconds": 2,
    })
    reply = adapter.send(FabricMessage(source="operator", target="ollama", body="hello"))
    assert reply.ok is True
    assert "model=llama3.2:latest" in reply.body
    assert "prompt=hello" in reply.body
    assert reply.raw["model"] == "llama3.2:latest"


def test_prefix(tmp: Path) -> None:
    command = tmp / "ollama"
    fake_ollama(command)
    adapter = OllamaAdapter("ollama", {
        "type": "ollama",
        "command": [str(command)],
        "model": "tiny",
        "message_prefix": "Be concise.",
        "timeout_seconds": 2,
    })
    reply = adapter.send(FabricMessage(source="operator", target="ollama", body="hello"))
    assert reply.ok is True
    assert "Be concise." in reply.body
    assert "hello" in reply.body


def test_missing_model_guidance(tmp: Path) -> None:
    command = tmp / "ollama"
    fake_ollama(command, mode="missing")
    adapter = OllamaAdapter("ollama", {
        "type": "ollama",
        "command": [str(command)],
        "model": "llama3.2",
        "timeout_seconds": 2,
    })
    reply = adapter.send(FabricMessage(source="operator", target="ollama", body="hello"))
    assert reply.ok is False
    assert "model not found" in (reply.error or "")
    assert "ollama pull llama3.2" in (reply.error or "")


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        test_success(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_prefix(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        test_missing_model_guidance(Path(raw))
    print("ollama adapter smoke test: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
