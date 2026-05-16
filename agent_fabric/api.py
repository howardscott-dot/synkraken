from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty
from urllib.parse import parse_qs, urlparse
import json

from .fabric import AgentFabric


class FabricRequestHandler(BaseHTTPRequestHandler):
    fabric: AgentFabric

    server_version = "agent-fabric/0.1"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(HTTPStatus.OK, self.fabric.health())
            return
        if parsed.path == "/v1/agents":
            self._send(HTTPStatus.OK, {"agents": self.fabric.list_agents()})
            return
        if parsed.path == "/v1/conversations":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [10])[0])
            self._send(HTTPStatus.OK, self.fabric.storage.list_recent_conversations(limit=limit))
            return
        if parsed.path == "/v1/deliveries":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [10])[0])
            self._send(HTTPStatus.OK, self.fabric.storage.list_recent_deliveries(limit=limit))
            return
        if parsed.path == "/v1/dead-letters":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [10])[0])
            self._send(HTTPStatus.OK, self.fabric.storage.list_dead_letters(limit=limit))
            return
        if parsed.path == "/v1/events/stream":
            self._stream_events()
            return
        if parsed.path.startswith("/v1/conversations/"):
            conversation_id = parsed.path.split("/v1/conversations/", 1)[1]
            self._send(HTTPStatus.OK, self.fabric.storage.get_conversation(conversation_id))
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _stream_events(self) -> None:
        q = self.fabric.event_bus.subscribe()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        try:
            self.wfile.write(b': connected\n\n')
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15)
                    payload = json.dumps(event, ensure_ascii=False).encode('utf-8')
                    self.wfile.write(b'data: ' + payload + b'\n\n')
                    self.wfile.flush()
                except Empty:
                    self.wfile.write(b': ping\n\n')
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            self.fabric.event_bus.unsubscribe(q)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/messages":
            try:
                payload = self._read_json()
                result = self.fabric.dispatch(payload)
            except KeyError as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"missing_field: {exc.args[0]}"})
                return
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def serve(fabric: AgentFabric, host: str, port: int) -> None:
    class BoundHandler(FabricRequestHandler):
        pass

    BoundHandler.fabric = fabric
    with ThreadingHTTPServer((host, port), BoundHandler) as httpd:
        print(f"agent-fabric listening on http://{host}:{port}")
        httpd.serve_forever()
