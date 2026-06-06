from __future__ import annotations

from pathlib import Path
import re

from .base import BaseAdapter
from .cli_utils import build_adapter_command, run_command
from ..models import AdapterReply, FabricMessage


class HermesAdapter(BaseAdapter):
    def runtime_name(self) -> str:
        explicit = self.config.get("runtime_name")
        if explicit:
            return explicit
        soul_path = self.config.get("identity_file") or str(Path.home() / ".hermes" / "SOUL.md")
        try:
            text = Path(soul_path).read_text(encoding="utf-8")
            match = re.search(r"Your name is\s+([A-Za-z0-9_-]+)", text)
            if match:
                return match.group(1)
        except Exception:
            pass
        return "Hermes"

    def _normalize_output(self, text: str) -> str:
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

    def send(self, message: FabricMessage) -> AdapterReply:
        base_command = self.config.get("command", ["hermes"])
        timeout = int(self.config.get("timeout_seconds", 120))
        prefix = self.config.get("system_prefix")
        body = f"{prefix}\n\n{message.body}" if prefix else message.body
        local_command = list(base_command) + ["-z", body]
        if self.config.get("yolo", False):
            local_command.append("--yolo")
        if self.config.get("accept_hooks", False):
            local_command.append("--accept-hooks")
        model = self.config.get("model")
        provider = self.config.get("provider")
        toolsets = self.config.get("toolsets")
        if model:
            local_command.extend(["--model", str(model)])
        if provider:
            local_command.extend(["--provider", str(provider)])
        if toolsets:
            local_command.extend(["--toolsets", str(toolsets)])
        command = build_adapter_command(self.config, local_command)
        returncode, stdout, stderr, duration_ms = run_command(command, timeout)
        ok = returncode == 0
        clean_stdout = self._normalize_output(stdout.strip())
        clean_stderr = stderr.strip()
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=ok,
            body=clean_stdout if clean_stdout else clean_stderr,
            error=None if ok else (clean_stderr or f"hermes exited with code {returncode}"),
            duration_ms=duration_ms,
            raw={"command": command, "stderr": clean_stderr, "returncode": returncode},
        )
