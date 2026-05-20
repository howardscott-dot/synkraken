from __future__ import annotations

import subprocess
import time
from typing import Sequence


def run_command(
    command: Sequence[str],
    timeout_seconds: int | float,
    *,
    cwd: str | None = None,
    input_text: str | None = None,
) -> tuple[int, str, str, int]:
    started = time.perf_counter()
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": timeout_seconds,
    }
    if cwd is not None:
        kwargs["cwd"] = cwd
    if input_text is not None:
        kwargs["input"] = input_text
    proc = subprocess.run(
        list(command),
        **kwargs,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip(), duration_ms
