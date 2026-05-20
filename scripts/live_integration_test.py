#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOM_NAME = "integration-test-room"
FAKE_AGENT = "__synkraken_live_fake_agent__"


class LiveTest:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.base = args.daemon_url.rstrip("/")
        self.started = datetime.now()
        root = Path(args.output_dir or "audits")
        self.output_dir = root / f"live-test-{self.started.strftime('%Y%m%d-%H%M%S')}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.commands_log = self.output_dir / "commands.log"
        self.raw_path = self.output_dir / "raw.json"
        self.report_path = self.output_dir / "report.md"
        self.raw: dict[str, Any] = {
            "started_at": self.started.isoformat(),
            "daemon_url": self.base,
            "checks": [],
            "commands": [],
            "http": [],
            "fanout_diagnostics": [],
        }
        self.failures: list[str] = []
        self.skips: list[str] = []
        self.agents: list[str] = []
        self.direct_durations: dict[str, int] = {}
        self.broadcast_replies = 0
        self.room_replies = 0
        self.discussion_result = "not run"
        self.task_id = ""
        self.team_task_id = ""
        self.goal_run_id = ""
        self.presence_checked = 0
        self.memory_id = ""

    def log_command(self, command: list[str], returncode: int, stdout: str, stderr: str, duration: float) -> None:
        entry = {
            "command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": round(duration, 3),
        }
        self.raw["commands"].append(entry)
        with self.commands_log.open("a", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(command)}\n")
            fh.write(f"# exit={returncode} duration={duration:.3f}s\n")
            if stdout:
                fh.write(stdout.rstrip() + "\n")
            if stderr:
                fh.write("[stderr]\n" + stderr.rstrip() + "\n")
            fh.write("\n")

    def run_command(self, command: list[str], *, required: bool = True) -> subprocess.CompletedProcess[str]:
        start = time.time()
        try:
            proc = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=self.args.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            proc = subprocess.CompletedProcess(command, 127, "", str(exc))
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
            proc = subprocess.CompletedProcess(command, 124, stdout, stderr or f"timeout after {self.args.timeout}s")
        duration = time.time() - start
        self.log_command(command, proc.returncode, proc.stdout, proc.stderr, duration)
        if required and proc.returncode != 0:
            self.fail(f"command failed: {' '.join(command)}")
        return proc

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None,
                *, required: bool = True, timeout: float | None = None) -> tuple[int, dict[str, Any]]:
        url = self.base + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        started = time.time()
        status = 0
        body: dict[str, Any] = {}
        error = ""
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.args.timeout) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
                body = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"error": raw}
            error = body.get("error", raw)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            body = {"error": error}
        entry = {
            "method": method,
            "path": path,
            "status": status,
            "payload": payload,
            "response": body,
            "error": error,
            "duration_seconds": round(time.time() - started, 3),
        }
        self.raw["http"].append(entry)
        if required and not (200 <= status < 300):
            self.fail(f"{method} {path} failed: {status} {error or body}")
        return status, body

    def pass_check(self, name: str, detail: str = "") -> None:
        self.raw["checks"].append({"name": name, "status": "PASS", "detail": detail})

    def fail(self, detail: str) -> None:
        self.failures.append(detail)
        self.raw["checks"].append({"name": detail, "status": "FAIL", "detail": detail})

    def skip(self, name: str, detail: str) -> None:
        self.skips.append(f"{name}: {detail}")
        self.raw["checks"].append({"name": name, "status": "SKIPPED", "detail": detail})

    def synkraken_command(self, *parts: str, required: bool = True) -> subprocess.CompletedProcess[str]:
        exe = shutil.which("synkraken")
        if not exe:
            self.fail("synkraken CLI not found on PATH")
            return subprocess.CompletedProcess(["synkraken", *parts], 127, "", "synkraken not found")
        command = [exe, *parts]
        if parts and parts[0] in {"status", "health", "agents"}:
            command.extend(["--url", self.base])
        return self.run_command(command, required=required)

    def choose_agents(self, agents_data: dict[str, Any]) -> list[str]:
        configured = [
            str(agent.get("adapter_id"))
            for agent in agents_data.get("agents", [])
            if agent.get("adapter_id") and agent.get("enabled", True)
        ]
        if self.args.agents:
            requested = [item.strip() for item in self.args.agents.split(",") if item.strip()]
            missing = [agent for agent in requested if agent not in configured]
            if missing:
                self.fail(f"requested agents not configured/enabled: {', '.join(missing)}")
            return [agent for agent in requested if agent in configured]
        return configured

    def send_message(self, target: str, body: str, *, required: bool = True,
                     metadata: dict[str, Any] | None = None,
                     timeout: float | None = None) -> dict[str, Any]:
        message_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "message_id": message_id,
            "source": "live-integration-test",
            "target": target,
            "body": body,
        }
        if metadata:
            payload["metadata"] = metadata
        _status, result = self.request("POST", "/v1/messages", payload, required=required, timeout=timeout or self.args.timeout)
        result.setdefault("message", {}).setdefault("message_id", message_id)
        result = self.hydrate_message_result_after_timeout(target, message_id, result)
        return result

    def hydrate_message_result_after_timeout(self, target: str, message_id: str,
                                             result: dict[str, Any]) -> dict[str, Any]:
        if result.get("deliveries") or result.get("routing"):
            return result
        if str(result.get("error", "")).lower() != "timed out":
            return result
        deadline = time.time() + 45
        transcript: dict[str, Any] = {}
        while time.time() < deadline:
            _status, transcript = self.request(
                "GET",
                f"/v1/conversations/{urllib.parse.quote(message_id)}",
                required=False,
                timeout=10,
            )
            if transcript.get("deliveries"):
                break
            time.sleep(2)
        deliveries = []
        for delivery in transcript.get("deliveries", []):
            deliveries.append({
                "adapter_id": delivery.get("adapter_id"),
                "ok": bool(delivery.get("ok")),
                "error": delivery.get("error"),
                "duration_ms": delivery.get("duration_ms"),
                "attempts": delivery.get("attempts"),
                "message_id": delivery.get("message_id"),
                "conversation_id": message_id,
                "original_target": target,
                "delivery_target": delivery.get("adapter_id"),
                "reply_context": target if target.startswith("room:") else None,
                "status": "replied" if delivery.get("ok") else delivery.get("status", "failed"),
                "body_preview": delivery.get("body", "")[:160],
            })
        if not deliveries:
            return result
        result["message"] = {
            "message_id": message_id,
            "conversation_id": message_id,
            "target": target,
        }
        result["routing"] = {
            "requested_target": target,
            "resolved_targets": [str(delivery.get("adapter_id")) for delivery in transcript.get("deliveries", [])],
            "reply_context": target if target.startswith("room:") else None,
            "transcript_target": target if target == "broadcast" or target.startswith("room:") else None,
            "recovered_after_client_timeout": True,
        }
        result["deliveries"] = deliveries
        result["dead_letters"] = transcript.get("dead_letters", [])
        result["recovered_after_client_timeout"] = True
        return result

    def record_fanout_diagnostics(self, label: str, result: dict[str, Any]) -> None:
        message = result.get("message") if isinstance(result.get("message"), dict) else {}
        message_id = str(message.get("message_id") or "")
        conversation_id = str(message.get("conversation_id") or message_id)
        diagnostics: dict[str, Any] = {
            "label": label,
            "message_id": message_id,
            "conversation_id": conversation_id,
            "requested_target": (result.get("routing") or {}).get("requested_target") or message.get("target"),
            "resolved_targets": (result.get("routing") or {}).get("resolved_targets", []),
            "reply_context": (result.get("routing") or {}).get("reply_context"),
            "transcript_target": (result.get("routing") or {}).get("transcript_target"),
            "memory_context": (result.get("routing") or {}).get("memory_context"),
            "deliveries_created": len(result.get("deliveries", [])),
            "deliveries": [],
            "dead_letters": result.get("dead_letters", []),
        }
        for delivery in result.get("deliveries", []):
            diagnostics["deliveries"].append({
                "delivery_target": delivery.get("delivery_target") or delivery.get("adapter_id"),
                "status": delivery.get("status"),
                "ok": delivery.get("ok"),
                "reply_context": delivery.get("reply_context"),
                "reply_message_id": delivery.get("reply_message_id"),
                "persisted_transcript_target": delivery.get("persisted_transcript_target"),
                "duration_ms": delivery.get("duration_ms"),
                "error": delivery.get("error"),
            })
        if conversation_id:
            _status, transcript = self.request(
                "GET",
                f"/v1/conversations/{urllib.parse.quote(conversation_id)}",
                required=False,
                timeout=10,
            )
            diagnostics["persisted_messages"] = [
                {
                    "message_id": item.get("message_id"),
                    "source": item.get("source"),
                    "target": item.get("target"),
                    "reply_to": item.get("reply_to"),
                    "body_preview": str(item.get("body", ""))[:120],
                }
                for item in transcript.get("messages", [])
            ]
        self.raw["fanout_diagnostics"].append(diagnostics)

    def record_discussion_diagnostics(self, result: dict[str, Any]) -> None:
        conversation_id = str(result.get("conversation_id") or result.get("discussion_id") or "")
        diagnostics: dict[str, Any] = {
            "label": "discussion",
            "conversation_id": conversation_id,
            "status": result.get("status"),
            "agents": result.get("agents", []),
            "turns": result.get("turns", []),
            "deliveries_created": len(result.get("deliveries", [])),
            "memory_context": result.get("memory_context"),
            "deliveries": [],
            "dead_letters": result.get("dead_letters", []),
        }
        for delivery in result.get("deliveries", []):
            diagnostics["deliveries"].append({
                "delivery_target": delivery.get("delivery_target") or delivery.get("adapter_id"),
                "status": delivery.get("status"),
                "ok": delivery.get("ok"),
                "reply_context": delivery.get("reply_context"),
                "duration_ms": delivery.get("duration_ms"),
                "error": delivery.get("error"),
            })
        if conversation_id:
            _status, transcript = self.request(
                "GET",
                f"/v1/conversations/{urllib.parse.quote(conversation_id)}",
                required=False,
                timeout=10,
            )
            diagnostics["persisted_messages"] = [
                {
                    "message_id": item.get("message_id"),
                    "source": item.get("source"),
                    "target": item.get("target"),
                    "reply_to": item.get("reply_to"),
                    "body_preview": str(item.get("body", ""))[:120],
                }
                for item in transcript.get("messages", [])
            ]
        self.raw["fanout_diagnostics"].append(diagnostics)

    def ensure_room(self) -> None:
        payload = {"name": ROOM_NAME, "description": "SynKraken live integration test room", "members": self.agents}
        status, result = self.request("POST", "/v1/rooms", payload, required=False)
        if 200 <= status < 300:
            self.pass_check("room created", ROOM_NAME)
        elif "already exists" in str(result.get("error", "")).lower():
            self.pass_check("room exists", ROOM_NAME)
        else:
            self.fail(f"room create failed: {result}")
        for agent in self.agents:
            self.request("POST", f"/v1/rooms/{urllib.parse.quote(ROOM_NAME)}/members", {"adapter_id": agent}, required=False)

    def ensure_room_memory(self) -> None:
        room_path = urllib.parse.quote(ROOM_NAME)
        _status, memory = self.request("PUT", f"/v1/rooms/{room_path}/memory", {
            "purpose": "Exercise SynKraken live room context",
            "objective": "Verify Room Memory v0.1 persistence and injection",
            "rules": "Keep the test local and bounded",
            "constraints": "No cloud sync, embeddings, or autonomous planning",
            "current_focus": "Room Memory live integration",
            "notes": "Created by scripts/live_integration_test.py",
            "actor": "live-integration-test",
        })
        if memory.get("objective") == "Verify Room Memory v0.1 persistence and injection":
            self.pass_check("room memory updated", ROOM_NAME)
        else:
            self.fail(f"room memory update returned unexpected payload: {memory}")
        _status, fetched = self.request("GET", f"/v1/rooms/{room_path}/memory")
        if fetched.get("current_focus") == "Room Memory live integration":
            self.pass_check("room memory fetched", ROOM_NAME)
        else:
            self.fail(f"room memory fetch mismatch: {fetched}")
        _status, events = self.request("GET", f"/v1/rooms/{room_path}/memory/events?limit=20")
        if events.get("events"):
            self.pass_check("room memory events", str(len(events.get("events", []))))
        else:
            self.fail("room memory events empty")

    def shared_memory_flow(self) -> None:
        if len(self.agents) < 2:
            self.skip("shared memory", "fewer than two agents for peer review")
            return
        proposer = self.agents[0]
        reviewer = self.agents[1]
        content = f"Live integration memory {self.started.isoformat()}: keep shared memory peer-reviewed and bounded."
        status, proposed = self.request("POST", "/v1/memory/propose", {
            "created_by": proposer,
            "room_name": ROOM_NAME,
            "memory_type": "rule",
            "content": content,
            "auto_review": False,
        }, required=False, timeout=max(self.args.timeout, 120))
        if not (200 <= status < 300):
            self.fail(f"shared memory propose failed: {status} {proposed.get('error', proposed)}")
            return
        memory = proposed.get("memory") or {}
        self.memory_id = str(memory.get("memory_id") or "")
        status, reviewed = self.request("POST", f"/v1/memory/{urllib.parse.quote(self.memory_id)}/review", {
            "reviewer": reviewer,
            "review": "Decision: approve\nConfidence: 90\nMemory type: rule\nReason: durable bounded integration-test memory",
        }, required=False, timeout=max(self.args.timeout, 120))
        if not (200 <= status < 300):
            self.fail(f"shared memory review failed: {status} {reviewed.get('error', reviewed)}")
            return
        memory = reviewed.get("memory") or {}
        if memory.get("status") == "peer_approved":
            self.pass_check("shared memory peer approved", self.memory_id)
        else:
            self.fail(f"shared memory was not peer approved: {memory}")
            return
        _status, fetched = self.request("GET", f"/v1/memory/{urllib.parse.quote(self.memory_id)}", required=False)
        if fetched.get("memory_id") == self.memory_id and fetched.get("events"):
            self.pass_check("shared memory fetched", f"{len(fetched.get('events', []))} events")
        else:
            self.fail(f"shared memory fetch mismatch: {fetched}")
        _status, budget = self.request("GET", f"/v1/memory/budget?room={urllib.parse.quote(ROOM_NAME)}", required=False)
        selected_ids = {str(item.get("memory_id")) for item in budget.get("selected", [])}
        if self.memory_id in selected_ids and budget.get("estimated_chars", 0) <= budget.get("injected_max_chars", 0):
            self.pass_check("shared memory budget", f"{budget.get('estimated_chars')} chars")
        else:
            self.fail(f"shared memory budget missing approved memory: {budget}")

    def verify_room_replies(self, expected: set[str]) -> None:
        if not expected:
            self.skip("room reply persistence", "no successful room deliveries to verify")
            return
        _status, transcript = self.request("GET", f"/v1/rooms/{urllib.parse.quote(ROOM_NAME)}/messages?limit=100")
        messages = transcript.get("messages", [])
        sources = {str(message.get("source")) for message in messages}
        found = expected & sources
        self.room_replies = len(found)
        missing = expected - found
        if missing:
            self.fail(f"room transcript missing replies from: {', '.join(sorted(missing))}")
        else:
            self.pass_check("room replies persisted", f"{len(found)} replies")

    def task_flow(self) -> None:
        assignee = self.agents[0] if self.agents else None
        _status, task = self.request("POST", "/v1/tasks", {
            "title": f"Live integration task {self.started.strftime('%Y-%m-%d %H:%M:%S')}",
            "description": "Created by scripts/live_integration_test.py",
            "status": "open",
            "priority": "normal",
            "assigned_agent_id": assignee,
            "room_name": ROOM_NAME,
            "actor": "live-integration-test",
        })
        self.task_id = str(task.get("task_id", ""))
        if self.task_id:
            self.pass_check("task created", self.task_id)
        else:
            self.fail("task creation did not return task_id")
            return
        if assignee:
            self.request("PATCH", f"/v1/tasks/{urllib.parse.quote(self.task_id)}", {
                "assigned_agent_id": assignee,
                "actor": "live-integration-test",
            })
        for status in ("in_progress", "blocked", "done"):
            self.request("PATCH", f"/v1/tasks/{urllib.parse.quote(self.task_id)}", {
                "status": status,
                "actor": "live-integration-test",
            })
        self.request("PATCH", f"/v1/tasks/{urllib.parse.quote(self.task_id)}", {
            "priority": "high",
            "actor": "live-integration-test",
        })
        self.request("POST", f"/v1/tasks/{urllib.parse.quote(self.task_id)}/comment", {
            "author": "live-integration-test",
            "actor": "live-integration-test",
            "body": "Live integration test comment.",
        })
        _status, events = self.request("GET", f"/v1/tasks/{urllib.parse.quote(self.task_id)}/events")
        if events.get("events"):
            self.pass_check("task events fetched", f"{len(events['events'])} events")
        else:
            self.fail("task events endpoint returned no events")

    def verify_task_persists(self) -> None:
        if not self.task_id:
            self.skip("task persistence", "no task id")
            return
        _status, tasks = self.request("GET", "/v1/tasks")
        found = next((task for task in tasks.get("tasks", []) if task.get("task_id") == self.task_id), None)
        if found:
            self.pass_check("task persists", self.task_id)
        else:
            self.fail(f"task not found after persistence check: {self.task_id}")

    def check_presence(self, label: str, *, require_events: bool = False) -> None:
        status, agents = self.request("GET", "/v1/agents", required=False)
        if status != 200:
            self.fail(f"presence {label} failed: {agents}")
            return
        rows = agents.get("agents", [])
        by_id = {str(agent.get("adapter_id")): agent for agent in rows}
        missing = [agent for agent in self.agents if agent not in by_id]
        if missing:
            self.fail(f"presence {label} missing agents: {', '.join(missing)}")
            return
        required_fields = {"status", "last_seen_at", "runtime", "current_task_id", "current_room", "last_message_at"}
        incomplete = [
            agent_id for agent_id in self.agents
            if not required_fields.issubset(set(by_id[agent_id]))
        ]
        if incomplete:
            self.fail(f"presence {label} missing fields for: {', '.join(incomplete)}")
            return
        invalid = [
            agent_id for agent_id in self.agents
            if by_id[agent_id].get("status") not in {"configured", "online", "idle", "working", "blocked", "offline", "disabled"}
        ]
        if invalid:
            self.fail(f"presence {label} invalid status for: {', '.join(invalid)}")
            return
        if require_events and self.agents:
            eventful = 0
            for agent_id in self.agents:
                event_status, events = self.request(
                    "GET",
                    f"/v1/agents/{urllib.parse.quote(agent_id)}/events?limit=20",
                    required=False,
                    timeout=10,
                )
                if event_status == 200 and events.get("events"):
                    eventful += 1
            if eventful == 0:
                self.fail(f"presence {label} found no persisted agent events")
                return
        self.presence_checked += 1
        self.pass_check(f"presence {label}", f"{len(rows)} agents")

    def restart_daemon(self) -> None:
        if self.args.skip_restart:
            self.skip("restart daemon", "--skip-restart")
            return
        proc = self.synkraken_command("restart", "daemon", required=False)
        if proc.returncode != 0:
            self.fail("synkraken restart daemon failed")
            return
        deadline = time.time() + self.args.timeout
        while time.time() < deadline:
            status, health = self.request("GET", "/health", required=False, timeout=5)
            if status == 200 and health.get("ok"):
                self.pass_check("daemon restarted", "health ok")
                return
            time.sleep(2)
        self.fail("daemon did not become healthy after restart")

    def run_discussion_if_available(self) -> None:
        candidates = [
            agent_id for agent_id, _duration in sorted(self.direct_durations.items(), key=lambda item: item[1])
            if agent_id in self.agents
        ]
        if len(candidates) < 2:
            self.discussion_result = "SKIPPED: fewer than two successful direct agents"
            self.skip("discussion", self.discussion_result)
            return
        discussion_agents = candidates[:2]
        payload = {
            "source": "live-integration-test",
            "agents": discussion_agents,
            "topic": "Give one improvement for SynKraken room handling.",
            "max_turns": 2,
            "room_name": ROOM_NAME,
        }
        discussion_timeout = max(self.args.timeout, (self.args.timeout * int(payload["max_turns"])) + 30)
        status, result = self.request("POST", "/v1/discussions", payload, required=False, timeout=discussion_timeout)
        self.record_discussion_diagnostics(result)
        if status == 404:
            self.discussion_result = "SKIPPED: /v1/discussions not exposed"
            self.skip("discussion", self.discussion_result)
            return
        if not (200 <= status < 300):
            self.discussion_result = f"FAIL: {result.get('error', result)}"
            self.fail(f"discussion failed: {self.discussion_result}")
            return
        self.discussion_result = str(result.get("status", "completed"))
        if result.get("status") == "completed":
            self.pass_check("discussion completed", f"{len(result.get('turns', []))} turns via {', '.join(discussion_agents)}")
            if result.get("memory_context"):
                self.pass_check("discussion memory injected", ROOM_NAME)
            else:
                self.fail("discussion did not report memory_context")
        else:
            self.fail(f"discussion ended with status {result.get('status')}")

    def run_team_task_if_available(self) -> None:
        if len(self.agents) < 2:
            self.skip("team task", "fewer than two configured agents")
            return
        payload = {
            "source": "live-integration-test",
            "room_name": ROOM_NAME,
            "question": "Use Team Task Mode to propose one concise reliability improvement for SynKraken fanout.",
            "turns": 4,
        }
        team_timeout = max(self.args.timeout + 180, self.args.timeout * max(3, len(self.agents)))
        status, result = self.request("POST", "/v1/team-tasks", payload, required=False, timeout=team_timeout)
        if not (200 <= status < 300):
            self.fail(f"team task failed: {status} {result.get('error', result)}")
            return
        self.team_task_id = str(result.get("task_id") or "")
        if self.team_task_id and result.get("final_report"):
            self.pass_check("team task completed", f"owner={result.get('owner')} task={self.team_task_id}")
        else:
            self.fail(f"team task missing task_id or final_report: {result}")
            return
        _status, events = self.request("GET", f"/v1/tasks/{urllib.parse.quote(self.team_task_id)}/events", required=False)
        event_types = {str(event.get("event_type")) for event in events.get("events", [])}
        if {"nominated", "assigned", "reviewed", "completed"} & event_types:
            self.pass_check("team task events", ", ".join(sorted(event_types)))
        else:
            self.fail(f"team task events missing expected lifecycle: {event_types}")
        _status, transcript = self.request("GET", f"/v1/rooms/{urllib.parse.quote(ROOM_NAME)}/messages?limit=200", required=False)
        bodies = "\n".join(str(message.get("body", "")) for message in transcript.get("messages", []))
        if "Team task:" in bodies and "Team owner selected:" in bodies and str(result.get("final_report", ""))[:40] in bodies:
            self.pass_check("team task transcript", ROOM_NAME)
        else:
            self.fail("team task transcript missing prompt, owner selection, or final report")

    def run_goal_if_available(self) -> None:
        if len(self.agents) < 2:
            self.skip("goal mode", "fewer than two configured agents")
            return
        payload = {
            "source": "live-integration-test",
            "room_name": ROOM_NAME,
            "goal": "Produce one concise, bounded improvement note for the selected room workflow.",
            "threshold": 50,
            "max_rounds": 1,
        }
        goal_timeout = max(self.args.timeout + 240, self.args.timeout * max(4, len(self.agents)))
        status, result = self.request("POST", "/v1/goal-runs", payload, required=False, timeout=goal_timeout)
        if not (200 <= status < 300):
            self.fail(f"goal mode failed: {status} {result.get('error', result)}")
            return
        run = result.get("goal_run") or {}
        self.goal_run_id = str(run.get("goal_run_id") or "")
        if run.get("status") in {"achieved", "partially_achieved"} and self.goal_run_id:
            self.pass_check("goal mode completed", f"{run.get('status')} score={run.get('latest_score')}")
        else:
            self.fail(f"goal mode unexpected status: {run}")
            return
        if run.get("linked_task_id"):
            self.pass_check("goal task linked", str(run.get("linked_task_id")))
        else:
            self.fail(f"goal mode missing linked task: {run}")
        _status, events = self.request("GET", f"/v1/goal-runs/{urllib.parse.quote(self.goal_run_id)}/events", required=False)
        event_types = {str(event.get("event_type")) for event in events.get("events", [])}
        if {"goal_started", "token_budget_checked", "guardrail_checked", "score_recorded"} <= event_types:
            self.pass_check("goal events", ", ".join(sorted(event_types)))
        else:
            self.fail(f"goal events missing expected lifecycle: {event_types}")
        report = str(run.get("final_report", ""))
        if "Token notes:" in report and "Guardrail notes:" in report:
            self.pass_check("goal control notes", self.goal_run_id)
        else:
            self.fail("goal final report missing token or guardrail notes")

    def fake_agent_failure(self) -> None:
        before_status, before = self.request("GET", "/v1/dead-letters?limit=20", required=False)
        before_count = len(before.get("dead_letters", [])) if before_status == 200 else 0
        status, result = self.request("POST", "/v1/messages", {
            "source": "live-integration-test",
            "target": FAKE_AGENT,
            "body": "This should fail cleanly.",
        }, required=False)
        after_status, after = self.request("GET", "/v1/dead-letters?limit=20", required=False)
        after_count = len(after.get("dead_letters", [])) if after_status == 200 else before_count
        error = str(result.get("error", ""))
        if status >= 400 and "unknown target adapter" in error.lower():
            detail = "HTTP clean failure"
            if after_count > before_count:
                detail += " and dead letter recorded"
            self.pass_check("fake agent failure", detail)
        elif after_count > before_count:
            self.pass_check("fake agent failure", "dead letter recorded")
        else:
            self.fail(f"fake agent did not fail cleanly: status={status} result={result}")

    def run(self) -> int:
        self.synkraken_command("status", required=False)
        self.synkraken_command("health")
        self.synkraken_command("agents")
        _status, health = self.request("GET", "/health")
        if health.get("ok"):
            self.pass_check("daemon health", "ok")
        else:
            self.fail("daemon health not ok")
        _status, agents_data = self.request("GET", "/v1/agents")
        self.agents = self.choose_agents(agents_data)
        if not self.agents:
            self.fail("no configured/enabled agents to test")
            self.finish()
            return 1
        self.pass_check("agents selected", ", ".join(self.agents))
        self.check_presence("before")

        direct_ok: list[str] = []
        for agent in self.agents:
            result = self.send_message(
                agent,
                f"Live integration direct check for {agent}. Reply briefly.",
                required=False,
            )
            self.record_fanout_diagnostics(f"direct:{agent}", result)
            deliveries = result.get("deliveries", [])
            if deliveries and deliveries[0].get("ok"):
                direct_ok.append(agent)
                self.direct_durations[agent] = int(deliveries[0].get("duration_ms") or 999999)
            else:
                reason = result.get("error") or (deliveries[0].get("error") if deliveries else "no delivery")
                self.fail(f"direct message failed for {agent}: {reason}")
        if len(direct_ok) == len(self.agents):
            self.pass_check("direct messages", f"{len(direct_ok)} agents")

        fanout_timeout = self.args.timeout + 45
        broadcast = self.send_message(
            "broadcast",
            "Live integration @everyone broadcast. Reply briefly.",
            required=False,
            timeout=fanout_timeout,
        )
        self.record_fanout_diagnostics("global broadcast", broadcast)
        self.broadcast_replies = sum(1 for delivery in broadcast.get("deliveries", []) if delivery.get("ok"))
        if self.broadcast_replies:
            self.pass_check("global broadcast", f"{self.broadcast_replies} replies")
        else:
            self.fail("global broadcast produced no successful replies")
        self.check_presence("after broadcast", require_events=True)

        self.ensure_room()
        self.ensure_room_memory()
        self.shared_memory_flow()
        room = self.send_message(
            f"room:{ROOM_NAME}",
            "Live integration room @everyone broadcast. Reply briefly.",
            required=False,
            timeout=fanout_timeout,
        )
        self.record_fanout_diagnostics("room broadcast", room)
        if (room.get("routing") or {}).get("memory_context"):
            self.pass_check("room broadcast memory injected", ROOM_NAME)
            if self.memory_id and "[SynKraken approved memory]" in str((room.get("routing") or {}).get("memory_context")):
                self.pass_check("shared memory injected", self.memory_id)
        else:
            self.fail("room broadcast did not report memory_context")
        room_success = {str(delivery.get("delivery_target") or delivery.get("adapter_id")) for delivery in room.get("deliveries", []) if delivery.get("ok")}
        if room_success:
            self.pass_check("room broadcast", f"{len(room_success)} replies")
        else:
            self.fail("room broadcast produced no successful replies")
        self.verify_room_replies(room_success)

        self.run_discussion_if_available()
        self.check_presence("after discussion", require_events=True)
        self.run_team_task_if_available()
        self.run_goal_if_available()
        self.task_flow()
        self.restart_daemon()
        self.verify_task_persists()
        self.fake_agent_failure()
        self.finish()
        return 1 if self.failures else 0

    def finish(self) -> None:
        self.raw["finished_at"] = datetime.now().isoformat()
        self.raw["summary"] = self.summary()
        self.raw_path.write_text(json.dumps(self.raw, indent=2, ensure_ascii=False), encoding="utf-8")
        self.report_path.write_text(self.render_report(), encoding="utf-8")
        summary = self.summary()
        print(f"{summary['status']}")
        print(f"agents tested: {', '.join(self.agents) or '(none)'}")
        print(f"broadcast replies: {self.broadcast_replies}")
        print(f"room replies: {self.room_replies}")
        print(f"discussion result: {self.discussion_result}")
        print(f"presence checks: {self.presence_checked}")
        print(f"team task id: {self.team_task_id or '(none)'}")
        print(f"goal run id: {self.goal_run_id or '(none)'}")
        print(f"task id: {self.task_id or '(none)'}")
        print(f"shared memory id: {self.memory_id or '(none)'}")
        print(f"report: {self.report_path}")

    def summary(self) -> dict[str, Any]:
        return {
            "status": "FAIL" if self.failures else "PASS",
            "agents_tested": self.agents,
            "broadcast_replies": self.broadcast_replies,
            "room_replies": self.room_replies,
            "discussion_result": self.discussion_result,
            "presence_checks": self.presence_checked,
            "team_task_id": self.team_task_id,
            "goal_run_id": self.goal_run_id,
            "task_id": self.task_id,
            "memory_id": self.memory_id,
            "failures": self.failures,
            "skips": self.skips,
            "report_path": str(self.report_path),
        }

    def render_report(self) -> str:
        summary = self.summary()
        lines = [
            "# SynKraken Live Integration Test",
            "",
            f"- Status: **{summary['status']}**",
            f"- Started: `{self.started.isoformat()}`",
            f"- Daemon URL: `{self.base}`",
            f"- Agents tested: `{', '.join(self.agents) or '(none)'}`",
            f"- Broadcast replies: `{self.broadcast_replies}`",
            f"- Room replies: `{self.room_replies}`",
            f"- Discussion result: `{self.discussion_result}`",
            f"- Presence checks: `{self.presence_checked}`",
            f"- Team task id: `{self.team_task_id or '(none)'}`",
            f"- Goal run id: `{self.goal_run_id or '(none)'}`",
            f"- Task id: `{self.task_id or '(none)'}`",
            f"- Shared memory id: `{self.memory_id or '(none)'}`",
            "",
            "## Checks",
            "",
        ]
        for check in self.raw["checks"]:
            lines.append(f"- {check['status']}: {check['name']} {check.get('detail', '')}".rstrip())
        if self.failures:
            lines.extend(["", "## Failures", ""])
            lines.extend(f"- {failure}" for failure in self.failures)
        if self.skips:
            lines.extend(["", "## Skipped", ""])
            lines.extend(f"- {skip}" for skip in self.skips)
        if self.raw.get("fanout_diagnostics"):
            lines.extend(["", "## Fanout Diagnostics", ""])
            for item in self.raw["fanout_diagnostics"]:
                lines.append(f"### {item.get('label', 'diagnostic')}")
                lines.append(f"- message id: `{item.get('message_id') or item.get('conversation_id') or ''}`")
                if item.get("requested_target"):
                    lines.append(f"- requested target: `{item.get('requested_target')}`")
                if item.get("resolved_targets") is not None:
                    lines.append(f"- resolved targets: `{', '.join(item.get('resolved_targets') or [])}`")
                if item.get("reply_context") is not None:
                    lines.append(f"- reply context: `{item.get('reply_context')}`")
                if item.get("transcript_target") is not None:
                    lines.append(f"- transcript target: `{item.get('transcript_target')}`")
                if item.get("memory_context"):
                    lines.append(f"- memory context: `{str(item.get('memory_context'))[:160]}`")
                lines.append(f"- deliveries created: `{item.get('deliveries_created', 0)}`")
                for delivery in item.get("deliveries", []):
                    lines.append(
                        "- delivery "
                        f"`{delivery.get('delivery_target')}` "
                        f"status=`{delivery.get('status')}` "
                        f"ok=`{delivery.get('ok')}` "
                        f"elapsed_ms=`{delivery.get('duration_ms')}` "
                        f"reply_context=`{delivery.get('reply_context')}` "
                        f"reply_message_id=`{delivery.get('reply_message_id')}` "
                        f"persisted_target=`{delivery.get('persisted_transcript_target')}`"
                    )
                if item.get("dead_letters"):
                    lines.append(f"- dead letters: `{len(item['dead_letters'])}`")
        lines.extend([
            "",
            "## Artifacts",
            "",
            f"- Raw JSON: `{self.raw_path.name}`",
            f"- Commands log: `{self.commands_log.name}`",
        ])
        return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a live end-to-end SynKraken integration test.")
    parser.add_argument("--daemon-url", default="http://127.0.0.1:9460")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--skip-restart", action="store_true")
    parser.add_argument("--agents", help="Comma-separated adapter ids to test")
    parser.add_argument("--output-dir", help="Directory under which live-test-YYYYMMDD-HHMMSS is created")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    test = LiveTest(args)
    raise SystemExit(test.run())


if __name__ == "__main__":
    main()
