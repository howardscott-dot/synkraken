from __future__ import annotations

import re
import subprocess

from .base import BaseAdapter
from .cli_utils import build_adapter_command, run_command
from .text_normalize import normalize_text_output
from ..models import AdapterReply, FabricMessage


class AntigravityAdapter(BaseAdapter):
    """Adapter for Google Antigravity CLI (agy).

    Runs `agy --print --dangerously-skip-permissions` for each fabric message.

    Configurable via the adapter's config block in config.local.json:
      command:           argv list (default ["agy"])
      timeout_seconds:   subprocess timeout (default 120)
    """

    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or "Google Antigravity"

    def _normalize_output(self, text: str) -> str:
        if not text:
            return text
        normalized = normalize_text_output(text)
        if normalized:
            return normalized
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return text.strip()
        if len(lines) == 1:
            return lines[0]
        # Prefer a terminal ALLCAPS marker line when present (consistent
        # with goose/hermes/openclaw normalisation).
        for line in reversed(lines):
            if re.match(r"^[A-Z0-9_-]+:\s+.+$", line):
                return line
            if re.match(r"^[A-Z0-9_-]+$", line):
                return line
        return "\n".join(lines).strip()

    def _auth_required(self, text: str) -> bool:
        lowered = text.lower()
        return "authentication required" in lowered or "accounts.google.com/o/oauth2" in lowered

    def send(self, message: FabricMessage) -> AdapterReply:
        base_command = self.config.get("command", ["agy"])
        timeout = int(self.config.get("timeout_seconds", 120))
        local_command = list(base_command) + [
            "--dangerously-skip-permissions",
            "--print",
            message.body,
        ]
        command = build_adapter_command(self.config, local_command)

        try:
            returncode, stdout, stderr, duration_ms = run_command(command, timeout)
            ok = returncode == 0
            clean_stdout = self._normalize_output(stdout.strip())
            clean_stderr = stderr.strip()
            auth_required = self._auth_required(stdout) or self._auth_required(stderr)
            if auth_required:
                clean_stdout = "Antigravity needs sign-in on the worker machine."
                ok = False
            return AdapterReply(
                adapter_id=self.adapter_id,
                ok=ok,
                body=clean_stdout if clean_stdout else clean_stderr,
                error=None if ok else (
                    "Antigravity authentication required"
                    if auth_required else (clean_stderr or f"agy exited with code {returncode}")
                ),
                duration_ms=duration_ms,
                raw={"command": command, "stderr": clean_stderr, "returncode": returncode, "auth_required": auth_required},
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
