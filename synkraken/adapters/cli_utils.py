from __future__ import annotations

import subprocess
import time
from typing import Sequence


def run_command(command: Sequence[str], timeout_seconds: int | float) -> tuple[int, str, str, int]:
    started = time.perf_counter()
    proc = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip(), duration_ms
