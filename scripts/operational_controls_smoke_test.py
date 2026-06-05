#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage


class EchoAdapter:
    def __init__(self, adapter_id: str) -> None:
        self.adapter_id = adapter_id

    def health(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "runtime_name": self.adapter_id,
            "type": "echo",
            "enabled": True,
        }

    def send(self, message: FabricMessage) -> AdapterReply:
        return AdapterReply(
            adapter_id=self.adapter_id,
            ok=True,
            body=f"echo: {message.body}",
            duration_ms=1,
        )


def _json(url: str) -> dict:
    with urlopen(url, timeout=10) as resp:
        return json.load(resp)


def _post(url: str, payload: dict) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.load(resp)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "synkraken.sqlite3")
        fabric = AgentFabric({"adapters": {}}, storage)
        fabric.adapters["echo"] = EchoAdapter("echo")
        storage.sync_agents([fabric.adapters["echo"].health()])

        class Handler(FabricRequestHandler):
            pass

        Handler.fabric = fabric
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            preset = _post(f"{base}/v1/rooms/preset", {"name": "ops", "preset": "ops"})
            assert preset["room"]["name"] == "ops"
            assert preset["memory"]["purpose"]

            note = _post(f"{base}/v1/rooms/ops/messages", {
                "source": "operator",
                "body": "Investigate failed echo delivery",
            })
            assert note["message"]["target"] == "room:ops"
            found = _json(f"{base}/v1/rooms/ops/messages?q=failed")
            assert len(found["messages"]) == 1
            summary = _post(f"{base}/v1/rooms/ops/summary", {"actor": "operator"})
            assert "failed echo delivery" in summary["summary"]
            assert "failed echo delivery" in summary["memory"]["notes"]
            proposed = _post(f"{base}/v1/memory/propose", {
                "content": "Use trace before retrying failed deliveries",
                "memory_type": "rule",
                "room_name": "ops",
                "auto_review": False,
            })
            edited = _post(f"{base}/v1/memory/{proposed['memory']['memory_id']}/edit", {
                "actor": "operator",
                "content": "Use trace before replaying failed deliveries",
            })
            assert edited["memory"]["content"] == "Use trace before replaying failed deliveries"

            msg = FabricMessage(
                message_id="msg-failed",
                conversation_id="conv-failed",
                source="operator",
                target="echo",
                body="retry this",
            ).normalized()
            storage.save_message(msg)
            storage.save_delivery(
                msg.message_id,
                AdapterReply(adapter_id="echo", ok=False, error="timeout", body=""),
                "2026-05-24T10:01:01+00:00",
                status="timeout",
            )
            storage.save_dead_letter(
                msg.message_id,
                "echo",
                "timeout",
                {"message": msg.to_dict()},
                "2026-05-24T10:01:02+00:00",
            )

            trace = _json(f"{base}/v1/trace/conv-failed")
            assert trace["id"] == "conv-failed"
            assert trace["summary"]["failure_count"] == 2
            assert trace["deliveries"]
            assert trace["dead_letters"]

            retry = _post(f"{base}/v1/deliveries/1/retry", {"actor": "operator"})
            assert retry["deliveries"][0]["ok"] is True
            replay = _post(f"{base}/v1/dead-letters/1/replay", {"actor": "operator"})
            assert replay["deliveries"][0]["ok"] is True
        finally:
            server.shutdown()
            thread.join(timeout=5)

    print("operational controls smoke test: ok")


if __name__ == "__main__":
    main()
