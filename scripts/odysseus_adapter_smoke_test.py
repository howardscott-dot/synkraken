#!/usr/bin/env python3
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.adapters.odysseus import OdysseusAdapter
from synkraken.fabric import AgentFabric
from synkraken.models import FabricMessage
from synkraken.storage import Storage


class FakeOdysseusState:
    def __init__(self) -> None:
        self.mode = "success"
        self.headers: dict[str, str] = {}
        self.payload: dict = {}


class FakeOdysseusHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        state: FakeOdysseusState = self.server.state
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        state.headers = {key: value for key, value in self.headers.items()}
        try:
            state.payload = json.loads(raw)
        except json.JSONDecodeError:
            state.payload = {}

        if self.path != "/api/v1/chat":
            self._write_json(404, {"detail": "not found"})
            return
        if state.mode == "error":
            self._write_json(401, {"detail": "invalid token"})
            return
        if state.mode == "malformed":
            body = b"{not-json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._write_json(200, {
            "response": "ODY_OK",
            "session_id": "session-123",
            "model": state.payload.get("model"),
        })

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


class FakeOdysseusServer:
    def __init__(self) -> None:
        self.state = FakeOdysseusState()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOdysseusHandler)
        self.server.state = self.state
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOdysseusServer":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def build_adapter(base_url: str, *, token_env: str = "ODYSSEUS_TEST_TOKEN") -> OdysseusAdapter:
    return OdysseusAdapter("odysseus", {
        "type": "odysseus",
        "runtime_name": "Odysseus Test",
        "base_url": base_url,
        "token_env": token_env,
        "model": "mistral-small:latest",
        "timeout_seconds": 2,
    })


def test_successful_chat() -> None:
    os.environ["ODYSSEUS_TEST_TOKEN"] = "ody_test_token"
    with FakeOdysseusServer() as fake:
        adapter = build_adapter(fake.base_url)
        reply = adapter.send(FabricMessage(
            source="operator",
            target="odysseus",
            body="hello odysseus",
            metadata={"odysseus_session_id": "session-existing"},
        ))
        assert reply.ok is True, reply.error
        assert reply.body == "ODY_OK"
        assert reply.external_reference == "session-123"
        assert reply.raw["session_id"] == "session-123"
        assert reply.raw["model"] == "mistral-small:latest"
        assert fake.state.headers.get("Authorization") == "Bearer ody_test_token"
        assert fake.state.payload["message"] == "hello odysseus"
        assert fake.state.payload["model"] == "mistral-small:latest"
        assert fake.state.payload["session"] == "session-existing"
        assert "ody_test_token" not in json.dumps(reply.to_dict())


def test_non_200_error() -> None:
    os.environ["ODYSSEUS_TEST_TOKEN"] = "ody_test_token"
    with FakeOdysseusServer() as fake:
        fake.state.mode = "error"
        reply = build_adapter(fake.base_url).send(FabricMessage(
            source="operator",
            target="odysseus",
            body="hello",
        ))
        assert reply.ok is False
        assert reply.error is not None
        assert "401" in reply.error
        assert "invalid token" in reply.error
        assert "ody_test_token" not in json.dumps(reply.to_dict())


def test_malformed_json() -> None:
    os.environ["ODYSSEUS_TEST_TOKEN"] = "ody_test_token"
    with FakeOdysseusServer() as fake:
        fake.state.mode = "malformed"
        reply = build_adapter(fake.base_url).send(FabricMessage(
            source="operator",
            target="odysseus",
            body="hello",
        ))
        assert reply.ok is False
        assert reply.error is not None
        assert "invalid JSON" in reply.error


def test_connection_failure() -> None:
    os.environ["ODYSSEUS_TEST_TOKEN"] = "ody_test_token"
    reply = build_adapter("http://127.0.0.1:9").send(FabricMessage(
        source="operator",
        target="odysseus",
        body="hello",
    ))
    assert reply.ok is False
    assert reply.error is not None
    assert "connection failed" in reply.error.lower() or "request failed" in reply.error.lower()


def test_missing_token() -> None:
    os.environ.pop("ODYSSEUS_TEST_TOKEN", None)
    reply = build_adapter("http://127.0.0.1:7000").send(FabricMessage(
        source="operator",
        target="odysseus",
        body="hello",
    ))
    assert reply.ok is False
    assert reply.error is not None
    assert "token missing" in reply.error.lower()


def test_direct_token_fallback_and_fabric_registration() -> None:
    os.environ.pop("ODYSSEUS_TEST_TOKEN", None)
    with FakeOdysseusServer() as fake, tempfile.TemporaryDirectory() as tmp:
        config = {
            "adapters": {
                "odysseus": {
                    "type": "odysseus",
                    "runtime_name": "Odysseus Test",
                    "base_url": fake.base_url,
                    "token_env": "ODYSSEUS_TEST_TOKEN",
                    "token": "ody_direct_token",
                    "model": "mistral-small:latest",
                    "timeout_seconds": 2,
                    "enabled": True,
                }
            },
            "routing": {"retry_limit": 0},
        }
        storage = Storage(Path(tmp) / "odysseus.sqlite3")
        fabric = AgentFabric(config, storage)
        result = fabric.dispatch({
            "source": "operator",
            "target": "odysseus",
            "body": "fabric hello",
        })
        assert result["deliveries"][0]["ok"] is True
        assert result["deliveries"][0]["external_reference"] == "session-123"
        assert fake.state.headers.get("Authorization") == "Bearer ody_direct_token"
        assert "ody_direct_token" not in json.dumps(result)


def main() -> None:
    test_successful_chat()
    test_non_200_error()
    test_malformed_json()
    test_connection_failure()
    test_missing_token()
    test_direct_token_fallback_and_fabric_registration()
    print("odysseus adapter smoke test: ok")


if __name__ == "__main__":
    main()
