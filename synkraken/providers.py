from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
import re
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import new_id
from .vault import CredentialVault


class ProviderError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Provider redirected the request; configure its final API URL")


@dataclass(slots=True)
class ModelReply:
    message: dict
    usage: dict
    finish_reason: str


def local_endpoint(url: str) -> bool:
    host = urlsplit(url).hostname
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


class ProviderRegistry:
    def __init__(self, storage) -> None:
        self.storage = storage
        self._lock = Lock()
        self.credentials = storage.sqlite_path.parent / (storage.sqlite_path.name + ".credentials")
        self.vault = CredentialVault(self.credentials)

    def _key(self, provider: dict) -> str:
        if provider.get("api_key_env"):
            return os.environ.get(provider["api_key_env"], "")
        reference = provider["provider_id"]
        if self.vault.contains(reference):
            return self.vault.get(reference)["api_key"]
        path = self.credentials / reference
        if path.is_file():
            secret = path.read_text(encoding="utf-8")
            self.vault.put(reference, {"api_key": secret})
            path.unlink()
            return secret
        return ""

    def get(self, provider_id: str) -> dict:
        provider = self.storage.get_provider(provider_id)
        if provider is None:
            raise ProviderError("Provider connection not found")
        provider["credential_ready"] = (bool(os.environ.get(provider.get("api_key_env", "")))
            if provider.get("api_key_env") else self.vault.contains(provider["provider_id"]) or
            (self.credentials / provider["provider_id"]).is_file()) or local_endpoint(provider["base_url"])
        return provider

    def list(self) -> list[dict]:
        return [self.get(provider["provider_id"]) for provider in self.storage.list_providers()]

    def save(self, payload: dict, provider_id: str | None = None) -> dict:
        allowed = {"name", "protocol", "base_url", "api_key_env", "api_key", "enabled"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("Invalid provider fields")
        with self._lock:
            before = self.get(provider_id) if provider_id else {}
            fields = {key: payload.get(key, before.get(key, "")) for key in allowed - {"api_key"}}
            for key in ("name", "protocol", "base_url", "api_key_env"):
                if not isinstance(fields[key], str) or len(fields[key]) > 500:
                    raise ValueError(f"Invalid {key}")
                fields[key] = fields[key].strip()
            fields["enabled"] = payload.get("enabled", before.get("enabled", True))
            if not isinstance(fields["enabled"], bool) or not fields["name"]:
                raise ValueError("Provider name and boolean enabled state required")
            if fields["protocol"] not in {"openai_compatible", "anthropic"}:
                raise ValueError("Unsupported provider protocol")
            fields["base_url"] = fields["base_url"].rstrip("/")
            url = urlsplit(fields["base_url"])
            if not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("Use an API base URL without credentials, query or fragment")
            if url.scheme != "https" and not (url.scheme == "http" and local_endpoint(fields["base_url"])):
                raise ValueError("Remote providers require HTTPS; local providers may use HTTP")
            env = fields["api_key_env"]
            if env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", env):
                raise ValueError("Invalid credential environment variable name")
            key = payload.get("api_key")
            if key is not None and (not isinstance(key, str) or len(key) > 4096 or "\n" in key or "\r" in key):
                raise ValueError("Invalid API key")
            if before and before["base_url"] != fields["base_url"] and not key:
                raise ValueError("Create a new connection or supply a new key when changing its endpoint")
            fields["provider_id"] = provider_id or new_id()
            if key:
                if env:
                    raise ValueError("Choose a saved key or environment variable, not both")
                self.vault.put(fields["provider_id"], {"api_key": key})
            self.storage.save_provider(fields)
        return self.get(fields["provider_id"])

    def client(self, provider_id: str) -> ProviderClient:
        provider = self.get(provider_id)
        if not provider["enabled"]:
            raise ProviderError("Provider connection is disabled")
        if not provider["credential_ready"]:
            raise ProviderError("Provider API key is missing; open Providers to configure it")
        return ProviderClient(provider, self._key(provider))

    def probe(self, provider_id: str) -> dict:
        client = self.client(provider_id)
        result = client.request("/models", None, 15)
        models = result.get("data", [])
        if not isinstance(models, list):
            raise ProviderError("Provider returned an invalid model list")
        return {"ok": True, "models": [item["id"] for item in models[:500]
                                       if isinstance(item, dict) and isinstance(item.get("id"), str)]}


class ProviderClient:
    def __init__(self, provider: dict, api_key: str) -> None:
        self.provider = provider
        self.api_key = api_key

    def request(self, path: str, payload: dict | None, timeout: float) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.provider["protocol"] == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            if self.api_key:
                headers["x-api-key"] = self.api_key
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps(payload).encode() if payload is not None else None
        if body is not None and len(body) > 1_000_000:
            raise ProviderError("Provider request exceeds context budget")
        req = Request(self.provider["base_url"] + path, data=body, headers=headers)
        try:
            with build_opener(NoRedirect()).open(req, timeout=max(.1, timeout)) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError("Provider response exceeds size limit")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ProviderError("Provider returned an invalid response")
            return result
        except HTTPError as exc:
            if exc.code == 402:
                if urlsplit(self.provider['base_url']).hostname in {'api.minimax.io', 'api.minimaxi.com'}:
                    raise ProviderError("MiniMax could not fund this request (HTTP 402). If you have a Coding/Token Plan, use its Subscription Key rather than a pay-as-you-go API key. Check your plan quota and model access.") from None
                raise ProviderError("Provider billing or credit limit prevented this request (HTTP 402). Check the account and plan associated with this connection.") from None
            if exc.code == 401:
                raise ProviderError("Provider sign-in was rejected (HTTP 401). Reconnect with a valid credential.") from None
            if exc.code == 429:
                raise ProviderError("Provider usage or rate limit reached (HTTP 429). Check your allowance or try again later.") from None
            raise ProviderError(f"Provider HTTP {exc.code}; check credentials, model and endpoint") from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("Provider connection failed or timed out") from None
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("Provider returned invalid JSON") from None

    def complete(self, model: str, messages: list[dict], tools: list[dict], timeout: float, required_tool: str | None = None) -> ModelReply:
        if required_tool and required_tool not in {tool['name'] for tool in tools}:
            raise ProviderError('Required tool is not available')
        if self.provider["protocol"] == "anthropic":
            return self._anthropic(model, messages, tools, timeout, required_tool)
        payload = {"model": model, "messages": messages, "stream": False}
        token_field = "max_completion_tokens" if urlsplit(self.provider["base_url"]).hostname == "api.openai.com" else "max_tokens"
        payload[token_field] = 4096
        if tools:
            payload["tools"] = [{"type": "function", "function": tool} for tool in tools]
        if required_tool:
            payload['tool_choice'] = {'type': 'function', 'function': {'name': required_tool}}
        result = self.request("/chat/completions", payload, timeout)
        try:
            choice = result["choices"][0]
            raw = choice["message"]
            message = {"role": "assistant", "content": raw.get("content") or raw.get("refusal") or ""}
            if raw.get("reasoning_content"):
                message["reasoning_content"] = raw["reasoning_content"]
            if raw.get("tool_calls"):
                message["tool_calls"] = raw["tool_calls"]
            return ModelReply(message, result.get("usage") or {}, choice.get("finish_reason") or "stop")
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError("Provider response has no valid assistant message") from None

    def _anthropic(self, model: str, messages: list[dict], tools: list[dict], timeout: float, required_tool: str | None = None) -> ModelReply:
        system = "\n".join(item["content"] for item in messages if item["role"] == "system")
        converted = []
        for item in messages:
            if item["role"] == "system":
                continue
            if item["role"] == "tool":
                content = [{"type": "tool_result", "tool_use_id": item["tool_call_id"], "content": item["content"]}]
                if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                    converted[-1]["content"].extend(content)
                else:
                    converted.append({"role": "user", "content": content})
            elif item.get("_anthropic_content") is not None:
                converted.append({"role": "assistant", "content": item["_anthropic_content"]})
            else:
                converted.append({"role": item["role"], "content": item["content"]})
        payload = {"model": model, "system": system, "messages": converted, "max_tokens": 4096}
        if tools:
            payload["tools"] = [{"name": tool["name"], "description": tool["description"],
                                 "input_schema": tool["parameters"]} for tool in tools]
        if required_tool:
            payload['tool_choice'] = {'type': 'tool', 'name': required_tool}
        result = self.request("/messages", payload, timeout)
        content = result.get("content")
        if not isinstance(content, list):
            raise ProviderError("Provider returned no content blocks")
        try:
            message = {"role": "assistant", "content": "\n".join(
                block["text"] for block in content if block["type"] == "text"), "_anthropic_content": content}
            calls = [{"id": block["id"], "type": "function", "function": {
                "name": block["name"], "arguments": json.dumps(block["input"]),
            }} for block in content if block["type"] == "tool_use"]
            if calls:
                message["tool_calls"] = calls
            return ModelReply(message, result.get("usage") or {}, result.get("stop_reason") or "end_turn")
        except (KeyError, TypeError):
            raise ProviderError("Provider returned malformed content blocks") from None
