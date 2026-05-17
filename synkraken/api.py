from __future__ import annotations

import re
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty
from urllib.parse import parse_qs, unquote, urlparse
import json

from .fabric import AgentFabric


_ROOM_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FabricRequestHandler(BaseHTTPRequestHandler):
    fabric: AgentFabric

    server_version = "synkraken/0.1"

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
        path = parsed.path

        if path == "/health":
            self._send(HTTPStatus.OK, self.fabric.health())
            return
        if path == "/v1/agents":
            self._send(HTTPStatus.OK, {"agents": self.fabric.list_agents()})
            return
        if path == "/v1/conversations":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [10])[0])
            self._send(HTTPStatus.OK, self.fabric.storage.list_recent_conversations(limit=limit))
            return
        if path == "/v1/deliveries":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [10])[0])
            self._send(HTTPStatus.OK, self.fabric.storage.list_recent_deliveries(limit=limit))
            return
        if path == "/v1/dead-letters":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [10])[0])
            self._send(HTTPStatus.OK, self.fabric.storage.list_dead_letters(limit=limit))
            return
        if path == "/v1/events/stream":
            self._stream_events()
            return
        if path.startswith("/v1/conversations/"):
            conversation_id = path.split("/v1/conversations/", 1)[1]
            self._send(HTTPStatus.OK, self.fabric.storage.get_conversation(conversation_id))
            return

        # ── rooms ────────────────────────────────────────────────────────
        if path == "/v1/rooms":
            self._send(HTTPStatus.OK, {"rooms": self.fabric.storage.list_rooms()})
            return
        m = re.fullmatch(r"/v1/rooms/([^/]+)/messages", path)
        if m:
            room = unquote(m.group(1))
            if not self.fabric.storage.room_exists(room):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, {
                "room": room,
                "messages": self.fabric.storage.get_room_messages(room, limit=limit),
            })
            return
        m = re.fullmatch(r"/v1/rooms/([^/]+)", path)
        if m:
            room = unquote(m.group(1))
            data = self.fabric.storage.get_room(room)
            if not data:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self._send(HTTPStatus.OK, data)
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
        path = parsed.path

        if path == "/v1/messages":
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

        # ── rooms ────────────────────────────────────────────────────────
        if path == "/v1/rooms":
            try:
                payload = self._read_json()
                name = str(payload.get("name", "")).strip().lower()
                if not _ROOM_NAME_RE.match(name):
                    raise ValueError("room name must be lowercase alphanumeric (- and _ allowed), max 63 chars")
                if self.fabric.storage.room_exists(name):
                    raise ValueError(f"room already exists: {name}")
                desc = str(payload.get("description", "")).strip()
                members = payload.get("members") or []
                if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
                    raise ValueError("members must be a list of adapter ids")
                self.fabric.storage.create_room(
                    name=name, description=desc, created_at=_utc_now_iso(), members=members,
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, self.fabric.storage.get_room(name))
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)/members", path)
        if m:
            room = unquote(m.group(1))
            try:
                payload = self._read_json()
                adapter_id = str(payload.get("adapter_id", "")).strip()
                if not adapter_id:
                    raise ValueError("adapter_id required")
                if not self.fabric.storage.room_exists(room):
                    raise ValueError(f"room not found: {room}")
                self.fabric.storage.add_room_member(room, adapter_id, _utc_now_iso())
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, self.fabric.storage.get_room(room))
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        m = re.fullmatch(r"/v1/rooms/([^/]+)/members/([^/]+)", path)
        if m:
            room = unquote(m.group(1))
            adapter_id = unquote(m.group(2))
            self.fabric.storage.remove_room_member(room, adapter_id)
            data = self.fabric.storage.get_room(room) or {"room": room, "removed": adapter_id}
            self._send(HTTPStatus.OK, data)
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)", path)
        if m:
            room = unquote(m.group(1))
            self.fabric.storage.delete_room(room)
            self._send(HTTPStatus.OK, {"deleted": room})
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def serve(fabric: AgentFabric, host: str, port: int) -> None:
    class BoundHandler(FabricRequestHandler):
        pass

    BoundHandler.fabric = fabric
    with ThreadingHTTPServer((host, port), BoundHandler) as httpd:
        print(f"synkraken listening on http://{host}:{port}")
        httpd.serve_forever()
