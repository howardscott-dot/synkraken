from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import re

from .base import BaseAdapter
from .cli_utils import run_command
from ..models import AdapterReply, FabricMessage


class OpenClawAdapter(BaseAdapter):
    """Experimental adapter.

    This adapter assumes the OpenClaw CLI can deliver a one-shot message to a
    configured agent via the local gateway and return JSON. Deployments may vary.
    """

    def runtime_name(self) -> str:
        explicit = self.config.get("runtime_name")
        if explicit:
            return explicit
        agent_id = str(self.config.get("agent_id", "main"))
        config_path = self.config.get("config_path") or str(Path.home() / ".openclaw" / "openclaw.json")
        try:
            raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
            agents = raw.get("agents", {}).get("list", [])
            for agent in agents:
                if agent.get("id") == agent_id:
                    return agent.get("name") or agent_id
        except Exception:
            pass
        if agent_id == "main":
            return "Stanley"
        return agent_id

    def _extract_text(self, parsed: Any) -> str | None:
        if parsed is None:
            return None
        if isinstance(parsed, str):
            stripped = parsed.strip()
            return stripped or None
        if isinstance(parsed, list):
            parts: list[str] = []
            for item in parsed:
                extracted = self._extract_text(item)
                if extracted:
                    parts.append(extracted)
            return "\n".join(parts).strip() or None
        if isinstance(parsed, dict):
            for key in ("reply", "message", "text", "content", "output"):
                if key in parsed:
                    extracted = self._extract_text(parsed.get(key))
                    if extracted:
                        return extracted
            for nested_key in ("payloads", "result", "choices", "assistant"):
                extracted = self._extract_text(parsed.get(nested_key))
                if extracted:
                    return extracted
            return None
        return None

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

    def _compact_raw(self, parsed: Any, stderr: str, returncode: int, command: list[str]) -> dict:
        compact = {
            "command": command,
            "stderr": stderr,
            "returncode": returncode,
        }
        if isinstance(parsed, dict):
            compact["top_level_keys"] = sorted(parsed.keys())[:32]
            extracted = self._extract_text(parsed)
            if extracted:
                compact["extracted_text_preview"] = extracted[:1000]
        elif isinstance(parsed, list):
            compact["parsed_list_length"] = len(parsed)
            extracted = self._extract_text(parsed)
            if extracted:
                compact["extracted_text_preview"] = extracted[:1000]
        elif isinstance(parsed, str):
            compact["parsed_preview"] = parsed[:1000]
        return compact

    def send(self, message: FabricMessage) -> AdapterReply:
        base_command = self.config.get("command", ["openclaw"])
        timeout = int(self.config.get("timeout_seconds", 120))
        agent_id = str(self.config.get("agent_id", "main"))
        prefix = self.config.get("message_prefix")
        runtime_name = self.runtime_name()
        dynamic_prefix = f"You are {runtime_name}. You are receiving this via synkraken. Reply as {runtime_name}, not as the sender, and keep replies direct and concise."
        if prefix:
            dynamic_prefix = f"{dynamic_prefix} {prefix}"
        body = f"{dynamic_prefix}\n\n{message.body}"
        command = list(base_command) + [
            "agent",
            "--agent",
            agent_id,
            "--message",
            body,
            "--json",
        ]
        if self.config.get("local", False):
            command.append("--local")
        returncode, stdout, stderr, duration_ms = run_command(command, timeout)
        ok = returncode == 0
        parsed: dict | list | str | None = None
        if stdout:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = None
        reply_text = self._extract_text(parsed) if parsed is not None else None
        if not reply_text:
            reply_text = stdout if stdout else stderr
        reply_text = self._normalize_output(reply_text)
        raw = self._compact_raw(parsed=parsed, stderr=stderr, returncode=returncode, command=command)
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=ok,
            body=reply_text,
            error=None if ok else (stderr or f"openclaw exited with code {returncode}"),
            duration_ms=duration_ms,
            raw=raw,
        )
