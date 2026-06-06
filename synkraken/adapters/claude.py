from __future__ import annotations

import json
import re

from .base import BaseAdapter
from .cli_utils import build_adapter_command, run_command
from ..models import AdapterReply, FabricMessage


class ClaudeAdapter(BaseAdapter):
    """Adapter for Anthropic's Claude Code CLI.

    Runs `claude -p` in print mode for each fabric message. Uses --bare to
    skip hooks/MCP/CLAUDE.md/auto-memory (fast, deterministic, low-cost), and
    --permission-mode bypassPermissions so subprocess invocation never hangs
    on a tool-permission prompt.

    Configurable via the adapter's config block in config.local.json:
      command:           argv list (default ["claude"])
      timeout_seconds:   subprocess timeout (default 120)
      bare:              skip hooks/MCP/etc (default True)
      permission_mode:   default "bypassPermissions"
      output_format:     "text" (default) | "json"
      model:             optional, e.g. "sonnet" or "opus"
      system:            optional system prompt prefix
      message_prefix:    optional prefix prepended to each user message
    """

    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or "Claude"

    def _normalize_output(self, text: str) -> str:
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

    def send(self, message: FabricMessage) -> AdapterReply:
        base_command = self.config.get("command", ["claude"])
        timeout = int(self.config.get("timeout_seconds", 120))
        bare = bool(self.config.get("bare", True))
        permission_mode = str(self.config.get("permission_mode", "bypassPermissions"))
        output_format = str(self.config.get("output_format", "text"))
        model = self.config.get("model")
        system = self.config.get("system")
        message_prefix = self.config.get("message_prefix")

        runtime_name = self.runtime_name()
        dynamic_prefix = (
            f"You are {runtime_name}. You are receiving this via synkraken. "
            f"Reply as {runtime_name}, not as the sender, and keep replies "
            f"direct and concise."
        )
        if message_prefix:
            dynamic_prefix = f"{dynamic_prefix} {message_prefix}"
        body = f"{dynamic_prefix}\n\n{message.body}"

        local_command = list(base_command) + [
            "-p",
            "--no-session-persistence",
            "--permission-mode", permission_mode,
            "--output-format", output_format,
        ]
        if bare:
            local_command.append("--bare")
        if model:
            local_command.extend(["--model", str(model)])
        if system:
            local_command.extend(["--system-prompt", str(system)])
        local_command.append(body)
        command = build_adapter_command(self.config, local_command)

        returncode, stdout, stderr, duration_ms = run_command(command, timeout)
        ok = returncode == 0

        reply_text = stdout
        if output_format == "json" and stdout:
            try:
                parsed = json.loads(stdout)
                # Claude's JSON shape exposes the final response in 'result'
                # (with --output-format=json) or 'content' (legacy). Fall back
                # to the raw stdout when neither key exists.
                reply_text = (parsed.get("result")
                              or parsed.get("content")
                              or parsed.get("text")
                              or stdout)
                if isinstance(reply_text, list):
                    # content blocks → concatenate text parts
                    reply_text = "\n".join(
                        block.get("text", "") for block in reply_text
                        if isinstance(block, dict) and block.get("type") == "text"
                    ).strip() or stdout
            except json.JSONDecodeError:
                pass

        clean_stdout = self._normalize_output(reply_text or "")
        clean_stderr = stderr.strip()
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=ok,
            body=clean_stdout if clean_stdout else clean_stderr,
            error=None if ok else (clean_stderr or f"claude exited with code {returncode}"),
            duration_ms=duration_ms,
            raw={"command": command, "stderr": clean_stderr, "returncode": returncode},
        )
