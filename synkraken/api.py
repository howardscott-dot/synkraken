from __future__ import annotations

import re
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty
from urllib.parse import parse_qs, unquote, urlparse
import json

from .fabric import AgentFabric
from .models import new_id


_ROOM_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')
_TASK_STATUSES = {"open", "in_progress", "blocked", "done"}
_TASK_PRIORITIES = {"low", "normal", "high"}
_MEMORY_STATUSES = {"proposed", "peer_approved", "rejected", "archived"}
_DECISION_STATUSES = {"proposed", "approved", "rejected", "superseded"}
_PROFILE_FIELDS = {
    "cost_tier",
    "usage_risk",
    "preferred_roles",
    "avoid_roles",
    "capabilities",
    "speed",
    "trust",
    "actor",
}


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
        if path == "/v1/profiles":
            self._send(HTTPStatus.OK, {"profiles": self.fabric.list_agents()})
            return
        if path == "/v1/runtimes":
            self._send(HTTPStatus.OK, {"runtimes": self.fabric.list_runtimes()})
            return
        if path == "/v1/runtimes/doctor":
            self._send(HTTPStatus.OK, self.fabric.runtime_doctor())
            return
        m = re.fullmatch(r"/v1/runtimes/([^/]+)", path)
        if m:
            runtime_id = unquote(m.group(1))
            runtime = self.fabric.storage.get_runtime(runtime_id)
            if not runtime:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"runtime not found: {runtime_id}"})
                return
            self._send(HTTPStatus.OK, runtime)
            return
        if path == "/v1/flight":
            self._send(HTTPStatus.OK, self.fabric.flight_summary())
            return
        if path == "/v1/workspaces":
            self._send(HTTPStatus.OK, {"workspaces": self.fabric.storage.list_workspace_packs()})
            return
        m = re.fullmatch(r"/v1/workspaces/([^/]+)", path)
        if m:
            name = unquote(m.group(1))
            workspace = self.fabric.storage.get_workspace_pack(name)
            if not workspace:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"workspace not found: {name}"})
                return
            self._send(HTTPStatus.OK, {"workspace": workspace})
            return
        m = re.fullmatch(r"/v1/agents/([^/]+)/profile", path)
        if m:
            agent_id = unquote(m.group(1))
            agent = self.fabric.storage.get_agent(agent_id)
            if not agent:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"agent not found: {agent_id}"})
                return
            self._send(HTTPStatus.OK, {"profile": agent})
            return
        m = re.fullmatch(r"/v1/agents/([^/]+)/events", path)
        if m:
            agent_id = unquote(m.group(1))
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            events = self.fabric.storage.list_agent_events(agent_id, limit=limit)
            if events is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"agent not found: {agent_id}"})
                return
            self._send(HTTPStatus.OK, {"agent_id": agent_id, "events": events})
            return
        m = re.fullmatch(r"/v1/agents/([^/]+)", path)
        if m:
            agent_id = unquote(m.group(1))
            agent = self.fabric.storage.get_agent(agent_id)
            if not agent:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"agent not found: {agent_id}"})
                return
            self._send(HTTPStatus.OK, agent)
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
        if path == "/v1/tasks":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            self._send(HTTPStatus.OK, {"tasks": self.fabric.storage.list_tasks(room_name=room)})
            return
        if path == "/v1/memory":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            room = qs.get("room", [None])[0]
            workspace = qs.get("workspace", [None])[0]
            limit = int(qs.get("limit", [50])[0])
            if status and status not in _MEMORY_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid memory status"})
                return
            self._send(HTTPStatus.OK, {
                "memories": self.fabric.storage.list_shared_memory(
                    status=status,
                    room_name=room,
                    workspace=workspace,
                    limit=limit,
                )
            })
            return
        if path == "/v1/memory/search":
            qs = parse_qs(parsed.query)
            query = qs.get("q", [""])[0]
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, {"memories": self.fabric.storage.search_shared_memory(query, limit=limit)})
            return
        if path == "/v1/memory/budget":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            self._send(HTTPStatus.OK, self.fabric.memory_budget(room_name=room))
            return
        m = re.fullmatch(r"/v1/memory/([^/]+)/events", path)
        if m:
            memory_id = unquote(m.group(1))
            events = self.fabric.storage.list_shared_memory_events(memory_id)
            if events is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"memory not found: {memory_id}"})
                return
            self._send(HTTPStatus.OK, {"memory_id": memory_id, "events": events})
            return
        m = re.fullmatch(r"/v1/memory/([^/]+)", path)
        if m:
            memory_id = unquote(m.group(1))
            memory = self.fabric.storage.get_shared_memory(memory_id)
            if not memory:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"memory not found: {memory_id}"})
                return
            memory["events"] = self.fabric.storage.list_shared_memory_events(memory_id) or []
            self._send(HTTPStatus.OK, memory)
            return
        if path == "/v1/team-runs":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            limit = int(qs.get("limit", [25])[0])
            self._send(HTTPStatus.OK, {"team_runs": self.fabric.storage.list_team_runs(room_name=room, limit=limit)})
            return
        if path == "/v1/goal-runs":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            limit = int(qs.get("limit", [25])[0])
            self._send(HTTPStatus.OK, {"goal_runs": self.fabric.storage.list_goal_runs(room_name=room, limit=limit)})
            return
        m = re.fullmatch(r"/v1/goal-runs/([^/]+)/events", path)
        if m:
            goal_run_id = unquote(m.group(1))
            events = self.fabric.storage.list_goal_events(goal_run_id)
            if events is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"goal run not found: {goal_run_id}"})
                return
            self._send(HTTPStatus.OK, {"goal_run_id": goal_run_id, "events": events})
            return
        m = re.fullmatch(r"/v1/goal-runs/([^/]+)", path)
        if m:
            goal_run_id = unquote(m.group(1))
            run = self.fabric.storage.get_goal_run(goal_run_id)
            if not run:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"goal run not found: {goal_run_id}"})
                return
            run["events"] = self.fabric.storage.list_goal_events(goal_run_id) or []
            run["task"] = self.fabric.storage.get_task(run["linked_task_id"]) if run.get("linked_task_id") else None
            run["messages"] = [
                message for message in self.fabric.storage.get_room_messages(run["room_name"], limit=200)
                if message.get("conversation_id") == goal_run_id
            ]
            self._send(HTTPStatus.OK, run)
            return
        m = re.fullmatch(r"/v1/team-runs/([^/]+)/events", path)
        if m:
            team_run_id = unquote(m.group(1))
            events = self.fabric.storage.list_team_events(team_run_id)
            if events is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"team run not found: {team_run_id}"})
                return
            self._send(HTTPStatus.OK, {"team_run_id": team_run_id, "events": events})
            return
        m = re.fullmatch(r"/v1/team-runs/([^/]+)", path)
        if m:
            team_run_id = unquote(m.group(1))
            run = self.fabric.storage.get_team_run(team_run_id)
            if not run:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"team run not found: {team_run_id}"})
                return
            events = self.fabric.storage.list_team_events(team_run_id) or []
            run["events"] = events
            messages = self.fabric.storage.get_room_messages(run["room_name"], limit=200)
            run["messages"] = [
                message for message in messages
                if message.get("metadata", {}).get("team_run_id") == team_run_id
                or message.get("metadata", {}).get("team_task")
            ]
            timeout_event = next((event for event in reversed(events) if event.get("event_type") == "timeout"), None)
            blocked_event = next((event for event in reversed(events) if event.get("event_type") == "run_blocked"), None)
            if timeout_event:
                try:
                    timeout_detail = json.loads(timeout_event.get("detail") or "{}")
                except Exception:
                    timeout_detail = {"detail": timeout_event.get("detail")}
                run["failure_summary"] = {
                    "status": run.get("status"),
                    "team_run_id": team_run_id,
                    "phase": timeout_detail.get("phase"),
                    "agent": timeout_detail.get("agent"),
                    "elapsed_ms": timeout_detail.get("elapsed_ms"),
                    "reason": blocked_event.get("detail") if blocked_event else timeout_event.get("detail"),
                    "partial_transcript": timeout_detail.get("partial_transcript") or run["messages"],
                }
            self._send(HTTPStatus.OK, run)
            return
        m = re.fullmatch(r"/v1/tasks/([^/]+)/events", path)
        if m:
            task_id = unquote(m.group(1))
            events = self.fabric.storage.list_task_events(task_id)
            if events is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"task not found: {task_id}"})
                return
            self._send(HTTPStatus.OK, {"task_id": task_id, "events": events})
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
        m = re.fullmatch(r"/v1/rooms/([^/]+)/memory/events", path)
        if m:
            room = unquote(m.group(1))
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            events = self.fabric.storage.list_room_memory_events(room, limit=limit)
            if events is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self._send(HTTPStatus.OK, {"room": room, "events": events})
            return
        m = re.fullmatch(r"/v1/rooms/([^/]+)/memory", path)
        if m:
            room = unquote(m.group(1))
            memory = self.fabric.storage.get_room_memory(room)
            if memory is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self._send(HTTPStatus.OK, memory)
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

        # ── decisions ──────────────────────────────────────────────────
        if path == "/v1/decisions":
            qs = parse_qs(parsed.query)
            room = qs.get("room", qs.get("room_id", [None]))[0]
            status = qs.get("status", [None])[0]
            limit = int(qs.get("limit", [50])[0])
            if status and status not in _DECISION_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid decision status"})
                return
            self._send(HTTPStatus.OK, {
                "decisions": self.fabric.storage.list_decisions(room_id=room, status=status, limit=limit)
            })
            return
        if path == "/v1/decision/latest":
            qs = parse_qs(parsed.query)
            room = qs.get("room", qs.get("room_id", [None]))[0]
            decision = self.fabric.storage.latest_decision(room_id=room)
            if not decision:
                self._send(HTTPStatus.NOT_FOUND, {"error": "no decisions found"})
                return
            decision["events"] = self.fabric.storage.list_decision_events(decision["id"]) or []
            self._send(HTTPStatus.OK, decision)
            return
        m = re.fullmatch(r"/v1/decision/([^/]+)", path) or re.fullmatch(r"/v1/decisions/([^/]+)", path)
        if m:
            decision_id = unquote(m.group(1))
            decision = self.fabric.storage.get_decision(decision_id)
            if not decision:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"decision not found: {decision_id}"})
                return
            decision["events"] = self.fabric.storage.list_decision_events(decision_id) or []
            self._send(HTTPStatus.OK, decision)
            return

        # ── handoffs ─────────────────────────────────────────────────────
        if path == "/v1/handoffs":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            status_q = qs.get("status", [None])[0]
            agent = qs.get("agent", [None])[0]
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, {
                "handoffs": self.fabric.storage.list_handoffs(room_name=room, status=status_q, agent=agent, limit=limit)
            })
            return
        m = re.fullmatch(r"/v1/handoffs/([^/]+)", path)
        if m:
            handoff_id = unquote(m.group(1))
            handoff = self.fabric.storage.get_handoff(handoff_id)
            if not handoff:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"handoff not found: {handoff_id}"})
                return
            handoff["events"] = self.fabric.storage.list_handoff_events(handoff_id) or []
            self._send(HTTPStatus.OK, handoff)
            return

        # ── flight recorder ──────────────────────────────────────────────
        m = re.fullmatch(r"/v1/replay/([^/]+)", path)
        if m:
            replay_id = unquote(m.group(1))
            try:
                result = self.fabric.get_replay(replay_id)
            except ValueError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return
        if path == "/v1/incident/latest":
            incident = self.fabric.get_latest_incident()
            if not incident:
                self._send(HTTPStatus.NOT_FOUND, {"error": "no incidents found"})
                return
            self._send(HTTPStatus.OK, incident)
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

        if path == "/v1/discussions":
            try:
                payload = self._read_json()
                result = self.fabric.discuss(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path == "/v1/team-tasks":
            try:
                payload = self._read_json()
                result = self.fabric.team_task(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path == "/v1/goal-runs":
            try:
                payload = self._read_json()
                result = self.fabric.goal_run(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/goal-runs/([^/]+)/cancel", path)
        if m:
            goal_run_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                result = self.fabric.cancel_goal_run(goal_run_id, actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path == "/v1/memory/propose":
            try:
                payload = self._read_json()
                result = self.fabric.propose_memory(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/memory/([^/]+)/(review|approve|reject|archive)", path)
        if m:
            memory_id = unquote(m.group(1))
            action = m.group(2)
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if action == "review":
                    result = self.fabric.review_memory(memory_id, payload)
                elif action == "approve":
                    result = self.fabric.approve_memory(memory_id, actor)
                elif action == "reject":
                    result = self.fabric.reject_memory(memory_id, actor, str(payload.get("reason", "")).strip() or None)
                else:
                    result = self.fabric.archive_memory(memory_id, actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/team-runs/([^/]+)/(approve|reject)", path)
        if m:
            team_run_id = unquote(m.group(1))
            action = m.group(2)
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                result = (
                    self.fabric.approve_team_run(team_run_id, actor)
                    if action == "approve"
                    else self.fabric.reject_team_run(team_run_id, actor)
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path == "/v1/tasks":
            try:
                payload = self._read_json()
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("title required")
                description = str(payload.get("description", "")).strip()
                status = str(payload.get("status", "open"))
                priority = str(payload.get("priority", "normal"))
                room_name = payload.get("room_name")
                assigned_agent_id = payload.get("assigned_agent_id")
                source_message_id = payload.get("source_message_id")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if status not in _TASK_STATUSES:
                    raise ValueError("invalid task status")
                if priority not in _TASK_PRIORITIES:
                    raise ValueError("invalid task priority")
                if room_name is not None:
                    room_name = str(room_name).strip() or None
                    if room_name and not self.fabric.storage.room_exists(room_name):
                        raise ValueError(f"room not found: {room_name}")
                if assigned_agent_id is not None:
                    assigned_agent_id = str(assigned_agent_id).strip() or None
                    if assigned_agent_id and assigned_agent_id not in self.fabric.adapters:
                        raise ValueError(f"unknown agent: {assigned_agent_id}")
                if source_message_id is not None:
                    source_message_id = str(source_message_id).strip() or None
                    if source_message_id and not self.fabric.storage.message_exists(source_message_id):
                        raise ValueError(f"source message not found: {source_message_id}")
                task = self.fabric.storage.create_task(
                    task_id=new_id(),
                    title=title,
                    description=description,
                    status=status,
                    priority=priority,
                    room_name=room_name,
                    assigned_agent_id=assigned_agent_id,
                    source_message_id=source_message_id,
                    actor=actor,
                    created_at=_utc_now_iso(),
                )
                self.fabric.event_bus.publish("task.created", {"task_id": task["task_id"]})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, task)
            return

        m = re.fullmatch(r"/v1/tasks/([^/]+)/comment", path)
        if m:
            task_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                author = str(payload.get("author", "operator")).strip() or "operator"
                actor = str(payload.get("actor", author)).strip() or author
                body = str(payload.get("body", "")).strip()
                if not body:
                    raise ValueError("body required")
                task = self.fabric.storage.add_task_comment(
                    comment_id=new_id(),
                    task_id=task_id,
                    author=author,
                    body=body,
                    actor=actor,
                    created_at=_utc_now_iso(),
                )
                if task is None:
                    self._send(HTTPStatus.NOT_FOUND, {"error": f"task not found: {task_id}"})
                    return
                self.fabric.event_bus.publish("task.commented", {"task_id": task_id})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, task)
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
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                self.fabric.add_room_member(room, adapter_id, actor=actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, self.fabric.storage.get_room(room))
            return

        m = re.fullmatch(r"/v1/workspaces/(init|load|export)", path)
        if m:
            action = m.group(1)
            try:
                payload = self._read_json()
                name = str(payload.get("name") or "").strip() or None
                if action == "init":
                    result = self.fabric.init_workspace(name)
                elif action == "load":
                    result = self.fabric.load_workspace(name)
                else:
                    result = self.fabric.export_workspace(name)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        # ── decisions ──────────────────────────────────────────────────
        if path == "/v1/decision/propose":
            try:
                payload = self._read_json()
                result = self.fabric.propose_decision(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path in {"/v1/decision/approve", "/v1/decision/reject"}:
            action = path.rsplit("/", 1)[1]
            try:
                payload = self._read_json()
                decision_id = str(payload.get("id") or payload.get("decision_id") or "").strip()
                if not decision_id:
                    raise ValueError("id required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if action == "approve":
                    result = self.fabric.approve_decision(decision_id, actor)
                else:
                    result = self.fabric.reject_decision(
                        decision_id,
                        actor,
                        str(payload.get("reason", "")).strip() or None,
                    )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/decision/([^/]+)/(approve|reject)", path)
        if m:
            decision_id = unquote(m.group(1))
            action = m.group(2)
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if action == "approve":
                    result = self.fabric.approve_decision(decision_id, actor)
                else:
                    result = self.fabric.reject_decision(
                        decision_id,
                        actor,
                        str(payload.get("reason", "")).strip() or None,
                    )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        # ── handoffs ─────────────────────────────────────────────────────
        if path == "/v1/handoff":
            try:
                payload = self._read_json()
                result = self.fabric.create_handoff(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/handoff/([^/]+)/(accept|reject|complete)", path)
        if m:
            handoff_id = unquote(m.group(1))
            action = m.group(2)
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if action == "accept":
                    result = self.fabric.accept_handoff(handoff_id, actor)
                elif action == "reject":
                    result = self.fabric.reject_handoff(handoff_id, actor)
                else:
                    result = self.fabric.complete_handoff(handoff_id, actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        m = re.fullmatch(r"/v1/agents/([^/]+)/profile", path)
        if m:
            agent_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                extra = set(payload) - _PROFILE_FIELDS
                if extra:
                    raise ValueError(f"unknown profile fields: {', '.join(sorted(extra))}")
                profile = self.fabric.update_agent_profile(agent_id, payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, {"profile": profile})
            return
        m = re.fullmatch(r"/v1/tasks/([^/]+)", path)
        if not m:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        task_id = unquote(m.group(1))
        try:
            payload = self._read_json()
            allowed = {
                "title", "description", "status", "priority", "room_name",
                "assigned_agent_id", "source_message_id", "actor",
            }
            extra = set(payload) - allowed
            if extra:
                raise ValueError(f"unknown task fields: {', '.join(sorted(extra))}")
            fields: dict = {}
            actor = str(payload.get("actor", "operator")).strip() or "operator"
            if "title" in payload:
                title = str(payload["title"]).strip()
                if not title:
                    raise ValueError("title cannot be empty")
                fields["title"] = title
            if "description" in payload:
                fields["description"] = str(payload["description"]).strip()
            if "status" in payload:
                status = str(payload["status"])
                if status not in _TASK_STATUSES:
                    raise ValueError("invalid task status")
                fields["status"] = status
            if "priority" in payload:
                priority = str(payload["priority"])
                if priority not in _TASK_PRIORITIES:
                    raise ValueError("invalid task priority")
                fields["priority"] = priority
            if "room_name" in payload:
                room_name = str(payload["room_name"]).strip() if payload["room_name"] is not None else ""
                room_name = room_name or None
                if room_name and not self.fabric.storage.room_exists(room_name):
                    raise ValueError(f"room not found: {room_name}")
                fields["room_name"] = room_name
            if "assigned_agent_id" in payload:
                agent = str(payload["assigned_agent_id"]).strip() if payload["assigned_agent_id"] is not None else ""
                agent = agent or None
                if agent and agent not in self.fabric.adapters:
                    raise ValueError(f"unknown agent: {agent}")
                fields["assigned_agent_id"] = agent
            if "source_message_id" in payload:
                message_id = str(payload["source_message_id"]).strip() if payload["source_message_id"] is not None else ""
                message_id = message_id or None
                if message_id and not self.fabric.storage.message_exists(message_id):
                    raise ValueError(f"source message not found: {message_id}")
                fields["source_message_id"] = message_id
            task = self.fabric.storage.update_task(task_id, fields, actor, _utc_now_iso())
            if task is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"task not found: {task_id}"})
                return
            self.fabric.event_bus.publish("task.updated", {"task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send(HTTPStatus.OK, task)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        m = re.fullmatch(r"/v1/rooms/([^/]+)/memory", path)
        if not m:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        room = unquote(m.group(1))
        try:
            payload = self._read_json()
            allowed = {"purpose", "objective", "rules", "constraints", "current_focus", "notes", "actor", "updated_by"}
            extra = set(payload) - allowed
            if extra:
                raise ValueError(f"unknown memory fields: {', '.join(sorted(extra))}")
            actor = str(payload.get("actor") or payload.get("updated_by") or "operator").strip() or "operator"
            fields = {
                key: payload[key]
                for key in ("purpose", "objective", "rules", "constraints", "current_focus", "notes")
                if key in payload
            }
            memory = self.fabric.storage.upsert_room_memory(room, fields, actor, _utc_now_iso())
            if memory is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self.fabric.event_bus.publish("room.memory.updated", {"room": room, "updated_by": actor})
        except Exception as exc:  # noqa: BLE001
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send(HTTPStatus.OK, memory)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        m = re.fullmatch(r"/v1/rooms/([^/]+)/members/([^/]+)", path)
        if m:
            room = unquote(m.group(1))
            adapter_id = unquote(m.group(2))
            self.fabric.remove_room_member(room, adapter_id)
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
