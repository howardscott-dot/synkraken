from __future__ import annotations

from http import HTTPStatus
import json
import os
import socket
import time
import urllib.error
import urllib.request

from .base import BaseAdapter
from ..models import AdapterReply, FabricMessage


class OdysseusAdapter(BaseAdapter):
    def runtime_name(self) -> str:
        return self.config.get("runtime_name") or "Odysseus"

    def health(self) -> dict:
        data = super().health()
        data["experimental"] = True
        data["base_url"] = self._base_url()
        if self.config.get("model"):
            data["model"] = str(self.config["model"])
        data["token_configured"] = bool(self._token())
        return data

    def _base_url(self) -> str:
        return str(self.config.get("base_url") or "http://127.0.0.1:7000").rstrip("/")

    def _timeout(self) -> int:
        return int(self.config.get("timeout_seconds", 120))

    def _token(self) -> str:
        token_env = str(self.config.get("token_env") or "").strip()
        if token_env:
            token = os.environ.get(token_env, "").strip()
            if token:
                return token
        return str(self.config.get("token") or "").strip()

    def _session_id(self, message: FabricMessage) -> str | None:
        metadata = message.metadata or {}
        for key in ("odysseus_session_id", "odysseus_session", "session_id", "session"):
            value = metadata.get(key)
            if value:
                return str(value)
        return None

    def _error_reply(self, error: str, duration_ms: int, raw: dict | None = None) -> AdapterReply:
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=False,
            body="",
            error=error,
            duration_ms=duration_ms,
            raw=raw or {},
        )

    def _odysseus_error_detail(self, payload: str) -> str:
        if not payload:
            return ""
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return payload.strip()[:1000]
        detail = parsed.get("detail") if isinstance(parsed, dict) else None
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return json.dumps(detail, ensure_ascii=False)
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, str):
            return error
        return payload.strip()[:1000]

    def send(self, message: FabricMessage) -> AdapterReply:
        started = time.perf_counter()
        token = self._token()
        if not token:
            return self._error_reply(
                "Odysseus API token missing; set token_env or token in adapter config",
                0,
                raw={"base_url": self._base_url(), "token_configured": False},
            )

        payload = {
            "message": message.body,
            "model": str(self.config.get("model") or ""),
        }
        session_id = self._session_id(message)
        if session_id:
            payload["session"] = session_id

        endpoint = f"{self._base_url()}/api/v1/chat"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout()) as response:
                status = int(response.status)
                raw_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            raw_body = exc.read().decode("utf-8", errors="replace")
            detail = self._odysseus_error_detail(raw_body)
            status = int(exc.code)
            try:
                reason = HTTPStatus(status).phrase
            except ValueError:
                reason = "HTTP error"
            error = f"Odysseus HTTP {status} {reason}"
            if detail:
                error = f"{error}: {detail}"
            return self._error_reply(
                error,
                duration_ms,
                raw={"status": status, "endpoint": endpoint, "detail": detail},
            )
        except (TimeoutError, socket.timeout) as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._error_reply(
                f"Odysseus request timed out after {self._timeout()} seconds",
                duration_ms,
                raw={"endpoint": endpoint, "exception_type": exc.__class__.__name__},
            )
        except urllib.error.URLError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._error_reply(
                f"Odysseus connection failed: {exc.reason}",
                duration_ms,
                raw={"endpoint": endpoint, "exception_type": exc.__class__.__name__},
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._error_reply(
                f"Odysseus request failed: {exc}",
                duration_ms,
                raw={"endpoint": endpoint, "exception_type": exc.__class__.__name__},
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        if status < 200 or status >= 300:
            return self._error_reply(
                f"Odysseus HTTP {status}",
                duration_ms,
                raw={"status": status, "endpoint": endpoint},
            )

        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            return self._error_reply(
                f"Odysseus returned invalid JSON: {exc}",
                duration_ms,
                raw={"status": status, "endpoint": endpoint, "body_preview": raw_body[:1000]},
            )
        if not isinstance(parsed, dict):
            return self._error_reply(
                "Odysseus returned unexpected JSON shape",
                duration_ms,
                raw={"status": status, "endpoint": endpoint},
            )

        response_text = parsed.get("response")
        if not isinstance(response_text, str) or not response_text.strip():
            return self._error_reply(
                "Odysseus response missing non-empty response field",
                duration_ms,
                raw={
                    "status": status,
                    "endpoint": endpoint,
                    "session_id": parsed.get("session_id"),
                    "model": parsed.get("model"),
                },
            )

        raw = {
            "status": status,
            "endpoint": endpoint,
            "session_id": parsed.get("session_id"),
            "model": parsed.get("model"),
        }
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=True,
            body=response_text.strip(),
            duration_ms=duration_ms,
            external_reference=str(parsed.get("session_id")) if parsed.get("session_id") else None,
            raw=raw,
        )
