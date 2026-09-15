from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Sequence


# Bound how much subprocess output is retained, so a runaway or hostile runtime
# cannot force unbounded memory growth downstream (storage, rendering).
MAX_OUTPUT_CHARS = 1_000_000


def _cap(text: str | None) -> str:
    text = text or ""
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n[synkraken] output truncated"
    return text


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill the child and any grandchildren it spawned (node, MCP servers, ...)."""
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


def is_remote_config(config: dict) -> bool:
    return bool(config.get("remote_host"))


def build_adapter_command(config: dict, command: Sequence[str]) -> list[str]:
    remote_host = str(config.get("remote_host") or "").strip()
    if not remote_host:
        return list(command)

    remote_user = str(config.get("remote_user") or "").strip()
    target = f"{remote_user}@{remote_host}" if remote_user else remote_host
    ssh_command = config.get("ssh_command") or ["ssh"]
    if isinstance(ssh_command, str):
        ssh_command = [ssh_command]
    ssh_args = [str(item) for item in ssh_command]
    remote_port = config.get("remote_port")
    if remote_port:
        ssh_args.extend(["-p", str(remote_port)])
    ssh_identity_file = str(config.get("ssh_identity_file") or "").strip()
    if ssh_identity_file:
        ssh_args.extend(["-i", str(Path(ssh_identity_file).expanduser())])
    ssh_options = [str(item) for item in config.get("ssh_options", [])]
    remote_working_dir = str(config.get("remote_working_dir") or "").strip()
    remote_path_entries = [str(item) for item in config.get("remote_path", []) if str(item)]

    shell_command = shlex.join([str(item) for item in command])
    if remote_path_entries:
        path_value = ":".join(shlex.quote(entry) for entry in remote_path_entries) + ":$PATH"
        shell_command = f"PATH={path_value} {shell_command}"
    if remote_working_dir:
        shell_command = f"cd {shlex.quote(remote_working_dir)} && {shell_command}"
    return ssh_args + ssh_options + [target, shell_command]


def run_command(
    command: Sequence[str],
    timeout_seconds: int | float,
    *,
    cwd: str | None = None,
    input_text: str | None = None,
    env: dict | None = None,
) -> tuple[int, str, str, int]:
    started = time.perf_counter()
    popen_kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        # Never let a child inherit and block on the daemon's stdin.
        "stdin": subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
    }
    if cwd is not None:
        popen_kwargs["cwd"] = cwd
    if env is not None:
        popen_kwargs["env"] = env
    if os.name == "posix":
        # Run in a new process group so a timeout can kill the entire tree,
        # not just the direct child — agent CLIs spawn node/MCP grandchildren
        # that would otherwise keep running (and keep spending) after we give up.
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(list(command), **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            # Drain briefly so pipes close and we don't leak the reader.
            proc.communicate(timeout=5)
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
        raise
    duration_ms = int((time.perf_counter() - started) * 1000)
    return proc.returncode, _cap(stdout).strip(), _cap(stderr).strip(), duration_ms
