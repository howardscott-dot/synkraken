"""Adapter subprocess hygiene and output sanitization."""
from __future__ import annotations

import subprocess
import time

import pytest

from synkraken.adapters.cli_utils import run_command
from synkraken.adapters.text_normalize import strip_terminal_controls


def test_strip_terminal_controls_removes_escape_sequences():
    dirty = "hello\x1b[2Jworld\x07\x00 end"
    clean = strip_terminal_controls(dirty)
    assert "\x1b" not in clean
    assert "\x07" not in clean
    assert "\x00" not in clean
    # Tab and newline are preserved.
    assert strip_terminal_controls("a\tb\nc") == "a\tb\nc"


def test_run_command_basic_capture():
    code, out, err, ms = run_command(["printf", "hello"], timeout_seconds=10)
    assert code == 0
    assert out == "hello"


def test_run_command_stdin_is_not_inherited():
    # Reading stdin should hit EOF immediately (DEVNULL), not block.
    code, out, err, ms = run_command(["cat"], timeout_seconds=5)
    assert code == 0
    assert out == ""


def test_run_command_timeout_kills_process_tree():
    started = time.perf_counter()
    # A shell that spawns a long-lived child; on timeout the whole group is
    # killed, so this returns promptly rather than hanging on the child's pipe.
    with pytest.raises(subprocess.TimeoutExpired):
        run_command(["sh", "-c", "sleep 30 & wait"], timeout_seconds=1)
    assert time.perf_counter() - started < 15
