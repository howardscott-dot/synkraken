from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Sequence


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
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": timeout_seconds,
    }
    if cwd is not None:
        kwargs["cwd"] = cwd
    if input_text is not None:
        kwargs["input"] = input_text
    if env is not None:
        kwargs["env"] = env
    proc = subprocess.run(
        list(command),
        **kwargs,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip(), duration_ms
