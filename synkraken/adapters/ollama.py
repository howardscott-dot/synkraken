from __future__ import annotations

from .base import BaseAdapter
from .cli_utils import build_adapter_command, run_command
from ..models import AdapterReply, FabricMessage


class OllamaAdapter(BaseAdapter):
    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or "Ollama"

    def health(self) -> dict:
        data = super().health()
        data["model"] = self._model()
        return data

    def _model(self) -> str:
        return str(self.config.get("model") or "llama3.2").strip()

    def send(self, message: FabricMessage) -> AdapterReply:
        model = self._model()
        if not model:
            return AdapterReply(
                adapter_id=self.adapter_id,
                ok=False,
                body="",
                error="Ollama model not configured. Run: ollama list",
                duration_ms=0,
                raw={},
            )
        timeout = int(self.config.get("timeout_seconds", 180))
        prefix = str(self.config.get("message_prefix") or "").strip()
        body = f"{prefix}\n\n{message.body}".strip() if prefix else message.body
        base_command = self.config.get("command", ["ollama"])
        local_command = [*base_command, "run", model, body]
        command = build_adapter_command(self.config, local_command)
        returncode, output, error_output, duration_ms = run_command(command, timeout)
        if returncode != 0:
            detail = error_output or output or f"ollama exited with status {returncode}"
            if "pull" in detail.lower() or "not found" in detail.lower():
                detail = f"{detail}\nSuggested action: ollama pull {model}"
            return AdapterReply(
                adapter_id=self.adapter_id,
                ok=False,
                body="",
                error=detail,
                duration_ms=duration_ms,
                raw={"returncode": returncode, "model": model},
            )
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=True,
            body=output,
            duration_ms=duration_ms,
            raw={"model": model},
        )
