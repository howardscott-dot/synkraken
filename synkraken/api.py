from __future__ import annotations

import re
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty
from urllib.parse import parse_qs, unquote, urlparse
import json
from uuid import uuid4

from .fabric import AgentFabric
from .models import new_id


_ROOM_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')
_TASK_STATUSES = {"open", "in_progress", "blocked", "done"}
_TASK_PRIORITIES = {"low", "normal", "high"}
_MEMORY_STATUSES = {"proposed", "approved", "peer_approved", "rejected", "archived"}
_DECISION_STATUSES = {"proposed", "approved", "rejected", "superseded"}
_HANDOFF_STATUSES = {"pending", "accepted", "rejected", "completed"}
_PROPOSAL_STATUSES = {"proposed", "approved", "rejected", "executed", "expired", "cancelled"}
_MISSION_STATUSES = {"proposed", "active", "blocked", "review", "completed", "cancelled"}
_OUTCOME_STATUSES = {"not_started", "in_progress", "review", "completed", "blocked", "cancelled"}
_ASSIGNMENT_STATUSES = {"assigned", "in_progress", "waiting", "blocked", "handoff", "review", "completed", "cancelled"}
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

    def _query_param(self, key: str, default: str = "") -> str:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        return qs.get(key, [default])[0]

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
        if path == "/v1/workforce":
            self._send(HTTPStatus.OK, self.fabric.workforce())
            return
        if path == "/v1/workforce/presence":
            self._send(HTTPStatus.OK, self.fabric.workforce_presence())
            return
        if path == "/v1/workforce/health":
            self._send(HTTPStatus.OK, self.fabric.storage.workforce_summary())
            return
        if path == "/v1/briefing":
            self._send(HTTPStatus.OK, self.fabric.storage.operator_briefing())
            return
        if path == "/v1/cookbook":
            self._send(HTTPStatus.OK, self.fabric.storage.workforce_cookbook())
            return
        if path == "/v1/arena-runs":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, {"arena_runs": self.fabric.storage.list_arena_runs(limit=limit)})
            return
        m = re.fullmatch(r"/v1/arena-runs/([^/]+)", path)
        if m:
            arena_run_id = unquote(m.group(1))
            run = self.fabric.storage.get_arena_run(arena_run_id)
            if not run:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"arena run not found: {arena_run_id}"})
                return
            self._send(HTTPStatus.OK, run)
            return
        if path == "/v1/research-runs":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, {"research_runs": self.fabric.storage.list_research_runs(limit=limit)})
            return
        m = re.fullmatch(r"/v1/research-runs/([^/]+)", path)
        if m:
            research_run_id = unquote(m.group(1))
            run = self.fabric.storage.get_research_run(research_run_id)
            if not run:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"research run not found: {research_run_id}"})
                return
            self._send(HTTPStatus.OK, run)
            return
        if path == "/v1/runbooks":
            qs = parse_qs(parsed.query)
            self._send(HTTPStatus.OK, {
                "runbooks": self.fabric.storage.list_runbooks(
                    status=qs.get("status", [None])[0],
                    limit=int(qs.get("limit", [50])[0]),
                )
            })
            return
        m = re.fullmatch(r"/v1/runbooks/([^/]+)", path)
        if m:
            runbook_id = unquote(m.group(1))
            runbook = self.fabric.storage.get_runbook(runbook_id)
            if not runbook:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"runbook not found: {runbook_id}"})
                return
            self._send(HTTPStatus.OK, runbook)
            return
        if path == "/v1/artifacts":
            qs = parse_qs(parsed.query)
            self._send(HTTPStatus.OK, {
                "artifacts": self.fabric.storage.list_artifacts(
                    status=qs.get("status", [None])[0],
                    limit=int(qs.get("limit", [50])[0]),
                )
            })
            return
        m = re.fullmatch(r"/v1/artifacts/([^/]+)", path)
        if m:
            artifact_id = unquote(m.group(1))
            artifact = self.fabric.storage.get_artifact(artifact_id)
            if not artifact:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"artifact not found: {artifact_id}"})
                return
            self._send(HTTPStatus.OK, artifact)
            return
        if path == "/v1/evidence":
            qs = parse_qs(parsed.query)
            self._send(HTTPStatus.OK, {"evidence": self.fabric.storage.list_evidence(limit=int(qs.get("limit", [50])[0]))})
            return
        m = re.fullmatch(r"/v1/evidence/([^/]+)", path)
        if m:
            evidence_id = unquote(m.group(1))
            evidence = self.fabric.storage.get_evidence(evidence_id)
            if not evidence:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"evidence not found: {evidence_id}"})
                return
            self._send(HTTPStatus.OK, evidence)
            return
        if path == "/v1/approvals":
            qs = parse_qs(parsed.query)
            self._send(HTTPStatus.OK, {
                "approvals": self.fabric.storage.list_approvals(
                    status=qs.get("status", [None])[0],
                    limit=int(qs.get("limit", [50])[0]),
                )
            })
            return
        m = re.fullmatch(r"/v1/approvals/([^/]+)", path)
        if m:
            approval_id = unquote(m.group(1))
            approval = self.fabric.storage.get_approval(approval_id)
            if not approval:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"approval not found: {approval_id}"})
                return
            self._send(HTTPStatus.OK, approval)
            return
        m = re.fullmatch(r"/v1/workforce/([^/]+)/assignments", path)
        if m:
            worker_id = unquote(m.group(1))
            self._send(HTTPStatus.OK, self.fabric.storage.worker_assignments(worker_id))
            return
        if path == "/v1/activity/recent":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, self.fabric.recent_activity(limit=limit))
            return
        if path == "/v1/activity/live":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, self.fabric.live_activity(
                limit=limit,
                runtime=qs.get("runtime", [None])[0],
                room=qs.get("room", [None])[0],
                event_type=qs.get("event_type", qs.get("type", [None]))[0],
                mission=qs.get("mission", qs.get("mission_id", [None]))[0],
                outcome=qs.get("outcome", qs.get("outcome_id", [None]))[0],
                assignment=qs.get("assignment", qs.get("assignment_id", [None]))[0],
                active_missions=str(qs.get("active_missions", [""])[0]).lower() in {"1", "true", "yes"},
            ))
            return
        if path == "/v1/canvas/relationships":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [500])[0])
            self._send(HTTPStatus.OK, {"relationships": self.fabric.storage.list_canvas_relationships(limit=limit)})
            return
        if path == "/v1/missions":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            limit = int(qs.get("limit", [100])[0])
            if status and status not in _MISSION_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid mission status"})
                return
            self._send(HTTPStatus.OK, {"missions": self.fabric.storage.list_missions(status=status, limit=limit)})
            return
        if path == "/v1/missions/summary":
            self._send(HTTPStatus.OK, self.fabric.storage.mission_summary())
            return
        if path == "/v1/outcomes":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            mission_id = qs.get("mission", qs.get("mission_id", [None]))[0]
            limit = int(qs.get("limit", [100])[0])
            if status and status not in _OUTCOME_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid outcome status"})
                return
            self._send(HTTPStatus.OK, {"outcomes": self.fabric.storage.list_outcomes(status=status, mission_id=mission_id, limit=limit)})
            return
        if path == "/v1/outcomes/summary":
            self._send(HTTPStatus.OK, self.fabric.storage.outcome_summary())
            return
        if path == "/v1/assignments":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            owner = qs.get("owner", qs.get("owner_worker", [None]))[0]
            contributor = qs.get("contributor", qs.get("contributor_worker", [None]))[0]
            mission_id = qs.get("mission", qs.get("mission_id", [None]))[0]
            outcome_id = qs.get("outcome", qs.get("outcome_id", [None]))[0]
            room_id = qs.get("room", qs.get("room_id", [None]))[0]
            limit = int(qs.get("limit", [100])[0])
            if status and status not in _ASSIGNMENT_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid assignment status"})
                return
            self._send(HTTPStatus.OK, {"assignments": self.fabric.storage.list_assignments(
                status=status,
                owner_worker=owner,
                contributor_worker=contributor,
                mission_id=mission_id,
                outcome_id=outcome_id,
                room_id=room_id,
                limit=limit,
            )})
            return
        if path == "/v1/assignments/summary":
            self._send(HTTPStatus.OK, self.fabric.storage.assignment_summary())
            return
        if path == "/v1/handoffs/recent":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            self._send(HTTPStatus.OK, {"handoffs": self.fabric.storage.recent_assignment_handoffs(limit=limit)})
            return
        m = re.fullmatch(r"/v1/assignments/([^/]+)/activity", path)
        if m:
            assignment_id = unquote(m.group(1))
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            activity = self.fabric.storage.assignment_activity(assignment_id, limit=limit)
            if activity is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                return
            self._send(HTTPStatus.OK, {"assignment_id": assignment_id, "activity": activity})
            return
        m = re.fullmatch(r"/v1/assignments/([^/]+)/handoffs", path)
        if m:
            assignment_id = unquote(m.group(1))
            if not self.fabric.storage.get_assignment(assignment_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                return
            self._send(HTTPStatus.OK, {"assignment_id": assignment_id, "handoffs": self.fabric.storage.assignment_handoffs(assignment_id)})
            return
        m = re.fullmatch(r"/v1/assignments/([^/]+)/proposals", path)
        if m:
            assignment_id = unquote(m.group(1))
            if not self.fabric.storage.get_assignment(assignment_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                return
            self._send(HTTPStatus.OK, {"assignment_id": assignment_id, "proposals": self.fabric.storage.assignment_proposals(assignment_id)})
            return
        m = re.fullmatch(r"/v1/assignments/([^/]+)/traces", path)
        if m:
            assignment_id = unquote(m.group(1))
            if not self.fabric.storage.get_assignment(assignment_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                return
            self._send(HTTPStatus.OK, {"assignment_id": assignment_id, "traces": self.fabric.storage.assignment_traces(assignment_id)})
            return
        m = re.fullmatch(r"/v1/assignments/([^/]+)", path)
        if m:
            assignment_id = unquote(m.group(1))
            assignment = self.fabric.storage.get_assignment(assignment_id)
            if not assignment:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                return
            self._send(HTTPStatus.OK, assignment)
            return
        m = re.fullmatch(r"/v1/outcomes/([^/]+)/activity", path)
        if m:
            outcome_id = unquote(m.group(1))
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            activity = self.fabric.storage.outcome_activity(outcome_id, limit=limit)
            if activity is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"outcome not found: {outcome_id}"})
                return
            self._send(HTTPStatus.OK, {"outcome_id": outcome_id, "activity": activity})
            return
        m = re.fullmatch(r"/v1/outcomes/([^/]+)/workers", path)
        if m:
            outcome_id = unquote(m.group(1))
            if not self.fabric.storage.get_outcome(outcome_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"outcome not found: {outcome_id}"})
                return
            self._send(HTTPStatus.OK, {"outcome_id": outcome_id, "workers": self.fabric.storage.outcome_workers(outcome_id)})
            return
        m = re.fullmatch(r"/v1/outcomes/([^/]+)/incidents", path)
        if m:
            outcome_id = unquote(m.group(1))
            if not self.fabric.storage.get_outcome(outcome_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"outcome not found: {outcome_id}"})
                return
            self._send(HTTPStatus.OK, {"outcome_id": outcome_id, "incidents": self.fabric.storage.outcome_incidents(outcome_id)})
            return
        m = re.fullmatch(r"/v1/outcomes/([^/]+)/proposals", path)
        if m:
            outcome_id = unquote(m.group(1))
            if not self.fabric.storage.get_outcome(outcome_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"outcome not found: {outcome_id}"})
                return
            self._send(HTTPStatus.OK, {"outcome_id": outcome_id, "proposals": self.fabric.storage.outcome_proposals(outcome_id)})
            return
        m = re.fullmatch(r"/v1/outcomes/([^/]+)/assignments", path)
        if m:
            outcome_id = unquote(m.group(1))
            assignments = self.fabric.storage.outcome_assignments(outcome_id)
            if assignments is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"outcome not found: {outcome_id}"})
                return
            self._send(HTTPStatus.OK, {"outcome_id": outcome_id, "assignments": assignments})
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)/activity", path)
        if m:
            mission_id = unquote(m.group(1))
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            activity = self.fabric.storage.mission_activity(mission_id, limit=limit)
            if activity is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, {"mission_id": mission_id, "activity": activity})
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)/workers", path)
        if m:
            mission_id = unquote(m.group(1))
            if not self.fabric.storage.get_mission(mission_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, {"mission_id": mission_id, "workers": self.fabric.storage.mission_workers(mission_id)})
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)/incidents", path)
        if m:
            mission_id = unquote(m.group(1))
            if not self.fabric.storage.get_mission(mission_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, {"mission_id": mission_id, "incidents": self.fabric.storage.mission_incidents(mission_id)})
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)/proposals", path)
        if m:
            mission_id = unquote(m.group(1))
            if not self.fabric.storage.get_mission(mission_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, {"mission_id": mission_id, "proposals": self.fabric.storage.mission_proposals(mission_id)})
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)/assignments", path)
        if m:
            mission_id = unquote(m.group(1))
            assignments = self.fabric.storage.mission_assignments(mission_id)
            if assignments is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, {"mission_id": mission_id, "assignments": assignments})
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)/outcomes", path)
        if m:
            mission_id = unquote(m.group(1))
            if not self.fabric.storage.get_mission(mission_id):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, {"mission_id": mission_id, "outcomes": self.fabric.storage.list_mission_outcomes(mission_id)})
            return
        m = re.fullmatch(r"/v1/outcomes/([^/]+)", path)
        if m:
            outcome_id = unquote(m.group(1))
            outcome = self.fabric.storage.get_outcome(outcome_id)
            if not outcome:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"outcome not found: {outcome_id}"})
                return
            self._send(HTTPStatus.OK, outcome)
            return
        m = re.fullmatch(r"/v1/missions/([^/]+)", path)
        if m:
            mission_id = unquote(m.group(1))
            mission = self.fabric.storage.get_mission(mission_id)
            if not mission:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"mission not found: {mission_id}"})
                return
            self._send(HTTPStatus.OK, mission)
            return
        m = re.fullmatch(r"/v1/runtime/([^/]+)/reputation", path)
        if m:
            runtime_id = unquote(m.group(1))
            reputation = self.fabric.storage.get_runtime_reputation(runtime_id)
            if not reputation:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"runtime not found: {runtime_id}"})
                return
            self._send(HTTPStatus.OK, {"reputation": reputation})
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
        m = re.fullmatch(r"/v1/trace/([^/]+)", path)
        if m:
            trace_id = unquote(m.group(1))
            self._send(HTTPStatus.OK, self.fabric.get_trace(trace_id))
            return
        if path == "/v1/tasks":
            qs = parse_qs(parsed.query)
            room = qs.get("room", [None])[0]
            self._send(HTTPStatus.OK, {"tasks": self.fabric.storage.list_tasks(room_name=room)})
            return
        if path == "/v1/proposals":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            room = qs.get("room", qs.get("room_id", [None]))[0]
            task = qs.get("task", qs.get("task_id", [None]))[0]
            goal = qs.get("goal", qs.get("goal_id", [None]))[0]
            limit = int(qs.get("limit", [50])[0])
            if status and status not in _PROPOSAL_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid proposal status"})
                return
            self._send(HTTPStatus.OK, {
                "proposals": self.fabric.storage.list_proposals(
                    status=status,
                    room_id=room,
                    task_id=task,
                    goal_id=goal,
                    limit=limit,
                )
            })
            return
        if path == "/v1/proposals/pending":
            self._send(HTTPStatus.OK, {"proposals": self.fabric.storage.list_proposals(status="proposed", limit=100)})
            return
        m = re.fullmatch(r"/v1/proposal/([^/]+)", path) or re.fullmatch(r"/v1/proposals/([^/]+)", path)
        if m:
            proposal_id = unquote(m.group(1))
            proposal = self.fabric.storage.get_proposal(proposal_id)
            if not proposal:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"proposal not found: {proposal_id}"})
                return
            proposal["events"] = self.fabric.storage.list_proposal_events(proposal_id) or []
            self._send(HTTPStatus.OK, proposal)
            return
        if path == "/v1/memory":
            qs = parse_qs(parsed.query)
            status = qs.get("status", [None])[0]
            memory_type = qs.get("type", [None])[0] or qs.get("memory_type", [None])[0]
            scope_type = qs.get("scope_type", [None])[0]
            scope_id = qs.get("scope_id", [None])[0]
            importance = qs.get("importance", [None])[0]
            room = qs.get("room", [None])[0]
            workspace = qs.get("workspace", [None])[0]
            limit = int(qs.get("limit", [50])[0])
            if status and status not in _MEMORY_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid memory status"})
                return
            self._send(HTTPStatus.OK, {
                "memories": self.fabric.storage.list_shared_memory(
                    status=status,
                    memory_type=memory_type,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    importance=importance,
                    room_name=room,
                    workspace=workspace,
                    limit=limit,
                )
            })
            return
        if path == "/v1/memory/pending":
            self._send(HTTPStatus.OK, {
                "memories": self.fabric.storage.list_shared_memory(status="proposed", limit=100)
            })
            return
        if path == "/v1/memory/context":
            qs = parse_qs(parsed.query)
            result = self.fabric.memory_context({
                "scope_type": qs.get("scope_type", ["global"])[0],
                "scope_id": qs.get("scope_id", [None])[0],
                "max_items": qs.get("max_items", [None])[0],
                "max_chars": qs.get("max_chars", [None])[0],
            })
            self._send(HTTPStatus.OK, result)
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
            query = qs.get("q", [""])[0]
            messages = (
                self.fabric.storage.search_room_messages(room, query, limit=limit)
                if query
                else self.fabric.storage.get_room_messages(room, limit=limit)
            )
            self._send(HTTPStatus.OK, {
                "room": room,
                "query": query,
                "messages": messages,
            })
            return
        m = re.fullmatch(r"/v1/rooms/([^/]+)/members", path)
        if m:
            room = unquote(m.group(1))
            data = self.fabric.storage.get_room(room)
            if not data:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self._send(HTTPStatus.OK, {"room": room, "members": data.get("members", [])})
            return
        m = re.fullmatch(r"/v1/rooms/([^/]+)/assignments", path)
        if m:
            room = unquote(m.group(1))
            assignments = self.fabric.storage.room_assignments(room)
            if assignments is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self._send(HTTPStatus.OK, {"room": room, "assignments": assignments})
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
            room = qs.get("room", qs.get("room_id", [None]))[0]
            status_q = qs.get("status", [None])[0]
            agent = qs.get("agent", [None])[0]
            limit = int(qs.get("limit", [50])[0])
            if status_q and status_q not in _HANDOFF_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid handoff status"})
                return
            self._send(HTTPStatus.OK, {
                "handoffs": self.fabric.storage.list_handoffs(room_id=room, status=status_q, agent=agent, limit=limit)
            })
            return
        if path == "/v1/handoff/latest":
            qs = parse_qs(parsed.query)
            room = qs.get("room", qs.get("room_id", [None]))[0]
            status_q = qs.get("status", [None])[0]
            if status_q and status_q not in _HANDOFF_STATUSES:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid handoff status"})
                return
            handoff = self.fabric.storage.latest_handoff(room_id=room, status=status_q)
            if not handoff:
                self._send(HTTPStatus.NOT_FOUND, {"error": "no handoffs found"})
                return
            handoff["events"] = self.fabric.storage.list_handoff_events(handoff["id"]) or []
            self._send(HTTPStatus.OK, handoff)
            return
        m = re.fullmatch(r"/v1/handoff/([^/]+)", path) or re.fullmatch(r"/v1/handoffs/([^/]+)", path)
        if m:
            handoff_id = unquote(m.group(1))
            handoff = self.fabric.storage.get_handoff(handoff_id)
            if not handoff:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"handoff not found: {handoff_id}"})
                return
            handoff["events"] = self.fabric.storage.list_handoff_events(handoff_id) or []
            self._send(HTTPStatus.OK, handoff)
            return

        # ── projects ────────────────────────────────────────────────────────
        m = re.fullmatch(r"/v1/projects", path)
        if m:
            self.do_GET_PROJECTS()
            return
        m = re.fullmatch(r"/v1/projects/([^/]+)", path)
        if m:
            self.do_GET_PROJECT_ITEM(m.group(1))
            return

        # ── flight recorder ──────────────────────────────────────────────
        m = re.fullmatch(r"/v1/replay/([^/]+)", path)
        if m:
            replay_id = unquote(m.group(1))
            self._send(HTTPStatus.OK, self.fabric.get_replay(replay_id))
            return
        if path == "/v1/incident/latest":
            self._send(HTTPStatus.OK, self.fabric.get_latest_incident())
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
                target = str(payload.get("target") or "")
                if target.startswith("room:"):
                    room = target[len("room:"):]
                    if not self.fabric.storage.room_exists(room):
                        self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                        return
                result = self.fabric.dispatch(payload)
            except KeyError as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": f"missing_field: {exc.args[0]}"})
                return
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path == "/v1/arena-runs":
            try:
                payload = self._read_json()
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    raise ValueError("prompt required")
                agents = payload.get("agents") or []
                if not isinstance(agents, list) or not all(isinstance(agent, str) for agent in agents):
                    raise ValueError("agents must be a list of worker ids")
                if not agents:
                    agents = [
                        item.get("adapter_id")
                        for item in self.fabric.list_agents()
                        if item.get("enabled", True) and item.get("adapter_id")
                    ]
                if not agents:
                    raise ValueError("no workers available for arena run")
                arena_run_id = str(payload.get("arena_run_id") or payload.get("id") or new_id()).strip()
                self.fabric.storage.create_arena_run(arena_run_id, prompt, agents)
                deliveries = []
                for agent in agents:
                    result = self.fabric.dispatch({
                        "source": "arena",
                        "target": agent,
                        "body": prompt,
                        "metadata": {"arena_run_id": arena_run_id, "phase": "arena"},
                    })
                    deliveries.extend(result.get("deliveries") or [])
                ok_deliveries = [item for item in deliveries if item.get("ok")]
                winner = str(payload.get("winner_agent") or (ok_deliveries[0].get("adapter_id") if ok_deliveries else "") or "")
                reason = "first successful delivery; use /v1/arena-runs/{id}/judge to override" if winner else "no successful deliveries"
                run = self.fabric.storage.update_arena_run(
                    arena_run_id,
                    status="completed" if ok_deliveries else "failed",
                    winner_agent=winner,
                    judge_reason=reason,
                    result={"deliveries": deliveries},
                    completed_at=_utc_now_iso(),
                )
                self.fabric.storage.record_arena_event(arena_run_id, "completed", "arena", {"winner_agent": winner})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, run or {})
            return

        m = re.fullmatch(r"/v1/arena-runs/([^/]+)/judge", path)
        if m:
            arena_run_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                winner = str(payload.get("winner_agent") or "").strip()
                reason = str(payload.get("reason") or payload.get("judge_reason") or "").strip()
                if not winner:
                    raise ValueError("winner_agent required")
                run = self.fabric.storage.update_arena_run(
                    arena_run_id,
                    status="judged",
                    winner_agent=winner,
                    judge_reason=reason,
                    completed_at=_utc_now_iso(),
                )
                if not run:
                    self._send(HTTPStatus.NOT_FOUND, {"error": f"arena run not found: {arena_run_id}"})
                    return
                self.fabric.storage.record_arena_event(arena_run_id, "judged", str(payload.get("actor", "operator")), {"winner_agent": winner, "reason": reason})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, run)
            return

        if path == "/v1/research-runs":
            try:
                payload = self._read_json()
                question = str(payload.get("question") or payload.get("prompt") or "").strip()
                if not question:
                    raise ValueError("question required")
                agents = payload.get("agents") or []
                if not isinstance(agents, list) or not all(isinstance(agent, str) for agent in agents):
                    raise ValueError("agents must be a list of worker ids")
                if not agents:
                    agents = [
                        item.get("adapter_id")
                        for item in self.fabric.list_agents()
                        if item.get("enabled", True) and item.get("adapter_id")
                    ][:4]
                if not agents:
                    raise ValueError("no workers available for research run")
                research_run_id = str(payload.get("research_run_id") or payload.get("id") or new_id()).strip()
                room = str(payload.get("room") or payload.get("room_name") or f"research-{research_run_id[:8]}").strip().lower()
                if not _ROOM_NAME_RE.match(room):
                    raise ValueError("room name must be lowercase alphanumeric (- and _ allowed), max 63 chars")
                if not self.fabric.storage.room_exists(room):
                    self.fabric.storage.create_room(room, f"Research: {question[:80]}", _utc_now_iso(), members=agents)
                else:
                    for agent in agents:
                        self.fabric.add_room_member(room, agent, actor="research")
                self.fabric.storage.create_research_run(research_run_id, question, room_name=room, agents=agents)
                result = self.fabric.dispatch({
                    "source": "research",
                    "target": f"room:{room}",
                    "body": f"Research question:\n{question}\n\nReturn evidence, risks, and a concise recommendation.",
                    "metadata": {"research_run_id": research_run_id, "phase": "research"},
                })
                deliveries = result.get("deliveries") or []
                report_lines = [f"# Research: {question}", ""]
                for delivery in deliveries:
                    report_lines.append(f"## {delivery.get('adapter_id')}")
                    report_lines.append(delivery.get("body") or delivery.get("error") or "(no response)")
                    report_lines.append("")
                run = self.fabric.storage.update_research_run(
                    research_run_id,
                    status="completed" if any(item.get("ok") for item in deliveries) else "failed",
                    report="\n".join(report_lines).strip(),
                    result={"dispatch": result},
                    completed_at=_utc_now_iso(),
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, run or {})
            return

        if path == "/v1/runbooks":
            try:
                payload = self._read_json()
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("title required")
                steps = payload.get("steps") or []
                if isinstance(steps, str):
                    steps = [line.strip() for line in steps.splitlines() if line.strip()]
                if not isinstance(steps, list) or not all(isinstance(step, str) for step in steps):
                    raise ValueError("steps must be a list of strings")
                runbook = self.fabric.storage.create_runbook(
                    str(payload.get("runbook_id") or payload.get("id") or new_id()),
                    title,
                    purpose=str(payload.get("purpose", "")).strip(),
                    steps=steps,
                    status=str(payload.get("status", "draft")).strip() or "draft",
                    owner=str(payload.get("owner", "")).strip(),
                    risk_level=str(payload.get("risk_level", "medium")).strip() or "medium",
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, runbook)
            return

        m = re.fullmatch(r"/v1/runbooks/([^/]+)/(approve|reject|apply)", path)
        if m:
            runbook_id = unquote(m.group(1))
            action = m.group(2)
            status = {"approve": "approved", "reject": "rejected", "apply": "applied"}[action]
            runbook = self.fabric.storage.update_runbook_status(runbook_id, status)
            if not runbook:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"runbook not found: {runbook_id}"})
                return
            self._send(HTTPStatus.OK, runbook)
            return

        if path == "/v1/artifacts":
            try:
                payload = self._read_json()
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("title required")
                artifact = self.fabric.storage.create_artifact(
                    str(payload.get("artifact_id") or payload.get("id") or new_id()),
                    title,
                    artifact_type=str(payload.get("artifact_type") or payload.get("type") or "note").strip() or "note",
                    body=str(payload.get("body", "")),
                    status=str(payload.get("status", "draft")).strip() or "draft",
                    owner=str(payload.get("owner", "")).strip(),
                    source=payload.get("source") if isinstance(payload.get("source"), dict) else {},
                    metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, artifact)
            return

        if path == "/v1/evidence":
            try:
                payload = self._read_json()
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("title required")
                evidence = self.fabric.storage.create_evidence(
                    str(payload.get("evidence_id") or payload.get("id") or new_id()),
                    title,
                    uri=str(payload.get("uri", "")).strip(),
                    summary=str(payload.get("summary", "")).strip(),
                    source_type=str(payload.get("source_type", "manual")).strip() or "manual",
                    linked_object_type=str(payload.get("linked_object_type", "")).strip(),
                    linked_object_id=str(payload.get("linked_object_id", "")).strip(),
                    metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, evidence)
            return

        if path == "/v1/approvals":
            try:
                payload = self._read_json()
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("title required")
                approval = self.fabric.storage.create_approval(
                    str(payload.get("approval_id") or payload.get("id") or new_id()),
                    title,
                    approval_type=str(payload.get("approval_type") or payload.get("type") or "operator").strip() or "operator",
                    requested_by=str(payload.get("requested_by", "operator")).strip() or "operator",
                    reason=str(payload.get("reason", "")).strip(),
                    linked_object_type=str(payload.get("linked_object_type", "")).strip(),
                    linked_object_id=str(payload.get("linked_object_id", "")).strip(),
                    payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
                )
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, approval)
            return

        m = re.fullmatch(r"/v1/approvals/([^/]+)/(approve|reject)", path)
        if m:
            approval_id = unquote(m.group(1))
            action = m.group(2)
            try:
                payload = self._read_json()
                approval = self.fabric.storage.resolve_approval(
                    approval_id,
                    "approved" if action == "approve" else "rejected",
                    str(payload.get("actor", "operator")).strip() or "operator",
                )
                if not approval:
                    self._send(HTTPStatus.NOT_FOUND, {"error": f"approval not found: {approval_id}"})
                    return
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, approval)
            return

        if path == "/v1/assignments":
            try:
                payload = self._read_json()
                title = str(payload.get("title", "")).strip()
                if not title:
                    raise ValueError("title required")
                owner_worker = str(payload.get("owner_worker") or payload.get("owner") or "").strip()
                if not owner_worker:
                    raise ValueError("owner_worker required")
                status = str(payload.get("status", "assigned")).strip()
                if status not in _ASSIGNMENT_STATUSES:
                    raise ValueError("invalid assignment status")
                contributors = payload.get("contributor_workers") or payload.get("contributors") or []
                if not isinstance(contributors, list) or not all(isinstance(item, str) for item in contributors):
                    raise ValueError("contributor_workers must be a list of worker ids")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                assignment = self.fabric.storage.create_assignment(
                    assignment_id=str(payload.get("id") or payload.get("assignment_id") or "").strip() or new_id(),
                    title=title,
                    description=str(payload.get("description", "")).strip(),
                    status=status,
                    owner_worker=owner_worker,
                    contributor_workers=contributors,
                    mission_id=str(payload.get("mission_id") or "").strip() or None,
                    outcome_id=str(payload.get("outcome_id") or "").strip() or None,
                    room_id=str(payload.get("room_id") or payload.get("room") or "").strip() or None,
                    actor=actor,
                    created_at=_utc_now_iso(),
                )
                self.fabric.event_bus.publish("assignment.created", {"assignment_id": assignment["assignment_id"], "owner_worker": owner_worker})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, assignment)
            return

        m = re.fullmatch(r"/v1/assignments/([^/]+)/contributors", path)
        if m:
            assignment_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                worker_id = str(payload.get("worker_id") or payload.get("adapter_id") or "").strip()
                if not worker_id:
                    raise ValueError("worker_id required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                assignment = self.fabric.storage.add_assignment_contributor(assignment_id, worker_id, actor=actor)
                if assignment is None:
                    self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                    return
                self.fabric.event_bus.publish("assignment.contributor_added", {"assignment_id": assignment_id, "worker_id": worker_id})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, assignment)
            return

        m = re.fullmatch(r"/v1/assignments/([^/]+)/handoff", path)
        if m:
            assignment_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                to_worker = str(payload.get("to_worker") or payload.get("to_agent") or "").strip()
                if not to_worker:
                    raise ValueError("to_worker required")
                reason = str(payload.get("reason", "")).strip()
                if not reason:
                    raise ValueError("reason required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                result = self.fabric.storage.create_assignment_handoff(
                    assignment_id,
                    to_worker=to_worker,
                    reason=reason,
                    context_summary=str(payload.get("context_summary", "")).strip(),
                    actor=actor,
                    created_at=_utc_now_iso(),
                )
                if result is None:
                    self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                    return
                self.fabric.event_bus.publish("assignment.handoff", {"assignment_id": assignment_id, "to_worker": to_worker})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path == "/v1/proposal/create":
            try:
                payload = self._read_json()
                result = self.fabric.create_proposal(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path in {
            "/v1/proposal/approve",
            "/v1/proposal/reject",
            "/v1/proposal/cancel",
            "/v1/proposal/execute",
        }:
            action = path.rsplit("/", 1)[1]
            try:
                payload = self._read_json()
                proposal_id = str(payload.get("id") or payload.get("proposal_id") or "").strip()
                if not proposal_id:
                    raise ValueError("proposal_id required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if action == "approve":
                    result = self.fabric.approve_proposal(proposal_id, actor)
                elif action == "reject":
                    result = self.fabric.reject_proposal(proposal_id, actor, str(payload.get("reason", "")).strip() or None)
                elif action == "cancel":
                    result = self.fabric.cancel_proposal(proposal_id, actor, str(payload.get("reason", "")).strip() or None)
                else:
                    result = self.fabric.execute_proposal(proposal_id, actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/deliveries/(\d+)/retry", path)
        if m:
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                result = self.fabric.replay_delivery(int(m.group(1)), actor=actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/dead-letters/(\d+)/replay", path)
        if m:
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                result = self.fabric.replay_dead_letter(int(m.group(1)), actor=actor)
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

        if path == "/v1/memory/operator-note":
            try:
                payload = self._read_json()
                result = self.fabric.create_operator_memory_note(payload)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        if path in {"/v1/memory/approve", "/v1/memory/reject", "/v1/memory/archive"}:
            try:
                payload = self._read_json()
                memory_id = str(payload.get("memory_id") or payload.get("id") or "").strip()
                if not memory_id:
                    raise ValueError("memory_id required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if path.endswith("/approve"):
                    result = self.fabric.approve_memory(memory_id, actor)
                elif path.endswith("/reject"):
                    result = self.fabric.reject_memory(memory_id, actor, str(payload.get("reason", "")).strip() or None)
                else:
                    result = self.fabric.archive_memory(memory_id, actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/memory/([^/]+)/(review|approve|reject|archive|edit)", path)
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
                elif action == "edit":
                    payload["actor"] = actor
                    result = self.fabric.edit_memory(memory_id, payload)
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

        if path == "/v1/rooms/preset":
            try:
                payload = self._read_json()
                name = str(payload.get("name") or payload.get("preset") or "").strip().lower()
                preset = str(payload.get("preset") or name).strip().lower()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if not _ROOM_NAME_RE.match(name):
                    raise ValueError("room name must be lowercase alphanumeric (- and _ allowed), max 63 chars")
                result = self.fabric.create_room_preset(name, preset, actor=actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)/members", path)
        if m:
            room = unquote(m.group(1))
            if not self.fabric.storage.room_exists(room):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            try:
                payload = self._read_json()
                adapter_id = str(payload.get("adapter_id", "")).strip()
                if not adapter_id:
                    raise ValueError("adapter_id required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                self.fabric.add_room_member(room, adapter_id, actor=actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, self.fabric.storage.get_room(room))
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)/messages", path)
        if m:
            room = unquote(m.group(1))
            if not self.fabric.storage.room_exists(room):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            try:
                payload = self._read_json()
                source = str(payload.get("source", "operator")).strip() or "operator"
                body = str(payload.get("body", "")).strip()
                result = self.fabric.record_room_note(room, source, body)
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)/summary", path)
        if m:
            room = unquote(m.group(1))
            if not self.fabric.storage.room_exists(room):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            try:
                payload = self._read_json()
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                limit = int(payload.get("limit", 50) or 50)
                result = self.fabric.summarize_room(room, actor=actor, limit=limit)
            except Exception as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
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

        if path in {"/v1/handoff/accept", "/v1/handoff/reject", "/v1/handoff/complete"}:
            action = path.rsplit("/", 1)[1]
            try:
                payload = self._read_json()
                handoff_id = str(payload.get("id") or payload.get("handoff_id") or "").strip()
                if not handoff_id:
                    raise ValueError("id required")
                actor = str(payload.get("actor", "operator")).strip() or "operator"
                if action == "accept":
                    result = self.fabric.accept_handoff(handoff_id, actor)
                elif action == "reject":
                    result = self.fabric.reject_handoff(
                        handoff_id,
                        actor,
                        str(payload.get("reason", "")).strip() or None,
                    )
                else:
                    result = self.fabric.complete_handoff(handoff_id, actor)
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
                    result = self.fabric.reject_handoff(
                        handoff_id,
                        actor,
                        str(payload.get("reason", "")).strip() or None,
                    )
                else:
                    result = self.fabric.complete_handoff(handoff_id, actor)
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, result)
            return

        # ── projects ────────────────────────────────────────────────────────
        m = re.fullmatch(r"/v1/projects", path)
        if m:
            self.do_POST_PROJECTS()
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
        m = re.fullmatch(r"/v1/assignments/([^/]+)", path)
        if m:
            assignment_id = unquote(m.group(1))
            try:
                payload = self._read_json()
                allowed = {"title", "description", "status", "owner_worker", "owner", "mission_id", "outcome_id", "room_id", "room", "actor"}
                extra = set(payload) - allowed
                if extra:
                    raise ValueError(f"unknown assignment fields: {', '.join(sorted(extra))}")
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
                    status = str(payload["status"]).strip()
                    if status not in _ASSIGNMENT_STATUSES:
                        raise ValueError("invalid assignment status")
                    fields["status"] = status
                if "owner_worker" in payload or "owner" in payload:
                    owner = str(payload.get("owner_worker") or payload.get("owner") or "").strip()
                    if not owner:
                        raise ValueError("owner_worker cannot be empty")
                    fields["owner_worker"] = owner
                if "mission_id" in payload:
                    fields["mission_id"] = str(payload["mission_id"]).strip() or None
                if "outcome_id" in payload:
                    fields["outcome_id"] = str(payload["outcome_id"]).strip() or None
                if "room_id" in payload or "room" in payload:
                    fields["room_id"] = str(payload.get("room_id") or payload.get("room") or "").strip() or None
                assignment = self.fabric.storage.update_assignment(assignment_id, fields, actor=actor, updated_at=_utc_now_iso())
                if assignment is None:
                    self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                    return
                self.fabric.event_bus.publish("assignment.updated", {"assignment_id": assignment_id})
            except Exception as exc:  # noqa: BLE001
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, assignment)
            return

        # ── projects ────────────────────────────────────────────────────────
        m = re.fullmatch(r"/v1/projects/([^/]+)", path)
        if m:
            self.do_PATCH_PROJECT_ITEM(m.group(1))
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

        m = re.fullmatch(r"/v1/assignments/([^/]+)/contributors/([^/]+)", path)
        if m:
            assignment_id = unquote(m.group(1))
            worker_id = unquote(m.group(2))
            assignment = self.fabric.storage.remove_assignment_contributor(assignment_id, worker_id, actor="operator")
            if assignment is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": f"assignment not found: {assignment_id}"})
                return
            self.fabric.event_bus.publish("assignment.contributor_removed", {"assignment_id": assignment_id, "worker_id": worker_id})
            self._send(HTTPStatus.OK, assignment)
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)/members/([^/]+)", path)
        if m:
            room = unquote(m.group(1))
            adapter_id = unquote(m.group(2))
            if not self.fabric.storage.room_exists(room):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self.fabric.remove_room_member(room, adapter_id)
            data = self.fabric.storage.get_room(room) or {"room": room, "removed": adapter_id}
            self._send(HTTPStatus.OK, data)
            return

        m = re.fullmatch(r"/v1/rooms/([^/]+)", path)
        if m:
            room = unquote(m.group(1))
            if not self.fabric.storage.room_exists(room):
                self._send(HTTPStatus.NOT_FOUND, {"error": f"room not found: {room}"})
                return
            self.fabric.storage.delete_room(room)
            self._send(HTTPStatus.OK, {"deleted": room})
            return

        # ── projects ────────────────────────────────────────────────────────
        m = re.fullmatch(r"/v1/projects/([^/]+)", path)
        if m:
            self.do_DELETE_PROJECT_ITEM(m.group(1))
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    # ── projects ────────────────────────────────────────────────────────────
    def do_GET_PROJECTS(self) -> None:
        status = self._query_param("status")
        limit = int(self._query_param("limit", "100"))
        projects = self.fabric.storage.list_projects(status=status, limit=limit)
        self._send(HTTPStatus.OK, {"projects": projects, "count": len(projects)})

    def do_GET_PROJECT_ITEM(self, project_id: str) -> None:
        project = self.fabric.storage.get_project(project_id)
        if not project:
            self._send(HTTPStatus.NOT_FOUND, {"error": "Project not found"})
            return
        self._send(HTTPStatus.OK, project)

    def do_POST_PROJECTS(self) -> None:
        try:
            payload = self._read_json()
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            project_id = str(payload.get("project_id") or uuid4().hex[:16])
            description = str(payload.get("description", ""))
            status = str(payload.get("status", "active"))
            metadata = payload.get("metadata", {})
            project = self.fabric.storage.create_project(project_id, name, description, status, metadata)
            self._send(HTTPStatus.CREATED, project)
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_PATCH_PROJECT_ITEM(self, project_id: str) -> None:
        try:
            payload = self._read_json()
            project = self.fabric.storage.update_project(project_id, **payload)
            if not project:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Project not found"})
                return
            self._send(HTTPStatus.OK, project)
        except Exception as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_DELETE_PROJECT_ITEM(self, project_id: str) -> None:
        deleted = self.fabric.storage.delete_project(project_id)
        if not deleted:
            self._send(HTTPStatus.NOT_FOUND, {"error": "Project not found"})
            return
        self._send(HTTPStatus.NO_CONTENT, {})


def serve(fabric: AgentFabric, host: str, port: int) -> None:
    class BoundHandler(FabricRequestHandler):
        pass

    BoundHandler.fabric = fabric
    with ThreadingHTTPServer((host, port), BoundHandler) as httpd:
        print(f"synkraken listening on http://{host}:{port}")
        httpd.serve_forever()
