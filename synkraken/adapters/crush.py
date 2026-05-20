from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .base import BaseAdapter
from .cli_utils import run_command
from ..models import AdapterReply, FabricMessage


class CrushAdapter(BaseAdapter):
    """Adapter for the Crush CLI.

    Runs `crush run` in non-interactive mode for each fabric message. Uses
    --quiet to suppress spinner output. The working directory is controlled
    by the adapter config's working_dir field; if not set, defaults to the
    user's home directory to avoid accidental repository context leakage.

    Prompt isolation: every message is wrapped with a SynKraken boundary
    that instructs Crush to respond only to the user message and not
    inspect the repository unless explicitly asked.

    Configurable via the adapter's config block in config.local.json:
      command:           argv list (default ["crush"])
      timeout_seconds:   subprocess timeout (default 120)
      working_dir:       working directory for the subprocess (default ~/)
    """

    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or "Crush"

    def _normalize_output(self, text: str) -> str:
        if not text:
            return text
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text.strip()
        if len(lines) == 1:
            return lines[0]
        for line in reversed(lines):
            if re.match(r"^[A-Z0-9_-]+:\s+.+$", line):
                return line
            if re.match(r"^[A-Z0-9_-]+$", line):
                return line
        return "\n".join(lines).strip()

    def _prompt_boundary(self, body: str) -> str:
        return (
            "You are receiving a direct message from SynKraken.\n"
            "Respond only to the user message below.\n"
            "Do not inspect the current repository unless explicitly asked.\n"
            "Do not explain Crush, SynKraken, or your invocation flags unless asked.\n"
            "If the user asks for exact output, return only that exact output.\n\n"
            "User message:\n"
            "<<<\n"
            f"{body}\n"
            ">>>"
        )

    def _build_env(self) -> dict:
        env = os.environ.copy()
        path_entries: list[str] = []

        cmd = self.config.get("command", ["crush"])
        if cmd:
            cmd_dir = str(Path(cmd[0]).parent.resolve())
            if cmd_dir and cmd_dir not in path_entries:
                path_entries.append(cmd_dir)

        configured_node_bin = self.config.get("node_bin_dir")
        if configured_node_bin and str(configured_node_bin) not in path_entries:
            path_entries.append(str(configured_node_bin))

        discovered_node_bin = self.config.get("node_bin_dir") or self.config.get("node_path")
        if discovered_node_bin and str(discovered_node_bin) not in path_entries:
            node_dir = str(Path(discovered_node_bin).parent) if "/" in discovered_node_bin else None
            if node_dir and node_dir not in path_entries:
                path_entries.append(node_dir)

        home_node_dir = Path.home() / ".nvm" / "versions" / "node"
        if home_node_dir.is_dir():
            try:
                for version_link in home_node_dir.iterdir():
                    bin_dir = str(version_link / "bin")
                    if bin_dir not in path_entries:
                        path_entries.append(bin_dir)
            except OSError:
                pass

        if path_entries:
            existing_path = env.get("PATH", "")
            env["PATH"] = os.pathsep.join(reversed(path_entries)) + (os.pathsep + existing_path if existing_path else "")

        return env

    def send(self, message: FabricMessage) -> AdapterReply:
        base_command = self.config.get("command", ["crush"])
        timeout = int(self.config.get("timeout_seconds", 120))
        working_dir = self.config.get("working_dir") or os.path.expanduser("~")

        wrapped_body = self._prompt_boundary(message.body)
        command = list(base_command) + [
            "run",
            "--quiet",
            "--",
            wrapped_body,
        ]

        try:
            returncode, stdout, stderr, duration_ms = run_command(
                command,
                timeout,
                cwd=working_dir,
                env=self._build_env(),
            )
        except subprocess.TimeoutExpired:
            return AdapterReply(
                adapter_id=self.adapter_id,
                ok=False,
                body="",
                error=f"Command timed out after {timeout} seconds",
                duration_ms=int(timeout * 1000),
                raw={"command": command, "stderr": "", "returncode": -1, "timeout": True},
            )
        ok = returncode == 0
        clean_stdout = self._normalize_output(stdout.strip())
        clean_stderr = stderr.strip()
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=ok,
            body=clean_stdout if clean_stdout else clean_stderr,
            error=None if ok else (clean_stderr or f"crush exited with code {returncode}"),
            duration_ms=duration_ms,
            raw={"command": command, "stderr": clean_stderr, "returncode": returncode},
        )