from __future__ import annotations

import re

from .base import BaseAdapter
from .cli_utils import run_command
from ..models import AdapterReply, FabricMessage


class GooseAdapter(BaseAdapter):
    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or "Goose"

    def _normalize_output(self, text: str) -> str:
        if not text:
            return text
        lines = [line.rstrip() for line in text.splitlines()]
        filtered: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[tool") or stripped.startswith("tool_"):
                continue
            if stripped.startswith("Updated ("):
                continue
            if stripped.startswith("goose is running"):
                continue
            filtered.append(stripped)
        if not filtered:
            return text.strip()
        if len(filtered) == 1:
            return filtered[0]
        exact_line = None
        for line in reversed(filtered):
            if re.match(r"^[A-Z0-9_-]+:\s+.+$", line):
                exact_line = line
                break
            if re.match(r"^[A-Z0-9_-]+$", line):
                exact_line = line
                break
        return exact_line or "\n".join(filtered).strip()

    def send(self, message: FabricMessage) -> AdapterReply:
        base_command = self.config.get("command", ["goose"])
        timeout = int(self.config.get("timeout_seconds", 90))
        command = list(base_command) + [
            "run",
            "--text",
            message.body,
            "--quiet",
            "--no-session",
        ]
        system = self.config.get("system")
        if system:
            command.extend(["--system", str(system)])
        returncode, stdout, stderr, duration_ms = run_command(command, timeout)
        ok = returncode == 0
        clean_stdout = self._normalize_output(stdout.strip())
        clean_stderr = stderr.strip()
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=ok,
            body=clean_stdout if clean_stdout else clean_stderr,
            error=None if ok else (clean_stderr or f"goose exited with code {returncode}"),
            duration_ms=duration_ms,
            raw={"command": command, "stderr": clean_stderr, "returncode": returncode},
        )
