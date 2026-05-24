from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from queue import Queue
from threading import Lock
from typing import Any
import json
import os
import re
import subprocess
import time

from .adapters import build_adapter
from .models import AdapterReply, FabricMessage, new_id, utc_now_iso
from .router import resolve_targets
from .storage import SHARED_MEMORY_TYPES, Storage


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Queue] = []
        self._lock = Lock()

    def subscribe(self) -> Queue:
        q: Queue = Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: Queue) -> None:
        with self._lock:
            self._subscribers = [item for item in self._subscribers if item is not q]

    def publish(self, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        payload = {
            'event': event,
            'timestamp': utc_now_iso(),
            'data': data,
        }
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except Exception:
                continue


class AgentFabric:
    def __init__(self, config: dict, storage: Storage) -> None:
        self.config = config
        self.storage = storage
        self.adapters = {}
        self.event_bus = EventBus()
        agent_records = []
        for adapter_id, adapter_config in config.get("adapters", {}).items():
            if adapter_config.get("enabled", True):
                self.adapters[adapter_id] = build_adapter(adapter_id, adapter_config)
                agent_records.append(self.adapters[adapter_id].health())
            else:
                agent_records.append({
                    "adapter_id": adapter_id,
                    "runtime_name": adapter_config.get("runtime_name") or adapter_id,
                    "type": adapter_config.get("type") or "unknown",
                    "runtime": adapter_config.get("type") or "unknown",
                    "enabled": False,
                })
        self.storage.sync_agents(agent_records)
        self._sync_runtime_registry()
        routing = config.get("routing", {})
        self.max_hops = int(routing.get("max_hops", 4))
        self.retry_limit = int(routing.get("retry_limit", 1))
        self.retry_backoff_seconds = int(routing.get("retry_backoff_seconds", 1))
        memory = config.get("memory", {})
        self.memory_max_items_injected = int(memory.get("max_items_injected", 5))
        self.memory_max_chars_injected = int(memory.get("max_chars_injected", 1200))
        self.memory_max_memory_chars = int(memory.get("max_memory_chars", 500))
        self.memory_min_confidence = int(memory.get("min_confidence", 70))
        goal = config.get("goal", {})
        self.goal_default_max_rounds = int(goal.get("max_rounds", 3))
        self.goal_default_threshold = int(goal.get("threshold", 80))
        self.goal_max_reviewers = int(goal.get("max_reviewers", 3))
        self.goal_max_context_chars = int(goal.get("max_context_chars", 4000))
        self.goal_max_revision_chars = int(goal.get("max_revision_chars", 1500))
        self.goal_max_agents = int(goal.get("max_agents", 4))
        instance = config.get("instance", {}) if isinstance(config.get("instance"), dict) else {}
        self.instance_name = str(instance.get("instance_name") or config.get("instance_name") or "").strip() or None
        self.organisation_name = (
            str(
                instance.get("organisation_name")
                or instance.get("organization_name")
                or config.get("organisation_name")
                or config.get("organization_name")
                or ""
            ).strip()
            or None
        )
        self.workspace = (
            str(instance.get("default_workspace") or config.get("default_workspace") or config.get("workspace") or "").strip()
            or None
        )
        self.started_at = utc_now_iso()

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "timestamp": utc_now_iso(),
            "started_at": self.started_at,
            "instance_name": self.instance_name,
            "organisation_name": self.organisation_name,
            "default_workspace": self.workspace,
            "adapters": {adapter_id: adapter.health() for adapter_id, adapter in self.adapters.items()},
        }

    def list_agents(self) -> list[dict[str, Any]]:
        return self.storage.list_agents()

    def update_agent_profile(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        actor = str(payload.get("actor", "operator")).strip() or "operator"
        fields = {
            key: payload[key]
            for key in ("cost_tier", "preferred_roles", "capabilities", "speed", "trust")
            if key in payload
        }
        updated = self.storage.update_agent_profile(agent_id, fields, actor=actor)
        if updated is None:
            raise ValueError(f"agent not found: {agent_id}")
        self.event_bus.publish("agent.profile_updated", {"agent_id": agent_id})
        return updated

    def _sync_runtime_registry(self) -> None:
        for adapter_id, adapter_config in self.config.get("adapters", {}).items():
            command = adapter_config.get("command") or []
            capabilities = adapter_config.get("capabilities") or []
            supported_modes = adapter_config.get("supported_modes") or [
                "direct", "broadcast", "room", "team", "goal", "memory"
            ]
            self.storage.upsert_runtime({
                "runtime_id": adapter_id,
                "runtime_type": adapter_config.get("runtime_type") or adapter_config.get("type") or "unknown",
                "adapter_type": adapter_config.get("type") or "unknown",
                "version": adapter_config.get("version") or "",
                "command": command,
                "working_dir": adapter_config.get("working_dir") or adapter_config.get("cwd") or "",
                "timeout": adapter_config.get("timeout_seconds") or self.config.get("routing", {}).get("default_timeout_seconds", 90),
                "cost_profile": adapter_config.get("cost_profile") or adapter_config.get("cost_tier") or "medium",
                "cost_tier": adapter_config.get("cost_tier") or adapter_config.get("cost_profile") or "medium",
                "usage_risk": adapter_config.get("usage_risk") or "medium",
                "preferred_roles": adapter_config.get("preferred_roles") or [],
                "avoid_roles": adapter_config.get("avoid_roles") or [],
                "supported_modes": supported_modes,
                "capabilities": capabilities,
                "enabled": adapter_config.get("enabled", True),
            })
        for runtime_id, runtime_config in self.config.get("runtime_registry", {}).items():
            item = dict(runtime_config)
            item.setdefault("runtime_id", runtime_id)
            if runtime_id in self.config.get("adapters", {}):
                continue
            self.storage.upsert_runtime(item)

    def list_runtimes(self) -> list[dict[str, Any]]:
        self._sync_runtime_registry()
        return self.storage.list_runtimes()

    def runtime_doctor(self) -> dict[str, Any]:
        runtimes = self.list_runtimes()
        results = []
        for runtime in runtimes:
            runtime_id = runtime["runtime_id"]
            adapter = self.adapters.get(runtime_id)
            health = adapter.health() if adapter else {"enabled": False, "ok": False}
            command = runtime.get("command") or []
            result: dict[str, Any] = {
                "runtime_id": runtime_id,
                "runtime_type": runtime.get("runtime_type"),
                "enabled": runtime.get("enabled"),
                "registered": runtime_id in self.adapters,
                "command": command,
                "cost_tier": runtime.get("cost_tier") or runtime.get("cost_profile") or "medium",
                "usage_risk": runtime.get("usage_risk") or "medium",
                "preferred_roles": runtime.get("preferred_roles") or [],
                "avoid_roles": runtime.get("avoid_roles") or [],
                "ok": bool(adapter and health.get("enabled", True)),
                "health": health,
                "warnings": [] if command else ["no command recorded"],
            }
            if health.get("type") == "crush" or runtime.get("adapter_type") == "crush":
                result["node_bin_dir"] = runtime.get("node_bin_dir")
                node_available = self._check_node_in_adapter_env(runtime_id)
                result["node_available"] = node_available
            results.append(result)
        return {"runtimes": results}

    def _check_node_in_adapter_env(self, runtime_id: str) -> bool:
        adapter = self.adapters.get(runtime_id)
        if adapter is None:
            return False
        try:
            check_cmd = ["sh", "-c", "command -v node > /dev/null 2>&1 && echo OK || echo MISSING"]
            if hasattr(adapter, "build_env"):
                env = adapter.build_env()
            elif hasattr(adapter, "_build_env"):
                env = adapter._build_env()
            else:
                env = None
            proc = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            return "OK" in proc.stdout
        except Exception:
            return False

    def add_room_member(self, room_name: str, adapter_id: str, actor: str = "operator") -> dict:
        if adapter_id not in self.adapters:
            raise ValueError(f"unknown agent: {adapter_id}")
        if not self.storage.room_exists(room_name):
            raise ValueError(f"room not found: {room_name}")
        self.storage.add_room_member(room_name, adapter_id, utc_now_iso())
        self._save_visible_message(
            "synkraken-room",
            f"room:{room_name}",
            f"Room member added: {adapter_id}",
            conversation_id=f"room:{room_name}",
            metadata={"room_event": True, "event": "member_added", "agent_id": adapter_id, "actor": actor},
        )
        self.event_bus.publish("room.member_added", {"room_name": room_name, "agent_id": adapter_id, "actor": actor})
        room = self.storage.get_room(room_name)
        assert room is not None
        return room

    def remove_room_member(self, room_name: str, adapter_id: str, actor: str = "operator") -> dict:
        if not self.storage.room_exists(room_name):
            raise ValueError(f"room not found: {room_name}")
        self.storage.remove_room_member(room_name, adapter_id)
        self._save_visible_message(
            "synkraken-room",
            f"room:{room_name}",
            f"Room member removed: {adapter_id}",
            conversation_id=f"room:{room_name}",
            metadata={"room_event": True, "event": "member_removed", "agent_id": adapter_id, "actor": actor},
        )
        self.event_bus.publish("room.member_removed", {"room_name": room_name, "agent_id": adapter_id, "actor": actor})
        return self.storage.get_room(room_name) or {"name": room_name, "members": []}

    def flight_summary(self) -> dict[str, Any]:
        agents = self.list_agents()
        goals = self.storage.list_goal_runs(limit=100)
        active_goals = [goal for goal in goals if goal.get("status") in {"planning", "running", "reviewing"}]
        blocked_goals = [goal for goal in goals if goal.get("status") in {"blocked", "failed", "cancelled"}]
        dead_letters = self.storage.list_dead_letters(limit=10).get("dead_letters", [])
        runtimes = self.list_runtimes()
        tiers = Counter(str(item.get("cost_tier") or item.get("cost_profile") or "medium") for item in runtimes)
        risks = Counter(str(item.get("usage_risk") or "medium") for item in runtimes)
        premium = tiers.get("premium", 0)
        cost_complexity = "high" if premium >= 2 or len(runtimes) >= 5 else "medium" if premium or len(runtimes) >= 3 else "low"
        token_risk = "high" if len(active_goals) > 2 else "medium" if active_goals else "low"
        pending_reviews = len([run for run in self.storage.list_team_runs(limit=100) if run.get("status") == "awaiting_approval"])
        pending_reviews += self.storage.count_shared_memory("proposed")
        return {
            "agents_online": len([agent for agent in agents if agent.get("enabled") and agent.get("status") in {"online", "idle", "working"}]),
            "agents_total": len(agents),
            "active_goals": len(active_goals),
            "blocked_goals": len(blocked_goals),
            "token_risk": token_risk,
            "failures": len([goal for goal in goals if goal.get("status") == "failed"]),
            "dead_letters": self.storage.count_dead_letters(),
            "recent_dead_letters": dead_letters,
            "cost_complexity": cost_complexity,
            "cost_profiles": {
                "cost_tiers": {key: tiers.get(key, 0) for key in ("local", "cheap", "medium", "premium")},
                "usage_risk": {key: risks.get(key, 0) for key in ("low", "medium", "high")},
            },
            "memory_count": self.storage.count_shared_memory(),
            "pending_reviews": pending_reviews,
        }

    def init_workspace(self, name: str | None = None) -> dict[str, Any]:
        workspace_name = (name or self.workspace or "default").strip() or "default"
        pack = {
            "rooms": self.storage.list_rooms(),
            "agents": self.list_agents(),
            "memory": self.storage.list_shared_memory(limit=1000),
            "skills": ["synkraken-bridge"],
            "goals": self.storage.list_goal_runs(limit=100),
            "repos": [],
            "governance": {"team_runs": self.storage.list_team_runs(limit=100)},
            "runtime_refs": [runtime["runtime_id"] for runtime in self.list_runtimes()],
        }
        return {"workspace": self.storage.upsert_workspace_pack(workspace_name, pack)}

    def load_workspace(self, name: str | None = None) -> dict[str, Any]:
        workspace_name = (name or self.workspace or "default").strip() or "default"
        pack = self.storage.get_workspace_pack(workspace_name)
        if not pack:
            raise ValueError(f"workspace not found: {workspace_name}")
        return {"workspace": pack}

    def export_workspace(self, name: str | None = None) -> dict[str, Any]:
        return self.load_workspace(name)

    def _presence_room(self, reply_context: str | None) -> str | None:
        if reply_context and reply_context.startswith("room:"):
            return reply_context.split(":", 1)[1]
        return None

    def _room_memory_context(self, room_name: str | None) -> str:
        if not room_name:
            return ""
        memory = self.storage.get_room_memory(room_name)
        if not memory:
            return ""
        labels = [
            ("Purpose", "purpose"),
            ("Objective", "objective"),
            ("Current focus", "current_focus"),
            ("Rules", "rules"),
            ("Constraints", "constraints"),
            ("Notes", "notes"),
        ]
        parts = [f"Room: {room_name}"]
        for label, key in labels:
            value = str(memory.get(key) or "").strip()
            if value:
                parts.append(f"{label}: {value}")
        if len(parts) == 1:
            return ""
        text = "\n".join(parts)
        return text[:482] + "..." if len(text) > 485 else text

    def _with_room_memory(self, body: str, memory_context: str) -> str:
        if not memory_context:
            return body
        return f"Room context:\n{memory_context}\n\nMessage:\n{body}"

    def _shared_memory_context(self, room_name: str | None, *, mark_used: bool = True) -> tuple[str, list[dict[str, Any]]]:
        memories = self.storage.select_shared_memory_for_injection(
            room_name=room_name,
            workspace=self.workspace,
            max_items=self.memory_max_items_injected,
            max_chars=self.memory_max_chars_injected,
            min_confidence=self.memory_min_confidence,
        )
        if not memories:
            return "", []
        lines = ["[SynKraken approved memory]"]
        used_chars = len(lines[0])
        included: list[dict[str, Any]] = []
        for memory in memories:
            line = f"- {memory.get('memory_type')}: {str(memory.get('content') or '').strip()}"
            if included and used_chars + 1 + len(line) > self.memory_max_chars_injected:
                continue
            if len(line) > self.memory_max_chars_injected:
                continue
            lines.append(line)
            used_chars += 1 + len(line)
            included.append(memory)
        if mark_used and included:
            self.storage.mark_shared_memory_used([memory["memory_id"] for memory in included])
        return "\n".join(lines), included

    def _prompt_memory_context(self, room_name: str | None, *, mark_used: bool = True) -> tuple[str, list[dict[str, Any]]]:
        parts = []
        room_context = self._room_memory_context(room_name)
        if room_context:
            parts.append(f"Room context:\n{room_context}")
        shared_context, memories = self._shared_memory_context(room_name, mark_used=mark_used)
        if shared_context:
            parts.append(shared_context)
        return "\n\n".join(parts), memories

    def _with_memory_context(self, body: str, memory_context: str) -> str:
        if not memory_context:
            return body
        return f"{memory_context}\n\nMessage:\n{body}"

    def _set_agent_working(self, adapter_id: str, message: FabricMessage, *,
                           reply_context: str | None, event_type: str = "message_received") -> None:
        now = utc_now_iso()
        self.storage.update_agent_presence(
            adapter_id,
            status="working",
            current_room=self._presence_room(reply_context),
            last_message_at=now,
            event_type=event_type,
            old_value=message.message_id,
            new_value=reply_context or message.target,
            seen_at=now,
        )
        self.event_bus.publish("agent.presence", {"agent_id": adapter_id, "status": "working"})

    def _set_agent_result(self, adapter_id: str, message: FabricMessage, reply: AdapterReply,
                          status: str, *, reply_context: str | None) -> None:
        now = utc_now_iso()
        if reply.ok:
            self.storage.update_agent_presence(
                adapter_id,
                status="idle",
                current_room=self._presence_room(reply_context),
                last_message_at=now,
                event_type="message_sent",
                old_value=message.message_id,
                new_value=reply.external_reference or message.conversation_id,
                seen_at=now,
            )
            self.event_bus.publish("agent.presence", {"agent_id": adapter_id, "status": "idle"})
            return
        event_type = "timeout" if status == "timeout" else "message_sent"
        self.storage.update_agent_presence(
            adapter_id,
            status="blocked",
            current_room=self._presence_room(reply_context),
            last_message_at=now,
            event_type=event_type,
            old_value=message.message_id,
            new_value=reply.error or status,
            seen_at=now,
        )
        self.event_bus.publish("agent.presence", {"agent_id": adapter_id, "status": "blocked"})

    def _reply_status(self, reply: AdapterReply) -> str:
        if reply.ok:
            return 'replied'
        if reply.error:
            err = reply.error.lower()
            if 'timeout' in err or 'timed out' in err:
                return 'timeout'
        return 'failed'

    def _adapter_exception_reply(self, adapter_id: str, exc: Exception) -> tuple[AdapterReply, str]:
        err = str(exc) or exc.__class__.__name__
        is_timeout = isinstance(exc, TimeoutError) or 'timeout' in err.lower() or 'timed out' in err.lower()
        reply = AdapterReply(
            adapter_id=adapter_id,
            ok=False,
            body='',
            error=err,
            raw={'exception_type': exc.__class__.__name__},
        )
        return reply, 'timeout' if is_timeout else 'failed'

    def _publish_delivery_queued(self, message: FabricMessage, delivery_target: str,
                                 runtime_name: str, original_target: str,
                                 reply_context: str | None) -> None:
        self.event_bus.publish('delivery.queued', {
            'adapter_id': delivery_target,
            'runtime_name': runtime_name,
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'original_target': original_target,
            'delivery_target': delivery_target,
            'reply_context': reply_context,
            'status': 'queued',
            'created_at': utc_now_iso(),
        })

    def _publish_delivery_sent(self, message: FabricMessage, delivery_target: str,
                               runtime_name: str, original_target: str,
                               reply_context: str | None, attempt: int) -> None:
        self.event_bus.publish('delivery.sent', {
            'adapter_id': delivery_target,
            'runtime_name': runtime_name,
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'original_target': original_target,
            'delivery_target': delivery_target,
            'reply_context': reply_context,
            'status': 'sent',
            'attempts': attempt,
            'created_at': utc_now_iso(),
        })

    def _publish_typing_started(self, message: FabricMessage, delivery_target: str,
                                runtime_name: str, original_target: str,
                                reply_context: str | None) -> None:
        self.event_bus.publish('typing.started', {
            'adapter_id': delivery_target,
            'runtime_name': runtime_name,
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'original_target': original_target,
            'delivery_target': delivery_target,
            'reply_context': reply_context,
            'status': 'thinking',
        })

    def _publish_typing_stopped(self, message: FabricMessage, delivery_target: str,
                                runtime_name: str, original_target: str,
                                reply_context: str | None, reply: AdapterReply,
                                status: str) -> None:
        self.event_bus.publish('typing.stopped', {
            'adapter_id': delivery_target,
            'runtime_name': runtime_name,
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'ok': reply.ok,
            'original_target': original_target,
            'delivery_target': delivery_target,
            'reply_context': reply_context,
            'status': status,
        })

    def _record_delivery(self, message: FabricMessage, reply: AdapterReply, *,
                         attempt: int, original_target: str, delivery_target: str,
                         reply_context: str | None, status: str) -> dict[str, Any]:
        self.storage.save_delivery(
            message.message_id,
            reply,
            created_at=datetime.now(timezone.utc).isoformat(),
            attempts=attempt,
        )
        delivery_payload = reply.to_dict() | {
            'attempts': attempt,
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'original_target': original_target,
            'delivery_target': delivery_target,
            'reply_context': reply_context,
            'status': status,
            'duration_ms': reply.duration_ms,
            'body_preview': (reply.body or '')[:160],
        }
        self.event_bus.publish('delivery.recorded', delivery_payload)
        return delivery_payload

    def _delivery_message_for_target(self, message: FabricMessage, delivery_target: str) -> FabricMessage:
        return FabricMessage(
            source=message.source,
            target=delivery_target,
            body=message.body,
            conversation_id=message.conversation_id,
            message_id=message.message_id,
            timestamp=message.timestamp,
            message_type=message.message_type,
            subject=message.subject,
            priority=message.priority,
            reply_to=message.reply_to,
            hop_count=message.hop_count,
            metadata=message.metadata,
        ).normalized()

    def _persist_reply_message(self, message: FabricMessage, delivery_target: str,
                               reply: AdapterReply, transcript_target: str | None) -> FabricMessage | None:
        if not reply.ok or not transcript_target or not (reply.body or '').strip():
            return None
        transcript_msg = FabricMessage(
            source=delivery_target,
            target=transcript_target,
            body=reply.body or '',
            conversation_id=message.conversation_id,
            reply_to=message.message_id,
            hop_count=message.hop_count + 1,
        ).normalized()
        self.storage.save_message(transcript_msg)
        self.event_bus.publish('message.accepted', {
            'message_id': transcript_msg.message_id,
            'conversation_id': transcript_msg.conversation_id,
            'source': transcript_msg.source,
            'target': transcript_msg.target,
            'priority': transcript_msg.priority,
        })
        return transcript_msg

    def _record_dead_letter(self, message: FabricMessage, delivery_target: str,
                            reply: AdapterReply, *, original_target: str,
                            reply_context: str | None, status: str) -> dict[str, Any]:
        dead_payload = {
            'message': message.to_dict(),
            'reply': reply.to_dict(),
        }
        self.storage.save_dead_letter(
            message.message_id,
            delivery_target,
            reason=reply.error or 'delivery_failed',
            payload=dead_payload,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        dead_letter = {
            'adapter_id': delivery_target,
            'reason': reply.error or 'delivery_failed',
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'original_target': original_target,
            'delivery_target': delivery_target,
            'reply_context': reply_context,
            'status': status,
        }
        self.event_bus.publish('dead-letter.recorded', dead_letter)
        return dead_letter

    def _save_visible_message(self, source: str, target: str, body: str, *,
                              conversation_id: str, reply_to: str | None = None,
                              metadata: dict[str, Any] | None = None) -> FabricMessage:
        message = FabricMessage(
            source=source,
            target=target,
            body=body,
            conversation_id=conversation_id,
            reply_to=reply_to,
            metadata=metadata or {},
        ).normalized()
        self.storage.save_message(message)
        self.event_bus.publish('message.accepted', {
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'source': message.source,
            'target': message.target,
            'priority': message.priority,
        })
        return message

    def _task_title(self, question: str) -> str:
        title = " ".join(question.split())
        return title[:117] + "..." if len(title) > 120 else title

    def _room_agents(self, room_name: str) -> list[str]:
        room = self.storage.get_room(room_name)
        if not room:
            return []
        return [
            str(member["adapter_id"])
            for member in room.get("members", [])
            if str(member.get("adapter_id")) in self.adapters
        ]

    def _agent_profile(self, agent_id: str) -> dict[str, Any]:
        agent = self.storage.get_agent(agent_id) or {}
        config = self.config.get("adapters", {}).get(agent_id, {})
        preferred_roles = list(agent.get("preferred_roles") or config.get("preferred_roles") or [])
        avoid_roles = list(agent.get("avoid_roles") or config.get("avoid_roles") or [])
        capabilities = list(agent.get("capabilities") or config.get("capabilities") or [])
        return {
            "cost_tier": str(agent.get("cost_tier") or config.get("cost_tier") or "medium").lower(),
            "usage_risk": str(agent.get("usage_risk") or config.get("usage_risk") or "medium").lower(),
            "preferred_roles": [str(item).lower() for item in preferred_roles],
            "avoid_roles": [str(item).lower() for item in avoid_roles],
            "capabilities": [str(item).lower() for item in capabilities],
            "speed": int(agent.get("speed") or config.get("speed") or 5),
            "trust": int(agent.get("trust") or config.get("trust") or 5),
            "config_role": str(config.get("role", "")).lower(),
        }

    def _profile_text(self, agent_id: str) -> str:
        profile = self._agent_profile(agent_id)
        return " ".join([
            profile["config_role"],
            " ".join(profile["preferred_roles"]),
            " ".join(profile["avoid_roles"]),
            " ".join(profile["capabilities"]),
            profile["cost_tier"],
            profile["usage_risk"],
        ]).lower()

    def _profile_score(self, agent_id: str, role: str, topic: str = "") -> int:
        profile = self._agent_profile(agent_id)
        roles = set(profile["preferred_roles"])
        avoided = set(profile["avoid_roles"])
        caps = set(profile["capabilities"])
        cost_tier = profile["cost_tier"]
        usage_risk = profile["usage_risk"]
        score = 0
        if role in roles:
            score += 40
        if role in avoided:
            score -= 60
        if usage_risk == "high":
            score -= 4
        elif usage_risk == "low":
            score += 3
        if role == "owner":
            deep_topic = any(term in str(topic).lower() for term in ("architecture", "design", "system", "plan", "strategy"))
            high_fit = "architecture" in caps or "coding" in caps or "files" in caps
            if cost_tier == "premium" and deep_topic and high_fit:
                score += 22
            elif cost_tier == "premium":
                score -= 8
            if "architecture" in caps:
                score += 15
            if deep_topic and "architecture" in caps:
                score += 20
            if cost_tier in {"cheap", "local"}:
                score += 4 if not deep_topic else -6
        elif role == "reviewer":
            if "reviewer" in roles:
                score += 20
            if {"review", "architecture", "quality", "risk"} & caps:
                score += 12
            if cost_tier in {"cheap", "local"} and not any(term in str(topic).lower() for term in ("architecture", "security", "risk")):
                score += 10
        elif role == "token_police":
            if cost_tier in {"cheap", "local"}:
                score += 30
            if "summary" in roles:
                score += 18
            if {"summary", "summaries", "tokens", "cost", "ops"} & caps:
                score += 15
        elif role == "guardrail":
            if "guardrail" in roles:
                score += 30
            if cost_tier == "premium":
                score += 8
            if {"architecture", "security", "risk", "governance"} & caps:
                score += 18
        elif role == "summary":
            if cost_tier in {"cheap", "local"}:
                score += 25
            if "summary" in roles or {"summary", "summaries"} & caps:
                score += 25
        score += profile["trust"] * 2
        if role in {"token_police", "summary"}:
            score += profile["speed"]
        return score

    def _team_prompt(
        self,
        phase: str,
        agent_id: str,
        body: str,
        *,
        conversation_id: str,
        progress_id: str,
        room_name: str,
        memory_context: str,
    ) -> FabricMessage:
        return FabricMessage(
            source="synkraken-team",
            target=agent_id,
            body=self._with_memory_context(body, memory_context),
            conversation_id=conversation_id,
            message_id=progress_id,
            reply_to=progress_id,
            metadata={
                "team_task": True,
                "phase": phase,
                "room_name": room_name,
                "room_memory_injected": bool(memory_context),
            },
        ).normalized()

    def _send_team_prompt(
        self,
        agent_id: str,
        phase: str,
        prompt: str,
        *,
        conversation_id: str,
        transcript_target: str,
        room_name: str,
        memory_context: str,
        reply_to: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        marker = self._save_visible_message(
            "synkraken-team",
            transcript_target,
            f"Team {phase}: {agent_id}",
            conversation_id=conversation_id,
            reply_to=reply_to,
            metadata={"team_task": True, "phase": phase, "agent_id": agent_id, "task_id": task_id},
        )
        runtime_name = self.adapters[agent_id].health().get("runtime_name", agent_id)
        delivery_message = self._team_prompt(
            phase,
            agent_id,
            prompt,
            conversation_id=conversation_id,
            progress_id=marker.message_id,
            room_name=room_name,
            memory_context=memory_context,
        )
        reply_context = transcript_target
        self._publish_delivery_queued(delivery_message, agent_id, runtime_name, agent_id, reply_context)
        self._publish_delivery_sent(delivery_message, agent_id, runtime_name, agent_id, reply_context, 1)
        self._publish_typing_started(delivery_message, agent_id, runtime_name, agent_id, reply_context)
        self._set_agent_working(agent_id, delivery_message, reply_context=reply_context, event_type="message_received")
        started = time.monotonic()
        try:
            reply = self.adapters[agent_id].send(delivery_message)
            status = self._reply_status(reply)
        except Exception as exc:  # noqa: BLE001
            reply, status = self._adapter_exception_reply(agent_id, exc)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if reply.duration_ms is None:
            reply.duration_ms = elapsed_ms
        self._publish_typing_stopped(delivery_message, agent_id, runtime_name, agent_id, reply_context, reply, status)
        delivery = self._record_delivery(
            delivery_message,
            reply,
            attempt=1,
            original_target=agent_id,
            delivery_target=agent_id,
            reply_context=reply_context,
            status=status,
        )
        self._set_agent_result(agent_id, delivery_message, reply, status, reply_context=reply_context)
        reply_message = None
        dead_letter = None
        if reply.ok:
            reply_message = self._save_visible_message(
                agent_id,
                transcript_target,
                reply.body or "",
                conversation_id=conversation_id,
                reply_to=marker.message_id,
                metadata={"team_task": True, "phase": phase, "agent_id": agent_id, "task_id": task_id},
            )
            delivery["reply_message_id"] = reply_message.message_id
            delivery["persisted_transcript_target"] = reply_message.target
        else:
            dead_letter = self._record_dead_letter(
                delivery_message,
                agent_id,
                reply,
                original_target=agent_id,
                reply_context=reply_context,
                status=status,
            )
            failure = self._save_visible_message(
                "synkraken-team",
                transcript_target,
                f"{agent_id} {status}: {reply.error or 'delivery_failed'}",
                conversation_id=conversation_id,
                reply_to=marker.message_id,
                metadata={"team_task": True, "phase": phase, "agent_id": agent_id, "status": status, "task_id": task_id},
            )
            delivery["reply_message_id"] = failure.message_id
            delivery["persisted_transcript_target"] = failure.target
        return {
            "agent_id": agent_id,
            "phase": phase,
            "status": status,
            "ok": reply.ok,
            "body": reply.body or "",
            "error": reply.error,
            "elapsed_ms": elapsed_ms,
            "message_id": reply_message.message_id if reply_message else None,
            "delivery": delivery,
            "dead_letter": dead_letter,
        }

    def _team_partial_transcript(self, room_name: str, conversation_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        return [
            message for message in self.storage.get_room_messages(room_name, limit=limit)
            if message.get("conversation_id") == conversation_id
        ]

    def _record_team_timeouts(
        self,
        team_run_id: str,
        *,
        room_name: str,
        conversation_id: str,
        results: list[dict[str, Any]],
    ) -> None:
        partial = self._team_partial_transcript(room_name, conversation_id)
        for item in results:
            if item.get("status") != "timeout":
                continue
            detail = {
                "team_run_id": team_run_id,
                "phase": item.get("phase"),
                "agent": item.get("agent_id"),
                "elapsed_ms": item.get("elapsed_ms"),
                "partial_transcript": partial,
            }
            self.storage.record_team_event(
                team_run_id,
                "timeout",
                actor=item.get("agent_id"),
                detail=json.dumps(detail, ensure_ascii=False),
            )

    def _block_team_run(
        self,
        result: dict[str, Any],
        *,
        phase: str,
        agent: str | None,
        reason: str,
        transcript_target: str,
        conversation_id: str,
        prompt_message_id: str,
        task_id: str,
        team_run_id: str,
        room_name: str,
        elapsed_ms: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        elapsed = f"{elapsed_ms}ms" if elapsed_ms is not None else "unknown"
        summary = (
            "Team run blocked.\n"
            f"Run: {team_run_id}\n"
            f"Phase: {phase}\n"
            f"Agent: {agent or '(unknown)'}\n"
            f"Elapsed: {elapsed}\n"
            f"Reason: {reason}\n"
            f"Inspect: /team-run {team_run_id}"
        )
        self.storage.update_task(task_id, {"status": "blocked"}, "synkraken-team", now)
        self.storage.record_task_event(task_id, "synkraken-team", "team_blocked", phase, reason, now)
        self.storage.update_team_run(team_run_id, {"status": "blocked", "completed_at": now})
        self.storage.record_team_event(team_run_id, "failed_phase", actor=agent or "synkraken-team", detail=phase, created_at=now)
        self.storage.record_team_event(team_run_id, "run_blocked", actor="synkraken-team", detail=reason, created_at=now)
        self._save_visible_message(
            "synkraken-team",
            transcript_target,
            summary,
            conversation_id=conversation_id,
            reply_to=prompt_message_id,
            metadata={
                "team_task": True,
                "phase": "blocked",
                "failed_phase": phase,
                "agent_id": agent,
                "task_id": task_id,
                "team_run_id": team_run_id,
                "status": "blocked",
            },
        )
        self.event_bus.publish("task.updated", {"task_id": task_id})
        self.event_bus.publish("team.blocked", {
            "team_run_id": team_run_id,
            "task_id": task_id,
            "room_name": room_name,
            "phase": phase,
            "agent": agent,
            "reason": reason,
            "elapsed_ms": elapsed_ms,
            "conversation_id": conversation_id,
        })
        result["status"] = "blocked"
        result["failure_summary"] = {
            "team_run_id": team_run_id,
            "phase": phase,
            "agent": agent,
            "elapsed_ms": elapsed_ms,
            "reason": reason,
            "partial_transcript": self._team_partial_transcript(room_name, conversation_id),
        }
        result["messages"] = self.storage.get_room_messages(room_name, limit=200)
        result["team_run"] = self.storage.get_team_run(team_run_id)
        result["team_events"] = self.storage.list_team_events(team_run_id) or []
        return result

    def _team_mentions(self, text: str, agents: list[str], label: str | None = None) -> list[str]:
        haystack = text.lower()
        if label:
            match = re.search(rf"{re.escape(label.lower())}\s*[:=-]\s*([a-z0-9_.-]+)", haystack)
            if match:
                candidate = match.group(1)
                for agent in agents:
                    if candidate == agent.lower():
                        return [agent]
        found = []
        for agent in agents:
            if re.search(rf"(?<![a-z0-9_.-])@?{re.escape(agent.lower())}(?![a-z0-9_.-])", haystack):
                found.append(agent)
        return found

    def _team_role_score(self, agent_id: str, question: str) -> int:
        adapter_config = self.config.get("adapters", {}).get(agent_id, {})
        capabilities = " ".join(str(item) for item in (adapter_config.get("capabilities", []) or []))
        haystack = f"{adapter_config.get('role', '')} {capabilities} {self._profile_text(agent_id)}".lower()
        terms = {term for term in re.findall(r"[a-z0-9_]+", question.lower()) if len(term) > 3}
        return sum(1 for term in terms if term in haystack) + self._profile_score(agent_id, "owner", question)

    def _choose_team_owner(
        self,
        agents: list[str],
        nomination_results: list[dict[str, Any]],
        question: str,
    ) -> tuple[str, list[str], dict[str, int], dict[str, int]]:
        owner_votes: Counter[str] = Counter()
        reviewer_votes: Counter[str] = Counter()
        for result in nomination_results:
            if not result.get("ok"):
                continue
            body = str(result.get("body") or "")
            owner_hits = self._team_mentions(body, agents, "owner") or self._team_mentions(body, agents, "best owner")
            reviewer_hits = self._team_mentions(body, agents, "reviewer")
            for agent in owner_hits[:1]:
                owner_votes[agent] += 1
            for agent in reviewer_hits:
                reviewer_votes[agent] += 1
        order = {agent: index for index, agent in enumerate(agents)}
        owner = max(
            agents,
            key=lambda agent: (owner_votes[agent], self._team_role_score(agent, question), -order[agent]),
        )
        reviewers = [
            agent for agent, _count in sorted(
                {agent: reviewer_votes[agent] for agent in agents if agent != owner}.items(),
                key=lambda item: (-item[1], -self._profile_score(item[0], "reviewer", question), order.get(item[0], 999)),
            )
            if agent != owner
        ]
        if not reviewers:
            reviewers = [agent for agent in agents if agent != owner][:1]
        return owner, reviewers[: max(1, min(2, len(reviewers)))], dict(owner_votes), dict(reviewer_votes)

    def _parse_team_memory_proposal(self, body: str) -> tuple[str, str] | None:
        text = str(body or "").strip()
        if not text or "NO_MEMORY" in text.upper():
            return None
        memory_type = "lesson"
        type_match = re.search(r"^\s*type\s*[:=-]\s*([a-z_]+)", text, flags=re.IGNORECASE | re.MULTILINE)
        if type_match and type_match.group(1).lower() in SHARED_MEMORY_TYPES:
            memory_type = type_match.group(1).lower()
        memory_match = re.search(r"^\s*memory\s*[:=-]\s*(.+)", text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        content = memory_match.group(1).strip() if memory_match else text
        content = content.splitlines()[0].strip() if "\n" in content else content
        if not content:
            return None
        return memory_type, content

    def _collect_team_memory_proposals(
        self,
        *,
        agents: list[str],
        room_name: str,
        question: str,
        final_report: str,
        conversation_id: str,
        transcript_target: str,
        memory_context: str,
        task_id: str,
        team_run_id: str,
    ) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []
        prompt = (
            "Team Task Mode - Shared Memory Proposal\n\n"
            f"Original task:\n{question}\n\n"
            f"Final report:\n{final_report}\n\n"
            "If this run produced a useful, durable, safe-to-reuse memory for future work, propose exactly one. "
            "Otherwise reply exactly NO_MEMORY.\n\n"
            "Use this format when proposing:\nType: fact|decision|preference|rule|lesson|technical_note|project_context\nMemory: <one concise memory under the configured limit>\n"
            "Do not include transient details from the current message."
        )
        for agent in agents:
            result = self._send_team_prompt(
                agent,
                "memory",
                prompt,
                conversation_id=conversation_id,
                transcript_target=transcript_target,
                room_name=room_name,
                memory_context=memory_context,
                task_id=task_id,
            )
            parsed = self._parse_team_memory_proposal(result.get("body") or "")
            if not result.get("ok") or not parsed:
                proposals.append({"agent_id": agent, "status": "none", "delivery": result.get("delivery")})
                continue
            memory_type, content = parsed
            proposed = self.propose_memory({
                "created_by": agent,
                "room_name": room_name,
                "workspace": self.workspace,
                "memory_type": memory_type,
                "content": content,
                "source_team_run_id": team_run_id,
                "source_task_id": task_id,
                "auto_review": True,
            })
            proposals.append({"agent_id": agent, "status": proposed.get("status"), "memory": proposed.get("memory")})
        self.storage.record_team_event(
            team_run_id,
            "memory_proposals_collected",
            actor="synkraken-team",
            detail=json.dumps([
                {"agent_id": item.get("agent_id"), "status": item.get("status"), "memory_id": (item.get("memory") or {}).get("memory_id")}
                for item in proposals
            ], ensure_ascii=False),
        )
        return proposals

    def team_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = str(payload.get("source", "operator")).strip() or "operator"
        room_name = str(payload.get("room_name", "")).strip()
        question = str(payload.get("question", "")).strip()
        turns = int(payload.get("turns", 4))
        approval_mode = str(payload.get("approval_mode", "AUTO")).strip().upper() or "AUTO"
        if approval_mode not in {"AUTO", "REVIEW_REQUIRED"}:
            raise ValueError("approval_mode must be AUTO or REVIEW_REQUIRED")
        approval_required = approval_mode == "REVIEW_REQUIRED"
        if not room_name:
            raise ValueError("Team mode needs a room. Create or select a room first.")
        if not self.storage.room_exists(room_name):
            raise ValueError(f"room not found: {room_name}")
        if not question:
            raise ValueError("question required")
        if turns < 1 or turns > 20:
            raise ValueError("turns must be between 1 and 20")
        agents = self._room_agents(room_name)
        if not agents:
            raise ValueError(f"room has no available agents: {room_name}")

        transcript_target = f"room:{room_name}"
        memory_context, memory_items = self._prompt_memory_context(room_name)
        prompt_message = FabricMessage(
            source=source,
            target=transcript_target,
            body=f"Team task: {question}",
            metadata={"team_task": True, "phase": "prompt", "turns": turns, "agents": agents},
        ).normalized()
        self.storage.save_message(prompt_message)
        self.event_bus.publish("message.accepted", {
            "message_id": prompt_message.message_id,
            "conversation_id": prompt_message.conversation_id,
            "source": prompt_message.source,
            "target": prompt_message.target,
            "priority": prompt_message.priority,
        })
        conversation_id = prompt_message.conversation_id
        now = utc_now_iso()
        task = self.storage.create_task(
            task_id=new_id(),
            title=self._task_title(question),
            description=f"Team Task Mode v0.1\n\n{question}",
            status="open",
            priority="normal",
            room_name=room_name,
            assigned_agent_id=None,
            source_message_id=prompt_message.message_id,
            actor=source,
            created_at=now,
        )
        task_id = task["task_id"]
        team_run_id = new_id()
        self.storage.create_team_run(
            team_run_id=team_run_id,
            task_id=task_id,
            room_name=room_name,
            source_prompt=question,
            owner_agent=None,
            reviewers=[],
            participants=agents,
            status="running",
            started_at=now,
            approval_required=approval_required,
        )
        self.storage.record_team_event(team_run_id, "team_started", actor=source, detail=question, created_at=now)
        self.storage.record_task_event(task_id, "synkraken-team", "team_started", None, question)
        self.event_bus.publish("task.created", {"task_id": task_id})
        self.event_bus.publish("team.phase", {"team_run_id": team_run_id, "task_id": task_id, "room_name": room_name, "phase": "clarify"})

        result: dict[str, Any] = {
            "team_run_id": team_run_id,
            "task_id": task_id,
            "room_name": room_name,
            "question": question,
            "agents": agents,
            "turns": turns,
            "owner": None,
            "reviewers": [],
            "approval_required": approval_required,
            "approval_mode": approval_mode,
            "status": "running",
            "final_report": "",
            "phases": {},
            "deliveries": [],
            "dead_letters": [],
            "memory_context": memory_context,
            "memory_items": memory_items,
            "memory_proposals": [],
            "conversation_id": conversation_id,
        }

        clarify_prompt = (
            f"Team Task Mode - Clarify\n\nOriginal task:\n{question}\n\n"
            "Restate the task in your own words. Identify the skills needed. "
            "Say whether you are suited to help. Do not message another agent; "
            "SynKraken will coordinate all phases in this room transcript."
        )
        clarify_results = [
            self._send_team_prompt(
                agent, "clarify", clarify_prompt,
                conversation_id=conversation_id, transcript_target=transcript_target,
                room_name=room_name, memory_context=memory_context,
                reply_to=prompt_message.message_id, task_id=task_id,
            )
            for agent in agents
        ]
        result["phases"]["clarify"] = clarify_results
        result["deliveries"].extend(item["delivery"] for item in clarify_results)
        result["dead_letters"].extend(item["dead_letter"] for item in clarify_results if item["dead_letter"])
        self._record_team_timeouts(
            team_run_id,
            room_name=room_name,
            conversation_id=conversation_id,
            results=clarify_results,
        )
        available = [item["agent_id"] for item in clarify_results if item["ok"]]
        self.storage.record_team_event(team_run_id, "clarify_complete", actor="synkraken-team", detail=", ".join(available))
        if not available:
            first_timeout = next((item for item in clarify_results if item.get("status") == "timeout"), None)
            return self._block_team_run(
                result,
                phase="clarify",
                agent=first_timeout.get("agent_id") if first_timeout else None,
                reason="all agents failed during clarify",
                transcript_target=transcript_target,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message.message_id,
                task_id=task_id,
                team_run_id=team_run_id,
                room_name=room_name,
                elapsed_ms=first_timeout.get("elapsed_ms") if first_timeout else None,
            )

        self.event_bus.publish("team.phase", {"team_run_id": team_run_id, "task_id": task_id, "room_name": room_name, "phase": "nominate"})
        clarify_summary = "\n\n".join(f"{item['agent_id']}: {item['body']}" for item in clarify_results if item["ok"])
        nominate_prompt = (
            f"Team Task Mode - Nominate\n\nOriginal task:\n{question}\n\n"
            f"Clarifications:\n{clarify_summary}\n\n"
            f"Available agents: {', '.join(available)}\n\n"
            "Nominate exactly one best owner and one reviewer. You may name an optional supporting agent. "
            "Use this format:\nOwner: <agent_id>\nReviewer: <agent_id>\nSupport: <agent_id or none>\n"
            "Do not message another agent."
        )
        nomination_results = [
            self._send_team_prompt(
                agent, "nominate", nominate_prompt,
                conversation_id=conversation_id, transcript_target=transcript_target,
                room_name=room_name, memory_context=memory_context,
                reply_to=prompt_message.message_id, task_id=task_id,
            )
            for agent in available
        ]
        result["phases"]["nominate"] = nomination_results
        result["deliveries"].extend(item["delivery"] for item in nomination_results)
        result["dead_letters"].extend(item["dead_letter"] for item in nomination_results if item["dead_letter"])
        self._record_team_timeouts(
            team_run_id,
            room_name=room_name,
            conversation_id=conversation_id,
            results=nomination_results,
        )
        owner, reviewers, owner_votes, reviewer_votes = self._choose_team_owner(available, nomination_results, question)
        result["owner"] = owner
        result["reviewers"] = reviewers
        result["owner_votes"] = owner_votes
        result["reviewer_votes"] = reviewer_votes
        self.storage.record_task_event(task_id, "synkraken-team", "nominated", None, str(owner_votes))
        self.storage.record_team_event(team_run_id, "owner_nominated", actor="synkraken-team", detail=str(owner_votes))
        self.storage.update_task(task_id, {"assigned_agent_id": owner, "status": "in_progress"}, "synkraken-team", utc_now_iso())
        self.storage.update_team_run(team_run_id, {"owner_agent": owner, "reviewers": reviewers})
        self.storage.record_team_event(team_run_id, "owner_selected", actor="synkraken-team", detail=owner)
        self.event_bus.publish("task.updated", {"task_id": task_id})
        selection_body = (
            f"Team owner selected: {owner}\n"
            f"Reviewers: {', '.join(reviewers) or '(none)'}\n"
            f"Owner votes: {owner_votes or {}}\n"
            f"Reviewer votes: {reviewer_votes or {}}\n"
            "Selection rule: most nominations wins; ties use configured role/capability score, then room order."
        )
        self._save_visible_message(
            "synkraken-team", transcript_target, selection_body,
            conversation_id=conversation_id, reply_to=prompt_message.message_id,
            metadata={"team_task": True, "phase": "owner_selected", "task_id": task_id, "owner": owner, "reviewers": reviewers},
        )

        self.event_bus.publish("team.phase", {"team_run_id": team_run_id, "task_id": task_id, "room_name": room_name, "phase": "execute"})
        self.storage.record_team_event(team_run_id, "execution_started", actor="synkraken-team", detail=owner)
        team_summary = "\n\n".join([
            "Clarifications:",
            clarify_summary or "(none)",
            "Nominations:",
            "\n".join(f"{item['agent_id']}: {item['body']}" for item in nomination_results if item["ok"]) or "(none)",
            selection_body,
        ])
        owner_candidates = [owner] + [agent for agent in available if agent != owner]
        owner_output = None
        owner_result = None
        attempted_owners = []
        for candidate in owner_candidates:
            attempted_owners.append(candidate)
            execute_prompt = (
                f"Team Task Mode - Execute\n\nOriginal task:\n{question}\n\n"
                f"Team discussion summary:\n{team_summary}\n\n"
                "You are the selected owner. Produce the proposed answer or work for the human operator. "
                "Do not message another agent; SynKraken will send your output for review."
            )
            owner_result = self._send_team_prompt(
                candidate, "execute", execute_prompt,
                conversation_id=conversation_id, transcript_target=transcript_target,
                room_name=room_name, memory_context=memory_context,
                reply_to=prompt_message.message_id, task_id=task_id,
            )
            result["deliveries"].append(owner_result["delivery"])
            if owner_result["dead_letter"]:
                result["dead_letters"].append(owner_result["dead_letter"])
            self._record_team_timeouts(
                team_run_id,
                room_name=room_name,
                conversation_id=conversation_id,
                results=[owner_result],
            )
            if owner_result["ok"]:
                if candidate != owner:
                    self.storage.record_task_event(task_id, "synkraken-team", "owner_fallback", owner, candidate)
                    self.storage.record_team_event(team_run_id, "owner_selected", actor="synkraken-team", detail=f"fallback {owner} -> {candidate}")
                    owner = candidate
                    result["owner"] = owner
                    reviewers = [agent for agent in reviewers if agent != owner] or [agent for agent in available if agent != owner][:1]
                    result["reviewers"] = reviewers
                    self.storage.update_task(task_id, {"assigned_agent_id": owner}, "synkraken-team", utc_now_iso())
                    self.storage.update_team_run(team_run_id, {"owner_agent": owner, "reviewers": reviewers})
                owner_output = owner_result["body"]
                break
        result["phases"]["execute"] = {"attempted_owners": attempted_owners, "result": owner_result}
        if not owner_output:
            failed = owner_result or {}
            return self._block_team_run(
                result,
                phase="execute",
                agent=failed.get("agent_id"),
                reason="no available owner produced output",
                transcript_target=transcript_target,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message.message_id,
                task_id=task_id,
                team_run_id=team_run_id,
                room_name=room_name,
                elapsed_ms=failed.get("elapsed_ms"),
            )

        self.storage.record_team_event(team_run_id, "execution_completed", actor=owner)
        self.event_bus.publish("team.phase", {"team_run_id": team_run_id, "task_id": task_id, "room_name": room_name, "phase": "review"})
        self.storage.record_team_event(team_run_id, "review_started", actor="synkraken-team", detail=", ".join(reviewers))
        review_results = []
        for reviewer in reviewers:
            review_prompt = (
                f"Team Task Mode - Review\n\nOriginal task:\n{question}\n\n"
                f"Owner: {owner}\n\nOwner output:\n{owner_output}\n\n"
                "Provide critique, risks, missing pieces, and suggested improvement. "
                "Do not message another agent."
            )
            review = self._send_team_prompt(
                reviewer, "review", review_prompt,
                conversation_id=conversation_id, transcript_target=transcript_target,
                room_name=room_name, memory_context=memory_context,
                reply_to=prompt_message.message_id, task_id=task_id,
            )
            review_results.append(review)
            result["deliveries"].append(review["delivery"])
            if review["dead_letter"]:
                result["dead_letters"].append(review["dead_letter"])
        result["phases"]["review"] = review_results
        self._record_team_timeouts(
            team_run_id,
            room_name=room_name,
            conversation_id=conversation_id,
            results=review_results,
        )
        timed_out_review = next((item for item in review_results if item.get("status") == "timeout"), None)
        if timed_out_review:
            return self._block_team_run(
                result,
                phase="review",
                agent=timed_out_review.get("agent_id"),
                reason=timed_out_review.get("error") or "review timed out",
                transcript_target=transcript_target,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message.message_id,
                task_id=task_id,
                team_run_id=team_run_id,
                room_name=room_name,
                elapsed_ms=timed_out_review.get("elapsed_ms"),
            )
        self.storage.record_task_event(
            task_id,
            "synkraken-team",
            "reviewed",
            owner,
            ", ".join(item["agent_id"] for item in review_results if item["ok"]) or "no successful reviews",
        )
        self.storage.record_team_event(
            team_run_id,
            "review_completed",
            actor="synkraken-team",
            detail=", ".join(item["agent_id"] for item in review_results if item["ok"]) or "no successful reviews",
        )

        self.event_bus.publish("team.phase", {"team_run_id": team_run_id, "task_id": task_id, "room_name": room_name, "phase": "final"})
        review_summary = "\n\n".join(f"{item['agent_id']}: {item['body']}" for item in review_results if item["ok"]) or "(no successful reviewer feedback)"
        final_prompt = (
            f"Team Task Mode - Final Report\n\nOriginal task:\n{question}\n\n"
            f"Owner output:\n{owner_output}\n\n"
            f"Reviewer feedback:\n{review_summary}\n\n"
            "Produce the final answer for the room with these sections: recommended solution, who did what, "
            "reviewer feedback, next action, confidence/risks. Do not message another agent."
        )
        final_result = self._send_team_prompt(
            owner, "final", final_prompt,
            conversation_id=conversation_id, transcript_target=transcript_target,
            room_name=room_name, memory_context=memory_context,
            reply_to=prompt_message.message_id, task_id=task_id,
        )
        result["phases"]["final"] = final_result
        result["deliveries"].append(final_result["delivery"])
        if final_result["dead_letter"]:
            result["dead_letters"].append(final_result["dead_letter"])
        self._record_team_timeouts(
            team_run_id,
            room_name=room_name,
            conversation_id=conversation_id,
            results=[final_result],
        )
        if final_result.get("status") == "timeout":
            return self._block_team_run(
                result,
                phase="final",
                agent=final_result.get("agent_id"),
                reason=final_result.get("error") or "final report timed out",
                transcript_target=transcript_target,
                conversation_id=conversation_id,
                prompt_message_id=prompt_message.message_id,
                task_id=task_id,
                team_run_id=team_run_id,
                room_name=room_name,
                elapsed_ms=final_result.get("elapsed_ms"),
            )
        if final_result["ok"]:
            result["final_report"] = final_result["body"]
            self.storage.update_team_run(team_run_id, {"final_report": final_result["body"]})
            self.storage.record_team_event(team_run_id, "final_report", actor=owner)
            if approval_required:
                result["status"] = "awaiting_approval"
                self.storage.update_team_run(team_run_id, {"status": "awaiting_approval"})
                self._save_visible_message(
                    "synkraken-team", transcript_target,
                    f"Team run awaiting approval: {team_run_id}\nApprove? /approve {team_run_id}\nReject? /reject {team_run_id}",
                    conversation_id=conversation_id, reply_to=prompt_message.message_id,
                    metadata={"team_task": True, "phase": "approval_required", "task_id": task_id, "team_run_id": team_run_id},
                )
            else:
                result["status"] = "completed"
                completed_at = utc_now_iso()
                self.storage.update_team_run(team_run_id, {"status": "completed", "completed_at": completed_at})
                self.storage.update_task(task_id, {"status": "done"}, "synkraken-team", completed_at)
                self.storage.record_task_event(task_id, "synkraken-team", "team_completed", owner, "done", completed_at)
                self.event_bus.publish("task.updated", {"task_id": task_id})
        else:
            fallback_report = (
                "Team task completed with owner output, but final report generation failed.\n\n"
                f"Owner: {owner}\nReviewers: {', '.join(reviewers) or '(none)'}\n\n"
                f"Owner output:\n{owner_output}\n\nReviewer feedback:\n{review_summary}"
            )
            self._save_visible_message(
                "synkraken-team", transcript_target, fallback_report,
                conversation_id=conversation_id, reply_to=prompt_message.message_id,
                metadata={"team_task": True, "phase": "final_fallback", "task_id": task_id},
            )
            result["final_report"] = fallback_report
            self.storage.update_team_run(team_run_id, {"final_report": fallback_report})
            self.storage.record_team_event(team_run_id, "final_report", actor="synkraken-team", detail="fallback")
            if approval_required:
                result["status"] = "awaiting_approval"
                self.storage.update_team_run(team_run_id, {"status": "awaiting_approval"})
                self._save_visible_message(
                    "synkraken-team", transcript_target,
                    f"Team run awaiting approval: {team_run_id}\nApprove? /approve {team_run_id}\nReject? /reject {team_run_id}",
                    conversation_id=conversation_id, reply_to=prompt_message.message_id,
                    metadata={"team_task": True, "phase": "approval_required", "task_id": task_id, "team_run_id": team_run_id},
                )
            else:
                result["status"] = "completed_with_final_failure"
                completed_at = utc_now_iso()
                self.storage.update_team_run(team_run_id, {"status": "completed_with_final_failure", "completed_at": completed_at})
                self.storage.update_task(task_id, {"status": "done"}, "synkraken-team", completed_at)
                self.storage.record_task_event(task_id, "synkraken-team", "team_completed", owner, "final_failed", completed_at)
                self.event_bus.publish("task.updated", {"task_id": task_id})

        if result.get("final_report"):
            result["memory_proposals"] = self._collect_team_memory_proposals(
                agents=available,
                room_name=room_name,
                question=question,
                final_report=result["final_report"],
                conversation_id=conversation_id,
                transcript_target=transcript_target,
                memory_context=memory_context,
                task_id=task_id,
                team_run_id=team_run_id,
            )

        self.event_bus.publish("team.completed", {
            "team_run_id": team_run_id,
            "task_id": task_id,
            "room_name": room_name,
            "owner": owner,
            "reviewers": reviewers,
            "status": result["status"],
            "conversation_id": conversation_id,
        })
        result["messages"] = self.storage.get_room_messages(room_name, limit=200)
        result["team_run"] = self.storage.get_team_run(team_run_id)
        result["team_events"] = self.storage.list_team_events(team_run_id) or []
        return result

    def approve_team_run(self, team_run_id: str, actor: str = "operator") -> dict[str, Any]:
        run = self.storage.get_team_run(team_run_id)
        if not run:
            raise ValueError(f"team run not found: {team_run_id}")
        if run["status"] != "awaiting_approval":
            raise ValueError(f"team run is not awaiting approval: {team_run_id}")
        now = utc_now_iso()
        self.storage.update_team_run(team_run_id, {
            "status": "approved",
            "approved_by": actor,
            "completed_at": now,
        })
        self.storage.record_team_event(team_run_id, "approved", actor=actor, created_at=now)
        if run.get("task_id"):
            self.storage.update_task(run["task_id"], {"status": "done"}, actor, now)
            self.storage.record_task_event(run["task_id"], actor, "team_completed", run.get("owner_agent"), "approved", now)
            self.event_bus.publish("task.updated", {"task_id": run["task_id"]})
        message = self._save_visible_message(
            actor,
            f"room:{run['room_name']}",
            f"Approved team run: {team_run_id}",
            conversation_id=team_run_id,
            metadata={"team_run_id": team_run_id, "team_governance": True, "event": "approved"},
        )
        self.event_bus.publish("team.approved", {"team_run_id": team_run_id, "approved_by": actor})
        updated = self.storage.get_team_run(team_run_id)
        return {"team_run": updated, "message": message.to_dict(), "events": self.storage.list_team_events(team_run_id) or []}

    def reject_team_run(self, team_run_id: str, actor: str = "operator") -> dict[str, Any]:
        run = self.storage.get_team_run(team_run_id)
        if not run:
            raise ValueError(f"team run not found: {team_run_id}")
        if run["status"] != "awaiting_approval":
            raise ValueError(f"team run is not awaiting approval: {team_run_id}")
        now = utc_now_iso()
        self.storage.update_team_run(team_run_id, {
            "status": "rejected",
            "approved_by": actor,
            "completed_at": now,
        })
        self.storage.record_team_event(team_run_id, "rejected", actor=actor, created_at=now)
        if run.get("task_id"):
            self.storage.update_task(run["task_id"], {"status": "blocked"}, actor, now)
            self.event_bus.publish("task.updated", {"task_id": run["task_id"]})
        message = self._save_visible_message(
            actor,
            f"room:{run['room_name']}",
            f"Rejected team run: {team_run_id}",
            conversation_id=team_run_id,
            metadata={"team_run_id": team_run_id, "team_governance": True, "event": "rejected"},
        )
        self.event_bus.publish("team.rejected", {"team_run_id": team_run_id, "rejected_by": actor})
        updated = self.storage.get_team_run(team_run_id)
        return {"team_run": updated, "message": message.to_dict(), "events": self.storage.list_team_events(team_run_id) or []}

    def _memory_review_prompt(self, memory: dict[str, Any]) -> str:
        return (
            "Shared Memory peer review v0.1\n\n"
            "Review the proposed memory below. Answer these questions:\n"
            "- Is this useful?\n"
            "- Is this durable beyond the current message?\n"
            "- Is it safe to reuse?\n"
            "- Is it too vague?\n"
            "- Should it be shortened?\n"
            "- What memory_type is best?\n"
            "- Confidence 0-100\n\n"
            "Return a concise result with:\n"
            "Decision: approve or reject\n"
            "Confidence: <0-100>\n"
            "Memory type: fact|decision|preference|rule|lesson|technical_note|project_context\n"
            "Reason: <short reason>\n\n"
            f"Proposed memory type: {memory.get('memory_type')}\n"
            f"Content:\n{memory.get('content')}"
        )

    def _parse_memory_review(self, body: str, default_type: str) -> dict[str, Any]:
        text = str(body or "")
        lowered = text.lower()
        reject = "reject" in lowered and "approve" not in lowered
        approve = "approve" in lowered and not reject
        if not approve and not reject:
            approve = any(word in lowered for word in ("useful", "safe to reuse", "durable"))
        match = re.search(r"(?:confidence|score)\s*[:=-]?\s*(\d{1,3})", lowered)
        confidence = int(match.group(1)) if match else 0
        confidence = max(0, min(100, confidence))
        type_match = re.search(r"(fact|decision|preference|rule|lesson|technical_note|project_context)", lowered)
        memory_type = type_match.group(1) if type_match else default_type
        reason_match = re.search(r"reason\s*[:=-]\s*(.+)", text, flags=re.IGNORECASE | re.DOTALL)
        reason = reason_match.group(1).strip() if reason_match else text.strip()
        return {
            "decision": "approve" if approve else "reject",
            "confidence": confidence,
            "memory_type": memory_type,
            "reason": reason[:1000],
        }

    def _memory_visible(self, room_name: str | None, body: str, *, memory_id: str,
                        actor: str, event: str) -> FabricMessage | None:
        if not room_name or not self.storage.room_exists(room_name):
            return None
        return self._save_visible_message(
            actor,
            f"room:{room_name}",
            body,
            conversation_id=memory_id,
            metadata={"shared_memory": True, "memory_id": memory_id, "event": event},
        )

    def _memory_reviewer(self, created_by: str | None, room_name: str | None) -> str | None:
        candidates = self._room_agents(room_name) if room_name else list(self.adapters.keys())
        if not candidates:
            candidates = list(self.adapters.keys())
        for agent_id in candidates:
            if agent_id != created_by and agent_id in self.adapters:
                return agent_id
        return None

    def memory_budget(self, *, room_name: str | None = None) -> dict[str, Any]:
        memories = self.storage.select_shared_memory_for_injection(
            room_name=room_name,
            workspace=self.workspace,
            max_items=self.memory_max_items_injected,
            max_chars=self.memory_max_chars_injected,
            min_confidence=self.memory_min_confidence,
        )
        text = "\n".join(f"- {item['memory_type']}: {item['content']}" for item in memories)
        return {
            "approved_memories": len(self.storage.list_shared_memory(status="peer_approved", limit=1000)),
            "injected_max_items": self.memory_max_items_injected,
            "injected_max_chars": self.memory_max_chars_injected,
            "max_memory_chars": self.memory_max_memory_chars,
            "min_confidence": self.memory_min_confidence,
            "estimated_chars": len(text),
            "estimated_tokens": max(1, len(text) // 4) if text else 0,
            "selected": memories,
        }

    def propose_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = " ".join(str(payload.get("content", "")).split())
        if not content:
            raise ValueError("content required")
        memory_type = str(payload.get("memory_type", "fact")).strip() or "fact"
        if memory_type not in SHARED_MEMORY_TYPES:
            raise ValueError(f"invalid memory_type: {memory_type}")
        room_name = payload.get("room_name")
        room_name = str(room_name).strip() if room_name is not None else None
        room_name = room_name or None
        if room_name and not self.storage.room_exists(room_name):
            raise ValueError(f"room not found: {room_name}")
        workspace = str(payload.get("workspace") or self.workspace or "").strip() or None
        actor = str(payload.get("created_by") or payload.get("actor") or "operator").strip() or "operator"
        now = utc_now_iso()
        memory_id = str(payload.get("memory_id") or "").strip() or new_id()
        duplicate = self.storage.find_duplicate_memory(content, room_name=room_name, workspace=workspace)
        too_long = len(content) > self.memory_max_memory_chars
        initial_status = "rejected" if duplicate or too_long else "proposed"
        confidence = int(payload.get("confidence", 0) or 0)
        memory = self.storage.create_shared_memory(
            memory_id=memory_id,
            room_name=room_name,
            workspace=workspace,
            memory_type=memory_type,
            content=content,
            status=initial_status,
            confidence=confidence,
            created_by=actor,
            created_at=now,
            source_team_run_id=payload.get("source_team_run_id"),
            source_task_id=payload.get("source_task_id"),
            source_message_id=payload.get("source_message_id"),
        )
        self._memory_visible(
            room_name,
            f"Shared memory proposed: {memory_id}\nType: {memory_type}\nContent: {content}",
            memory_id=memory_id,
            actor=actor,
            event="memory_proposed",
        )
        if duplicate or too_long:
            reason = "duplicate memory" if duplicate else f"content too long ({len(content)} > {self.memory_max_memory_chars})"
            memory = self.storage.update_shared_memory(
                memory_id,
                {
                    "status": "rejected",
                    "review_result": "reject",
                    "review_reason": reason,
                    "reviewed_by": "synkraken",
                    "reviewed_at": now,
                },
                actor="synkraken",
                event_type="peer_rejected",
            ) or memory
            self._memory_visible(
                room_name,
                f"Shared memory rejected: {memory_id}\nReason: {reason}",
                memory_id=memory_id,
                actor="synkraken",
                event="peer_rejected",
            )
            return {"memory": memory, "review": None, "status": memory["status"], "duplicate": duplicate}
        reviewer = self._memory_reviewer(actor, room_name)
        if reviewer:
            self.storage.record_shared_memory_event(
                memory_id,
                "peer_review_requested",
                actor="synkraken",
                details={"reviewer": reviewer},
            )
            self._memory_visible(
                room_name,
                f"Peer review requested for shared memory: {memory_id}\nReviewer: {reviewer}",
                memory_id=memory_id,
                actor="synkraken",
                event="peer_review_requested",
            )
            if payload.get("auto_review", True):
                return self.review_memory(memory_id, {"actor": reviewer, "reviewer": reviewer, "auto": True})
        return {"memory": memory, "reviewer": reviewer, "status": memory["status"]}

    def review_memory(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        memory = self.storage.get_shared_memory(memory_id)
        if not memory:
            raise ValueError(f"memory not found: {memory_id}")
        reviewer = str(payload.get("reviewer") or payload.get("actor") or "operator").strip() or "operator"
        review_body = str(payload.get("review") or "").strip()
        if not review_body and reviewer not in self.adapters:
            reviewer = self._memory_reviewer(memory.get("created_by"), memory.get("room_name")) or reviewer
        if reviewer == memory.get("created_by"):
            raise ValueError("memory reviewer must differ from creator")
        delivery = None
        if not review_body and reviewer in self.adapters:
            prompt = self._memory_review_prompt(memory)
            delivery_message = FabricMessage(
                source="synkraken-memory",
                target=reviewer,
                body=prompt,
                conversation_id=memory_id,
                metadata={"shared_memory": True, "memory_id": memory_id, "phase": "review"},
            ).normalized()
            self.storage.save_message(delivery_message)
            self._set_agent_working(reviewer, delivery_message, reply_context=f"room:{memory['room_name']}" if memory.get("room_name") else None)
            try:
                reply = self.adapters[reviewer].send(delivery_message)
                status = self._reply_status(reply)
            except Exception as exc:  # noqa: BLE001
                reply, status = self._adapter_exception_reply(reviewer, exc)
            delivery = self._record_delivery(
                delivery_message,
                reply,
                attempt=1,
                original_target=reviewer,
                delivery_target=reviewer,
                reply_context=f"room:{memory['room_name']}" if memory.get("room_name") else None,
                status=status,
            )
            self._set_agent_result(reviewer, delivery_message, reply, status, reply_context=f"room:{memory['room_name']}" if memory.get("room_name") else None)
            if not reply.ok:
                review_body = f"Decision: reject\nConfidence: 0\nReason: {reply.error or 'review failed'}"
            else:
                review_body = reply.body or ""
        parsed = self._parse_memory_review(review_body, str(memory.get("memory_type") or "fact"))
        confidence = int(payload.get("confidence", parsed["confidence"]) or parsed["confidence"])
        decision = str(payload.get("decision", parsed["decision"])).lower()
        memory_type = str(payload.get("memory_type", parsed["memory_type"]))
        reason = str(payload.get("reason", parsed["reason"])).strip()
        now = utc_now_iso()
        duplicate = self.storage.find_duplicate_memory(
            str(memory.get("content") or ""),
            room_name=memory.get("room_name"),
            workspace=memory.get("workspace"),
        )
        duplicate_detected = bool(duplicate and duplicate.get("memory_id") != memory_id)
        too_long = len(str(memory.get("content") or "")) > self.memory_max_memory_chars
        approve = decision == "approve" and confidence >= self.memory_min_confidence and not duplicate_detected and not too_long
        status = "peer_approved" if approve else "rejected"
        if duplicate_detected:
            reason = reason or "duplicate memory"
        if too_long:
            reason = reason or f"content too long ({len(str(memory.get('content') or ''))} > {self.memory_max_memory_chars})"
        if confidence < self.memory_min_confidence:
            reason = reason or f"confidence below {self.memory_min_confidence}"
        fields: dict[str, Any] = {
            "status": status,
            "confidence": confidence,
            "memory_type": memory_type,
            "reviewed_by": reviewer,
            "review_result": "approve" if approve else "reject",
            "review_reason": reason,
            "reviewed_at": now,
        }
        if approve:
            fields["approved_by"] = reviewer
            fields["approved_at"] = now
        updated = self.storage.update_shared_memory(
            memory_id,
            fields,
            actor=reviewer,
            event_type="peer_approved" if approve else "peer_rejected",
        )
        self._memory_visible(
            memory.get("room_name"),
            f"Shared memory peer {'approved' if approve else 'rejected'}: {memory_id}\nReviewer: {reviewer}\nConfidence: {confidence}\nReason: {reason or '(none)'}",
            memory_id=memory_id,
            actor=reviewer,
            event="peer_approved" if approve else "peer_rejected",
        )
        self.event_bus.publish("memory.reviewed", {"memory_id": memory_id, "status": status, "reviewer": reviewer})
        return {"memory": updated, "review": parsed, "delivery": delivery, "status": status}

    def approve_memory(self, memory_id: str, actor: str = "operator") -> dict[str, Any]:
        memory = self.storage.get_shared_memory(memory_id)
        if not memory:
            raise ValueError(f"memory not found: {memory_id}")
        now = utc_now_iso()
        updated = self.storage.update_shared_memory(
            memory_id,
            {"status": "peer_approved", "approved_by": actor, "approved_at": now},
            actor=actor,
            event_type="human_overridden",
        )
        self._memory_visible(memory.get("room_name"), f"Shared memory approved by human override: {memory_id}", memory_id=memory_id, actor=actor, event="human_overridden")
        return {"memory": updated}

    def reject_memory(self, memory_id: str, actor: str = "operator", reason: str | None = None) -> dict[str, Any]:
        memory = self.storage.get_shared_memory(memory_id)
        if not memory:
            raise ValueError(f"memory not found: {memory_id}")
        updated = self.storage.update_shared_memory(
            memory_id,
            {"status": "rejected", "review_result": "reject", "review_reason": reason or "human override"},
            actor=actor,
            event_type="human_overridden",
        )
        self._memory_visible(memory.get("room_name"), f"Shared memory rejected by human override: {memory_id}", memory_id=memory_id, actor=actor, event="human_overridden")
        return {"memory": updated}

    def archive_memory(self, memory_id: str, actor: str = "operator") -> dict[str, Any]:
        memory = self.storage.get_shared_memory(memory_id)
        if not memory:
            raise ValueError(f"memory not found: {memory_id}")
        updated = self.storage.update_shared_memory(
            memory_id,
            {"status": "archived"},
            actor=actor,
            event_type="memory_archived",
        )
        self._memory_visible(memory.get("room_name"), f"Shared memory archived: {memory_id}", memory_id=memory_id, actor=actor, event="memory_archived")
        return {"memory": updated}

    # ── Goal Mode ────────────────────────────────────────────────────────

    def _compact_text(self, text: str, limit: int) -> str:
        compact = "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())
        compact = re.sub(r"\n{3,}", "\n\n", compact)
        return compact[: max(0, limit - 3)] + "..." if len(compact) > limit else compact

    def _goal_score(self, text: str) -> int:
        match = re.search(r"(?:score|rating)\s*[:=-]?\s*(\d{1,3})", str(text or ""), flags=re.IGNORECASE)
        if not match:
            match = re.search(r"\b(\d{1,3})\s*/\s*100\b", str(text or ""))
        if not match:
            return 0
        return max(0, min(100, int(match.group(1))))

    def _goal_mode_limits(self, mode: str) -> dict[str, Any]:
        profiles = {
            "cheap": {"max_agents": 2, "max_rounds": 1, "reviewers": 1, "control_roles": False},
            "balanced": {"max_agents": min(self.goal_max_agents, 4), "max_rounds": min(self.goal_default_max_rounds, 2), "reviewers": 1, "control_roles": True},
            "full": {"max_agents": self.goal_max_agents, "max_rounds": self.goal_default_max_rounds, "reviewers": self.goal_max_reviewers, "control_roles": True},
        }
        if mode not in profiles:
            raise ValueError("goal mode must be cheap, balanced, or full")
        return profiles[mode]

    def _goal_mode_agents(self, agents: list[str], mode: str, goal: str) -> list[str]:
        if mode == "full":
            return agents[: self.goal_max_agents]
        tier_rank = {"local": 0, "cheap": 1, "medium": 2, "premium": 3}
        risk_rank = {"low": 0, "medium": 1, "high": 2}
        order = {agent: index for index, agent in enumerate(agents)}
        if mode == "cheap":
            return sorted(
                agents,
                key=lambda agent: (
                    tier_rank.get(self._agent_profile(agent)["cost_tier"], 2),
                    risk_rank.get(self._agent_profile(agent)["usage_risk"], 1),
                    -self._profile_score(agent, "reviewer", goal),
                    order[agent],
                ),
            )[: self._goal_mode_limits(mode)["max_agents"]]
        owner_candidate = max(
            agents,
            key=lambda agent: (self._profile_score(agent, "owner", goal), -order[agent]),
        )
        selected = [owner_candidate]
        remaining = [agent for agent in agents if agent != owner_candidate]
        selected.extend(sorted(
            remaining,
            key=lambda agent: (
                tier_rank.get(self._agent_profile(agent)["cost_tier"], 2),
                risk_rank.get(self._agent_profile(agent)["usage_risk"], 1),
                -max(
                    self._profile_score(agent, "token_police", goal),
                    self._profile_score(agent, "reviewer", goal),
                    self._profile_score(agent, "summary", goal),
                ),
                order[agent],
            ),
        ))
        return selected[: self._goal_mode_limits(mode)["max_agents"]]

    def _goal_execution_profile(self, mode: str, agents: list[str], max_rounds: int, reviewers: list[str] | None = None,
                                token_police: str | None = None, guardrail_agent: str | None = None) -> dict[str, Any]:
        reviewer_count = len(reviewers or [])
        control_count = len([agent for agent in (token_police, guardrail_agent) if agent])
        estimated_calls = (len(agents) * 2) + (max_rounds * (1 + reviewer_count + control_count)) + 1
        risks = [self._agent_profile(agent)["usage_risk"] for agent in agents]
        if mode == "full" or "high" in risks:
            risk_level = "high"
        elif mode == "balanced" or "medium" in risks:
            risk_level = "medium"
        else:
            risk_level = "low"
        return {
            "mode": mode,
            "agents": agents,
            "max_rounds": max_rounds,
            "estimated_call_count": estimated_calls,
            "risk_level": risk_level,
        }

    def _format_goal_execution_profile(self, profile: dict[str, Any]) -> str:
        return (
            "Goal execution profile:\n"
            f"Mode: {profile['mode']}\n"
            f"Agents: {', '.join(profile['agents']) or '(none)'}\n"
            f"Max rounds: {profile['max_rounds']}\n"
            f"Estimated call count: {profile['estimated_call_count']}\n"
            f"Risk level: {profile['risk_level']}"
        )

    def _choose_control_roles(self, agents: list[str], owner: str, reviewers: list[str], goal: str) -> tuple[str | None, str | None]:
        others = [agent for agent in agents if agent != owner]
        if not others:
            return None, None

        def role_score(agent_id: str, terms: set[str]) -> int:
            adapter_config = self.config.get("adapters", {}).get(agent_id, {})
            haystack = " ".join([
                str(adapter_config.get("role", "")),
                " ".join(str(item) for item in adapter_config.get("capabilities", []) or []),
                self._profile_text(agent_id),
            ]).lower()
            return sum(1 for term in terms if term in haystack)

        order = {agent: index for index, agent in enumerate(agents)}
        token_terms = {"concise", "local", "low_cost", "low-cost", "reviewer", "coordinator"}
        guard_terms = {"reviewer", "coordinator", "security", "architecture", "risk", "governance"}
        token_police = max(
            others,
            key=lambda agent: (
                self._profile_score(agent, "token_police", goal),
                role_score(agent, token_terms),
                -order[agent],
            ),
        )
        guard_candidates = others if len(agents) < 3 else [agent for agent in others if agent != token_police] or others
        guardrail = max(
            guard_candidates,
            key=lambda agent: (
                self._profile_score(agent, "guardrail", goal),
                role_score(agent, guard_terms),
                agent in reviewers,
                -order[agent],
            ),
        )
        return token_police, guardrail

    def _goal_visible(self, room_name: str, body: str, *, goal_run_id: str, actor: str = "synkraken-goal",
                      conversation_id: str | None = None) -> FabricMessage:
        return self._save_visible_message(
            actor,
            f"room:{room_name}",
            body,
            conversation_id=conversation_id or goal_run_id,
            metadata={"goal_mode": True, "goal_run_id": goal_run_id},
        )

    def _send_goal_prompt(
        self,
        agent_id: str,
        phase: str,
        prompt: str,
        *,
        goal_run_id: str,
        room_name: str,
        conversation_id: str,
        memory_context: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        transcript_target = f"room:{room_name}"
        marker = self._goal_visible(
            room_name,
            f"Goal {phase}: {agent_id}",
            goal_run_id=goal_run_id,
            conversation_id=conversation_id,
        )
        runtime_name = self.adapters[agent_id].health().get("runtime_name", agent_id)
        delivery_message = FabricMessage(
            source="synkraken-goal",
            target=agent_id,
            body=self._with_memory_context(prompt, memory_context),
            conversation_id=conversation_id,
            message_id=marker.message_id,
            reply_to=marker.message_id,
            metadata={
                "goal_mode": True,
                "goal_run_id": goal_run_id,
                "phase": phase,
                "task_id": task_id,
                "room_memory_injected": bool(memory_context),
            },
        ).normalized()
        self._publish_delivery_queued(delivery_message, agent_id, runtime_name, agent_id, transcript_target)
        self._publish_delivery_sent(delivery_message, agent_id, runtime_name, agent_id, transcript_target, 1)
        self._publish_typing_started(delivery_message, agent_id, runtime_name, agent_id, transcript_target)
        self._set_agent_working(agent_id, delivery_message, reply_context=transcript_target, event_type="message_received")
        started = time.monotonic()
        try:
            reply = self.adapters[agent_id].send(delivery_message)
            status = self._reply_status(reply)
        except Exception as exc:  # noqa: BLE001
            reply, status = self._adapter_exception_reply(agent_id, exc)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if reply.duration_ms is None:
            reply.duration_ms = elapsed_ms
        self._publish_typing_stopped(delivery_message, agent_id, runtime_name, agent_id, transcript_target, reply, status)
        delivery = self._record_delivery(
            delivery_message,
            reply,
            attempt=1,
            original_target=agent_id,
            delivery_target=agent_id,
            reply_context=transcript_target,
            status=status,
        )
        self._set_agent_result(agent_id, delivery_message, reply, status, reply_context=transcript_target)
        if reply.ok:
            reply_message = self._goal_visible(
                room_name,
                reply.body or "",
                goal_run_id=goal_run_id,
                actor=agent_id,
                conversation_id=conversation_id,
            )
            delivery["reply_message_id"] = reply_message.message_id
        else:
            self._record_dead_letter(delivery_message, agent_id, reply, original_target=agent_id, reply_context=transcript_target, status=status)
            failure = self._goal_visible(
                room_name,
                f"{agent_id} {status}: {reply.error or 'delivery_failed'}",
                goal_run_id=goal_run_id,
                conversation_id=conversation_id,
            )
            delivery["reply_message_id"] = failure.message_id
        return {
            "agent_id": agent_id,
            "phase": phase,
            "ok": reply.ok,
            "status": status,
            "body": reply.body or "",
            "error": reply.error,
            "elapsed_ms": elapsed_ms,
            "delivery": delivery,
        }

    def goal_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = str(payload.get("source", "operator")).strip() or "operator"
        room_name = str(payload.get("room_name", "")).strip()
        goal = str(payload.get("goal") or payload.get("source_goal") or "").strip()
        threshold = int(payload.get("threshold", self.goal_default_threshold))
        mode = str(payload.get("mode") or "balanced").strip().lower()
        mode_limits = self._goal_mode_limits(mode)
        requested_rounds = int(payload.get("max_rounds", payload.get("rounds", mode_limits["max_rounds"])))
        max_rounds = min(requested_rounds, mode_limits["max_rounds"])
        if not room_name:
            raise ValueError("Goal mode needs a room. Create or select a room first.")
        if not self.storage.room_exists(room_name):
            raise ValueError(f"room not found: {room_name}")
        if not goal:
            raise ValueError("goal required")
        if threshold < 1 or threshold > 100:
            raise ValueError("threshold must be between 1 and 100")
        if requested_rounds < 1:
            raise ValueError("rounds must be at least 1")
        agents = self._goal_mode_agents(self._room_agents(room_name), mode, goal)
        if not agents:
            raise ValueError(f"room has no available agents: {room_name}")

        now = utc_now_iso()
        goal_run_id = new_id()
        conversation_id = goal_run_id
        memory_context, memory_items = self._prompt_memory_context(room_name)
        execution_profile = self._goal_execution_profile(mode, agents, max_rounds)
        prompt_message = self._goal_visible(
            room_name,
            f"{self._format_goal_execution_profile(execution_profile)}\n\nGoal started: {goal}",
            goal_run_id=goal_run_id,
            actor=source,
            conversation_id=conversation_id,
        )
        task = self.storage.create_task(
            task_id=new_id(),
            title=self._task_title(goal),
            description=f"Goal Mode v0.1\n\n{goal}",
            status="open",
            priority="normal",
            room_name=room_name,
            assigned_agent_id=None,
            source_message_id=prompt_message.message_id,
            actor=source,
            created_at=now,
        )
        task_id = task["task_id"]
        run = self.storage.create_goal_run(
            goal_run_id=goal_run_id,
            room_name=room_name,
            source_goal=goal,
            status="planning",
            threshold=threshold,
            max_rounds=max_rounds,
            current_round=0,
            participants=agents,
            token_budget_chars=self.goal_max_context_chars,
            linked_task_id=task_id,
            started_at=now,
            created_by=source,
        )
        self.storage.record_goal_event(
            goal_run_id,
            "goal_started",
            actor=source,
            details={"goal": goal, "participants": agents, "execution_profile": execution_profile},
            created_at=now,
        )
        self.storage.record_task_event(task_id, "synkraken-goal", "goal_started", None, goal, now)
        self.event_bus.publish("goal.started", {"goal_run_id": goal_run_id, "room_name": room_name, "task_id": task_id})

        criteria_prompt = (
            "Goal Mode - Criteria\n\n"
            f"Goal:\n{goal}\n\n"
            "Define success criteria for this goal. Include what done means, what must be true, "
            "what should not happen, and key risks. Keep it concise and generic to this room context."
        )
        criteria_results = [
            self._send_goal_prompt(agent, "criteria", criteria_prompt, goal_run_id=goal_run_id, room_name=room_name,
                                   conversation_id=conversation_id, memory_context=memory_context, task_id=task_id)
            for agent in agents
        ]
        criteria_text = "\n".join(f"- {item['agent_id']}: {self._compact_text(item['body'], 350)}" for item in criteria_results if item["ok"])
        if not criteria_text:
            criteria_text = "- The goal must be completed safely, visibly, and within the configured round limit."
        checklist = self._compact_text(criteria_text, 1200)
        self.storage.update_goal_run(goal_run_id, {"success_criteria": checklist})
        self.storage.record_goal_event(goal_run_id, "criteria_defined", actor="synkraken-goal", details=checklist)
        self._goal_visible(room_name, f"Goal success criteria:\n{checklist}", goal_run_id=goal_run_id, conversation_id=conversation_id)

        nomination_prompt = (
            "Goal Mode - Assignment\n\n"
            f"Goal:\n{goal}\n\nSuccess criteria:\n{checklist}\n\n"
            f"Available agents: {', '.join(agents)}\n\n"
            "Nominate exactly one owner and one or more reviewers. Use:\n"
            "Owner: <agent_id>\nReviewer: <agent_id>\nSupport: <agent_id or none>"
        )
        nomination_results = [
            self._send_goal_prompt(agent, "assignment", nomination_prompt, goal_run_id=goal_run_id, room_name=room_name,
                                   conversation_id=conversation_id, memory_context=memory_context, task_id=task_id)
            for agent in agents
        ]
        owner, reviewers, owner_votes, reviewer_votes = self._choose_team_owner(agents, nomination_results, goal)
        reviewers = [agent for agent in reviewers if agent != owner][: mode_limits["reviewers"]]
        if not reviewers:
            reviewers = [agent for agent in agents if agent != owner][:1]
        token_police, guardrail_agent = self._choose_control_roles(agents, owner, reviewers, goal) if mode_limits["control_roles"] else (None, None)
        execution_profile = self._goal_execution_profile(mode, agents, max_rounds, reviewers, token_police, guardrail_agent)
        self.storage.update_goal_run(goal_run_id, {
            "status": "running",
            "owner_agent": owner,
            "reviewers": reviewers,
            "token_police_agent": token_police,
            "guardrail_agent": guardrail_agent,
        })
        self.storage.update_task(task_id, {"status": "in_progress", "assigned_agent_id": owner}, "synkraken-goal", utc_now_iso())
        self.storage.record_goal_event(goal_run_id, "owner_selected", actor="synkraken-goal", details={"owner": owner, "owner_votes": owner_votes, "reviewer_votes": reviewer_votes})
        self.storage.record_goal_event(
            goal_run_id,
            "control_roles_selected",
            actor="synkraken-goal",
            details={"token_police": token_police, "guardrail_agent": guardrail_agent, "execution_profile": execution_profile},
        )
        self._goal_visible(
            room_name,
            f"{self._format_goal_execution_profile(execution_profile)}\n\nGoal owner selected: {owner}\nReviewers: {', '.join(reviewers) or '(none)'}\nToken Police: {token_police or '(none)'}\nGuardrail Agent: {guardrail_agent or '(none)'}",
            goal_run_id=goal_run_id,
            conversation_id=conversation_id,
        )

        latest_output = ""
        reviewer_feedback = ""
        token_notes = ""
        guardrail_notes = ""
        latest_score = 0
        guardrail_status = "clear"
        status = "running"
        attempted_fallback = False
        current_owner = owner
        for round_number in range(1, max_rounds + 1):
            self.storage.update_goal_run(goal_run_id, {"current_round": round_number, "status": "running"})
            self.storage.record_goal_event(goal_run_id, "round_started", actor="synkraken-goal", details={"round": round_number})
            self.storage.record_task_event(task_id, "synkraken-goal", "goal_round", str(round_number - 1), str(round_number))
            revision_brief = self._compact_text(
                "\n\n".join(part for part in [
                    f"Previous owner output summary:\n{self._compact_text(latest_output, 600)}" if latest_output else "",
                    f"Reviewer gaps:\n{self._compact_text(reviewer_feedback, 600)}" if reviewer_feedback else "",
                    f"Previous score: {latest_score}" if latest_score else "",
                    f"Token police notes:\n{self._compact_text(token_notes, 300)}" if token_notes else "",
                    f"Guardrail notes:\n{self._compact_text(guardrail_notes, 300)}" if guardrail_notes else "",
                ] if part),
                self.goal_max_revision_chars,
            )
            estimated_context = len(goal) + len(checklist) + len(revision_brief) + len(memory_context)
            self.storage.update_goal_run(goal_run_id, {"estimated_context_chars": estimated_context})
            self._goal_visible(
                room_name,
                f"Goal context budget:\nround {round_number}/{max_rounds}\nestimated context chars: {estimated_context}\nlimit: {self.goal_max_context_chars}",
                goal_run_id=goal_run_id,
                conversation_id=conversation_id,
            )
            owner_prompt = (
                "Goal Mode - Execute Round\n\n"
                f"Goal:\n{goal}\n\nSuccess criteria:\n{checklist}\n\n"
                f"Round: {round_number}/{max_rounds}\n\n"
                f"Revision brief:\n{revision_brief or '(first round)'}\n\n"
                "Produce the best current work toward the goal. Do not message other agents. "
                "Keep output concise enough for review."
            )
            owner_result = self._send_goal_prompt(current_owner, f"round {round_number} execute", owner_prompt,
                                                  goal_run_id=goal_run_id, room_name=room_name,
                                                  conversation_id=conversation_id, memory_context=memory_context,
                                                  task_id=task_id)
            if not owner_result["ok"] and not attempted_fallback:
                fallback = next((agent for agent in agents if agent != current_owner), None)
                attempted_fallback = True
                if fallback:
                    self.storage.record_goal_event(goal_run_id, "revision_requested", actor="synkraken-goal", details=f"owner fallback {current_owner} -> {fallback}")
                    current_owner = fallback
                    self.storage.update_goal_run(goal_run_id, {"owner_agent": current_owner})
                    self.storage.update_task(task_id, {"assigned_agent_id": current_owner}, "synkraken-goal", utc_now_iso())
                    owner_result = self._send_goal_prompt(current_owner, f"round {round_number} execute", owner_prompt,
                                                          goal_run_id=goal_run_id, room_name=room_name,
                                                          conversation_id=conversation_id, memory_context=memory_context,
                                                          task_id=task_id)
            if not owner_result["ok"]:
                status = "failed"
                self.storage.record_goal_event(goal_run_id, "goal_failed", actor=current_owner, details=owner_result.get("error"))
                break
            latest_output = owner_result["body"]
            self.storage.record_goal_event(goal_run_id, "owner_work_completed", actor=current_owner, details={"round": round_number, "chars": len(latest_output)})

            if token_police:
                token_prompt = (
                    "Goal Mode - Token Review\n\n"
                    f"Goal:\n{goal}\nRound: {round_number}/{max_rounds}\n"
                    f"Estimated context chars: {estimated_context}\nLimit: {self.goal_max_context_chars}\n\n"
                    f"Owner output summary:\n{self._compact_text(latest_output, 900)}\n\n"
                    "Review context size, repeated prompt bloat, summary compaction, and whether another round is worth the cost. "
                    "Return concise notes and include WARNING if budget risk is high."
                )
                token_result = self._send_goal_prompt(token_police, f"round {round_number} token", token_prompt,
                                                      goal_run_id=goal_run_id, room_name=room_name,
                                                      conversation_id=conversation_id, memory_context="", task_id=task_id)
                token_notes = token_result["body"] if token_result["ok"] else f"Token review failed: {token_result.get('error') or token_result.get('status')}"
                self.storage.record_goal_event(goal_run_id, "token_budget_checked", actor=token_police, details=token_notes)
                if estimated_context > self.goal_max_context_chars or "warning" in token_notes.lower():
                    self.storage.record_goal_event(goal_run_id, "token_warning", actor=token_police, details=token_notes)

            if guardrail_agent:
                guard_prompt = (
                    "Goal Mode - Guardrail Review\n\n"
                    f"Goal:\n{goal}\n\nSuccess criteria:\n{checklist}\n\n"
                    f"Owner output summary:\n{self._compact_text(latest_output, 900)}\n\n"
                    "Check scope, security, architecture, project boundaries, goal drift, and overengineering. "
                    "Return CLEAR or BLOCK with a concise reason."
                )
                guard_result = self._send_goal_prompt(guardrail_agent, f"round {round_number} guardrail", guard_prompt,
                                                      goal_run_id=goal_run_id, room_name=room_name,
                                                      conversation_id=conversation_id, memory_context="", task_id=task_id)
                guardrail_notes = guard_result["body"] if guard_result["ok"] else f"Guardrail review failed: {guard_result.get('error') or guard_result.get('status')}"
                guard_l = guardrail_notes.lower()
                blocked = "block" in guard_l and "not block" not in guard_l and "clear" not in guard_l
                guardrail_status = "blocked" if blocked else "clear"
                self.storage.update_goal_run(goal_run_id, {"guardrail_status": guardrail_status})
                self.storage.record_goal_event(goal_run_id, "guardrail_checked", actor=guardrail_agent, details=guardrail_notes)
                if blocked:
                    status = "blocked"
                    self.storage.record_goal_event(goal_run_id, "guardrail_blocked", actor=guardrail_agent, details=guardrail_notes)
                    self._goal_visible(room_name, f"Goal blocked by guardrail:\n{guardrail_notes}", goal_run_id=goal_run_id, conversation_id=conversation_id)
                    break
                if "warning" in guard_l or "risk" in guard_l:
                    self.storage.record_goal_event(goal_run_id, "guardrail_warning", actor=guardrail_agent, details=guardrail_notes)

            self.storage.update_goal_run(goal_run_id, {"status": "reviewing"})
            self.storage.record_goal_event(goal_run_id, "review_started", actor="synkraken-goal", details={"round": round_number, "reviewers": reviewers})
            review_results = []
            for reviewer in reviewers:
                review_prompt = (
                    "Goal Mode - Quality Review\n\n"
                    f"Goal:\n{goal}\n\nSuccess criteria:\n{checklist}\n\n"
                    f"Owner output:\n{self._compact_text(latest_output, 1200)}\n\n"
                    "Score the output against criteria. Include:\n"
                    "Score: <0-100>\nPass: yes/no\nMissing items:\nRisks:\nSuggested revision:"
                )
                review = self._send_goal_prompt(reviewer, f"round {round_number} review", review_prompt,
                                                goal_run_id=goal_run_id, room_name=room_name,
                                                conversation_id=conversation_id, memory_context="", task_id=task_id)
                if review["ok"]:
                    review["score"] = self._goal_score(review["body"])
                    review_results.append(review)
            if review_results:
                latest_score = int(sum(item["score"] for item in review_results) / len(review_results))
                reviewer_feedback = self._compact_text("\n\n".join(f"{item['agent_id']} ({item['score']}): {item['body']}" for item in review_results), 1200)
            else:
                latest_score = 0
                reviewer_feedback = "No reviewer completed successfully."
            self.storage.update_goal_run(goal_run_id, {"latest_score": latest_score, "status": "running"})
            self.storage.record_goal_event(goal_run_id, "review_completed", actor="synkraken-goal", details=reviewer_feedback)
            self.storage.record_goal_event(goal_run_id, "score_recorded", actor="synkraken-goal", details={"round": round_number, "score": latest_score})
            self.storage.record_task_event(task_id, "synkraken-goal", "goal_score", None, str(latest_score))
            self._goal_visible(room_name, f"Goal review score: {latest_score}/{threshold}\n{self._compact_text(reviewer_feedback, 900)}", goal_run_id=goal_run_id, conversation_id=conversation_id)
            if latest_score >= threshold and guardrail_status != "blocked":
                status = "achieved"
                self.storage.record_goal_event(goal_run_id, "threshold_met", actor="synkraken-goal", details={"score": latest_score, "threshold": threshold})
                break
            if round_number < max_rounds:
                self.storage.record_goal_event(goal_run_id, "revision_requested", actor="synkraken-goal", details={"round": round_number, "score": latest_score})
            else:
                status = "partially_achieved"
                self.storage.record_goal_event(goal_run_id, "max_rounds_reached", actor="synkraken-goal", details={"score": latest_score, "threshold": threshold})

        completed_at = utc_now_iso()
        if status == "running":
            status = "partially_achieved"
        if status == "failed":
            task_status = "blocked"
            event_type = "goal_failed"
            self.storage.record_goal_event(goal_run_id, "goal_failed", actor="synkraken-goal", details="goal ended failed")
        elif status == "blocked":
            task_status = "blocked"
            event_type = "goal_blocked"
            self.storage.record_goal_event(goal_run_id, "goal_blocked", actor="synkraken-goal", details=guardrail_notes or "goal blocked")
        elif status == "achieved":
            task_status = "done"
            event_type = "goal_completed"
        else:
            task_status = "done"
            event_type = "goal_completed"
        final_report = (
            "Goal Mode final report\n"
            f"Mode: {mode}\n"
            f"Goal: {goal}\n"
            f"Status: {status}\n"
            f"Score: {latest_score}/{threshold}\n"
            f"Rounds: {self.storage.get_goal_run(goal_run_id)['current_round']}/{max_rounds}\n"
            f"Owner: {current_owner}\n"
            f"Reviewers: {', '.join(reviewers) or '(none)'}\n"
            f"Token Police: {token_police or '(none)'}\n"
            f"Guardrail Agent: {guardrail_agent or '(none)'}\n"
            f"Estimated context chars: {self.storage.get_goal_run(goal_run_id)['estimated_context_chars']}/{self.goal_max_context_chars}\n"
            f"Guardrail status: {guardrail_status}\n\n"
            f"Token notes:\n{self._compact_text(token_notes, 700) or '(none)'}\n\n"
            f"Guardrail notes:\n{self._compact_text(guardrail_notes, 700) or '(none)'}\n\n"
            f"Remaining gaps:\n{self._compact_text(reviewer_feedback, 1000) or '(none)'}"
        )
        self.storage.update_goal_run(goal_run_id, {
            "status": status,
            "latest_score": latest_score,
            "final_report": final_report,
            "completed_at": completed_at,
            "guardrail_status": guardrail_status,
        })
        self.storage.update_task(task_id, {"status": task_status}, "synkraken-goal", completed_at)
        self.storage.record_task_event(task_id, "synkraken-goal", event_type, None, status, completed_at)
        self._goal_visible(room_name, final_report, goal_run_id=goal_run_id, conversation_id=conversation_id)
        self.event_bus.publish("goal.completed", {"goal_run_id": goal_run_id, "room_name": room_name, "status": status, "score": latest_score})
        run = self.storage.get_goal_run(goal_run_id)
        assert run is not None
        return {
            "goal_run": run,
            "execution_profile": execution_profile,
            "events": self.storage.list_goal_events(goal_run_id) or [],
            "messages": self.storage.get_room_messages(room_name, limit=200),
            "memory_context": memory_context,
            "memory_items": memory_items,
            "task": self.storage.get_task(task_id),
        }

    def cancel_goal_run(self, goal_run_id: str, actor: str = "operator") -> dict[str, Any]:
        run = self.storage.get_goal_run(goal_run_id)
        if not run:
            raise ValueError(f"goal run not found: {goal_run_id}")
        if run["status"] in {"achieved", "partially_achieved", "blocked", "failed", "cancelled"}:
            raise ValueError(f"goal run is already terminal: {goal_run_id}")
        now = utc_now_iso()
        updated = self.storage.update_goal_run(goal_run_id, {"status": "cancelled", "completed_at": now})
        self.storage.record_goal_event(goal_run_id, "goal_cancelled", actor=actor, details="cancelled by request", created_at=now)
        if run.get("linked_task_id"):
            self.storage.update_task(run["linked_task_id"], {"status": "blocked"}, actor, now)
            self.storage.record_task_event(run["linked_task_id"], actor, "goal_cancelled", None, "cancelled", now)
        self._goal_visible(run["room_name"], f"Goal cancelled: {goal_run_id}", goal_run_id=goal_run_id, actor=actor, conversation_id=goal_run_id)
        return {"goal_run": updated, "events": self.storage.list_goal_events(goal_run_id) or []}

    def discuss(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = str(payload.get('source', 'operator')).strip() or 'operator'
        agents = [str(agent).strip() for agent in payload.get('agents', []) if str(agent).strip()]
        topic = str(payload.get('topic', '')).strip()
        max_turns = int(payload.get('max_turns', 4))
        room_name = payload.get('room_name')
        room_name = str(room_name).strip() if room_name is not None else ''
        if len(agents) < 2:
            raise ValueError('discussion requires at least two agents')
        if not topic:
            raise ValueError('discussion topic required')
        if max_turns < 1 or max_turns > 20:
            raise ValueError('max_turns must be between 1 and 20')
        unknown = [agent for agent in agents if agent not in self.adapters]
        if unknown:
            raise ValueError(f"unknown agent: {', '.join(unknown)}")
        transcript_target = 'discussion'
        reply_context = 'discussion'
        memory_context = ''
        if room_name:
            if not self.storage.room_exists(room_name):
                raise ValueError(f'room not found: {room_name}')
            transcript_target = f'room:{room_name}'
            reply_context = transcript_target
            memory_context, memory_items = self._prompt_memory_context(room_name)
        else:
            memory_items = []

        topic_message = FabricMessage(
            source=source,
            target=transcript_target,
            body=f'Discussion topic: {topic}',
            metadata={'discussion': True, 'topic': topic, 'agents': agents, 'max_turns': max_turns},
        ).normalized()
        self.storage.save_message(topic_message)
        self.event_bus.publish('message.accepted', {
            'message_id': topic_message.message_id,
            'conversation_id': topic_message.conversation_id,
            'source': topic_message.source,
            'target': topic_message.target,
            'priority': topic_message.priority,
        })
        conversation_id = topic_message.conversation_id

        result: dict[str, Any] = {
            'discussion_id': conversation_id,
            'conversation_id': conversation_id,
            'room_name': room_name or None,
            'topic': topic,
            'agents': agents,
            'max_turns': max_turns,
            'turns': [],
            'deliveries': [],
            'dead_letters': [],
            'status': 'completed',
        }
        previous_agent = None
        previous_reply = ''
        for turn in range(1, max_turns + 1):
            agent_id = agents[(turn - 1) % len(agents)]
            final_turn = turn == max_turns
            marker = f'{agent_id} final recommendation' if final_turn else f'{agent_id} turn {turn}'
            progress = self._save_visible_message(
                'synkraken-discussion',
                transcript_target,
                marker,
                conversation_id=conversation_id,
                metadata={'discussion': True, 'turn': turn, 'agent_id': agent_id, 'final': final_turn},
            )
            runtime_name = self.adapters[agent_id].health().get('runtime_name', agent_id)
            self.event_bus.publish('discussion.turn', {
                'discussion_id': conversation_id,
                'conversation_id': conversation_id,
                'room_name': room_name or None,
                'adapter_id': agent_id,
                'runtime_name': runtime_name,
                'turn': turn,
                'max_turns': max_turns,
                'final': final_turn,
                'label': marker,
            })
            if final_turn:
                prompt = (
                    f'Original topic:\n{topic}\n\n'
                    f'Previous reply from {previous_agent or "the discussion"}:\n{previous_reply or "(none yet)"}\n\n'
                    'Provide a concise final recommendation for the human operator. '
                    'Do not continue the discussion or message another agent.'
                )
            elif turn == 1:
                prompt = (
                    f'Original topic:\n{topic}\n\n'
                    'Start the discussion. Give your position and key reasoning. '
                    'Do not message another agent; SynKraken will coordinate turns.'
                )
            else:
                prompt = (
                    f'Original topic:\n{topic}\n\n'
                    f'{previous_agent} said:\n{previous_reply}\n\n'
                    f'Respond to {previous_agent}. Advance the discussion for the human operator. '
                    'Do not message another agent; SynKraken will coordinate turns.'
                )
            delivery_message = FabricMessage(
                source='synkraken-discussion',
                target=agent_id,
                body=self._with_memory_context(prompt, memory_context),
                conversation_id=conversation_id,
                message_id=progress.message_id,
                reply_to=progress.message_id,
                metadata={'discussion': True, 'turn': turn, 'final': final_turn, 'room_memory_injected': bool(memory_context)},
            ).normalized()
            self._publish_delivery_queued(delivery_message, agent_id, runtime_name, agent_id, reply_context)
            self._publish_delivery_sent(delivery_message, agent_id, runtime_name, agent_id, reply_context, 1)
            self._publish_typing_started(delivery_message, agent_id, runtime_name, agent_id, reply_context)
            self._set_agent_working(
                agent_id,
                delivery_message,
                reply_context=reply_context,
                event_type="discussion_started",
            )
            try:
                reply = self.adapters[agent_id].send(delivery_message)
                status = self._reply_status(reply)
            except Exception as exc:  # noqa: BLE001
                reply, status = self._adapter_exception_reply(agent_id, exc)
            self._publish_typing_stopped(delivery_message, agent_id, runtime_name, agent_id, reply_context, reply, status)
            delivery = self._record_delivery(
                delivery_message,
                reply,
                attempt=1,
                original_target=agent_id,
                delivery_target=agent_id,
                reply_context=reply_context,
                status=status,
            )
            result['deliveries'].append(delivery)
            self._set_agent_result(agent_id, delivery_message, reply, status, reply_context=reply_context)
            if not reply.ok:
                dead_letter = self._record_dead_letter(
                    delivery_message,
                    agent_id,
                    reply,
                    original_target=agent_id,
                    reply_context=reply_context,
                    status=status,
                )
                result['dead_letters'].append(dead_letter)
                self._save_visible_message(
                    'synkraken-discussion',
                    transcript_target,
                    f'{agent_id} {status}: {reply.error or "delivery_failed"}',
                    conversation_id=conversation_id,
                    reply_to=progress.message_id,
                    metadata={'discussion': True, 'turn': turn, 'agent_id': agent_id, 'status': status},
                )
                result['status'] = status
                break
            reply_message = self._save_visible_message(
                agent_id,
                transcript_target,
                reply.body or '',
                conversation_id=conversation_id,
                reply_to=progress.message_id,
                metadata={'discussion': True, 'turn': turn, 'final': final_turn},
            )
            result['turns'].append({
                'turn': turn,
                'agent_id': agent_id,
                'message_id': reply_message.message_id,
                'final': final_turn,
                'status': status,
                'body_preview': (reply.body or '')[:160],
            })
            previous_agent = agent_id
            previous_reply = reply.body or ''
        self.event_bus.publish('discussion.completed', {
            'discussion_id': conversation_id,
            'conversation_id': conversation_id,
            'room_name': room_name or None,
            'status': result['status'],
            'turn_count': len(result['turns']),
            'max_turns': max_turns,
        })
        for agent_id in agents:
            self.storage.record_agent_event(
                agent_id,
                "discussion_completed",
                conversation_id,
                result["status"],
            )
        result['messages'] = self.storage.get_conversation(conversation_id)['messages']
        result['memory_context'] = memory_context
        result['memory_items'] = memory_items
        return result

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        message_id = str(payload.get("message_id") or "").strip() or new_id()
        message = FabricMessage(
            source=str(payload["source"]),
            target=str(payload["target"]),
            body=str(payload["body"]),
            conversation_id=payload.get("conversation_id"),
            message_id=message_id,
            subject=payload.get("subject"),
            priority=payload.get("priority", "normal"),
            reply_to=payload.get("reply_to"),
            hop_count=int(payload.get("hop_count", 0)),
            metadata=dict(payload.get("metadata", {})),
        ).normalized()
        if message.hop_count > self.max_hops:
            raise ValueError(f"Max hop count exceeded: {message.hop_count} > {self.max_hops}")
        self.storage.save_message(message)
        self.event_bus.publish('message.accepted', {
            'message_id': message.message_id,
            'conversation_id': message.conversation_id,
            'source': message.source,
            'target': message.target,
            'priority': message.priority,
        })
        original_target = message.target
        room_context = message.metadata.get("room_context")
        if room_context is not None:
            room_context = str(room_context)
            if not room_context.startswith("room:"):
                raise ValueError(f"Invalid room context: {room_context}")
            room_name = room_context[len("room:"):]
            if not self.storage.room_exists(room_name):
                raise ValueError(f"Unknown room context: {room_context}")
            if original_target != room_context:
                transcript_msg = FabricMessage(
                    source=message.source,
                    target=room_context,
                    body=message.body,
                    conversation_id=message.conversation_id,
                    reply_to=message.reply_to,
                    hop_count=message.hop_count,
                    metadata={"delivery_target": original_target},
                ).normalized()
                self.storage.save_message(transcript_msg)
                self.event_bus.publish('message.accepted', {
                    'message_id': transcript_msg.message_id,
                    'conversation_id': transcript_msg.conversation_id,
                    'source': transcript_msg.source,
                    'target': transcript_msg.target,
                    'priority': transcript_msg.priority,
                })
        delivery_targets = resolve_targets(
            message.source, original_target, self.adapters.keys(), self.storage
        )
        reply_context = room_context or (original_target if original_target.startswith("room:") else None)
        memory_room = self._presence_room(reply_context)
        memory_context, memory_items = self._prompt_memory_context(memory_room)
        transcript_target = reply_context or ("broadcast" if original_target == "broadcast" else None)
        deliveries: list[dict[str, Any]] = []
        dead_letters: list[dict[str, Any]] = []
        for delivery_target in delivery_targets:
            adapter = self.adapters[delivery_target]
            runtime_name = adapter.health().get('runtime_name', delivery_target)
            self._publish_delivery_queued(message, delivery_target, runtime_name, original_target, reply_context)

        def deliver_one(delivery_target: str) -> dict[str, Any]:
            adapter = self.adapters[delivery_target]
            runtime_name = adapter.health().get('runtime_name', delivery_target)
            delivery_message = self._delivery_message_for_target(message, delivery_target)
            if memory_context:
                delivery_message.body = self._with_memory_context(delivery_message.body, memory_context)
                delivery_message.metadata = dict(delivery_message.metadata) | {"room_memory_injected": True}
            target_deliveries: list[dict[str, Any]] = []
            target_dead_letters: list[dict[str, Any]] = []
            last_reply: AdapterReply | None = None
            terminal_status = 'failed'
            for attempt in range(1, self.retry_limit + 2):
                self._publish_delivery_sent(delivery_message, delivery_target, runtime_name, original_target, reply_context, attempt)
                self._publish_typing_started(delivery_message, delivery_target, runtime_name, original_target, reply_context)
                self._set_agent_working(delivery_target, delivery_message, reply_context=reply_context)
                try:
                    reply = adapter.send(delivery_message)
                except Exception as exc:  # noqa: BLE001
                    reply, terminal_status = self._adapter_exception_reply(delivery_target, exc)
                else:
                    terminal_status = self._reply_status(reply)
                self._publish_typing_stopped(
                    delivery_message, delivery_target, runtime_name, original_target,
                    reply_context, reply, terminal_status,
                )
                last_reply = reply
                delivery_payload = self._record_delivery(
                    delivery_message,
                    reply,
                    attempt=attempt,
                    original_target=original_target,
                    delivery_target=delivery_target,
                    reply_context=reply_context,
                    status=terminal_status,
                )
                reply_message = self._persist_reply_message(
                    message, delivery_target, reply, transcript_target,
                )
                self._set_agent_result(delivery_target, delivery_message, reply, terminal_status, reply_context=reply_context)
                if reply_message is not None:
                    delivery_payload['reply_message_id'] = reply_message.message_id
                    delivery_payload['persisted_transcript_target'] = reply_message.target
                else:
                    delivery_payload['reply_message_id'] = None
                    delivery_payload['persisted_transcript_target'] = None
                target_deliveries.append(delivery_payload)
                if reply.ok:
                    break
                if attempt <= self.retry_limit:
                    time.sleep(self.retry_backoff_seconds)
            if last_reply is not None and not last_reply.ok:
                target_dead_letters.append(self._record_dead_letter(
                    delivery_message,
                    delivery_target,
                    last_reply,
                    original_target=original_target,
                    reply_context=reply_context,
                    status=terminal_status,
                ))
            return {
                'delivery_target': delivery_target,
                'deliveries': target_deliveries,
                'dead_letters': target_dead_letters,
            }

        if len(delivery_targets) <= 1:
            target_results = [deliver_one(target) for target in delivery_targets]
        else:
            max_workers = max(1, min(len(delivery_targets), int(self.config.get('routing', {}).get('fanout_workers', 8))))
            target_results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(deliver_one, target): target for target in delivery_targets}
                for future in as_completed(futures):
                    target_results.append(future.result())
            target_results.sort(key=lambda item: delivery_targets.index(item['delivery_target']))
        for target_result in target_results:
            deliveries.extend(target_result['deliveries'])
            dead_letters.extend(target_result['dead_letters'])
        return {
            "message": message.to_dict(),
            "routing": {
                "requested_target": original_target,
                "resolved_targets": delivery_targets,
                "reply_context": reply_context,
                "transcript_target": transcript_target,
                "memory_context": memory_context,
                "memory_items": memory_items,
            },
            "deliveries": deliveries,
            "dead_letters": dead_letters,
        }

    # ── Decisions ─────────────────────────────────────────────────────────

    def propose_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("title required")
        summary = str(payload.get("summary", "")).strip()
        reason = str(payload.get("reason") or payload.get("reasoning") or "").strip()
        options_considered = str(payload.get("options_considered", "")).strip()
        selected_option = str(payload.get("selected_option") or "").strip() or None
        risk = str(payload.get("risk", "")).strip()
        raw_confidence = payload.get("confidence")
        confidence = int(raw_confidence) if raw_confidence not in (None, "") else None
        room_id = str(payload.get("room_id") or payload.get("room_name") or "").strip() or None
        task_id = str(payload.get("task_id") or "").strip() or None
        goal_id = str(payload.get("goal_id") or "").strip() or None
        proposed_by = str(payload.get("proposed_by") or payload.get("actor") or "operator").strip() or "operator"
        linked_runtime_ids = [str(x) for x in (payload.get("linked_runtime_ids") or [])]
        linked_message_ids = [str(x) for x in (payload.get("linked_message_ids") or [])]
        now = utc_now_iso()
        decision_id = str(payload.get("id") or payload.get("decision_id") or "").strip() or new_id()
        decision = self.storage.create_decision(
            decision_id=decision_id,
            room_id=room_id,
            task_id=task_id,
            goal_id=goal_id,
            proposed_by=proposed_by,
            title=title,
            summary=summary,
            reason=reason,
            options_considered=options_considered,
            selected_option=selected_option,
            risk=risk,
            confidence=confidence,
            linked_runtime_ids=linked_runtime_ids,
            linked_message_ids=linked_message_ids,
            created_at=now,
        )
        self.storage.append_decision_event(
            decision_id, "proposed", proposed_by,
            {"title": title, "status": "proposed"}, now,
        )
        self.event_bus.publish("decision.proposed", {"decision_id": decision_id, "id": decision_id, "proposed_by": proposed_by})
        return {"decision": decision, "events": self.storage.list_decision_events(decision_id) or []}

    def approve_decision(self, decision_id: str, actor: str = "operator") -> dict[str, Any]:
        decision = self.storage.get_decision(decision_id)
        if not decision:
            raise ValueError(f"decision not found: {decision_id}")
        if decision["status"] not in {"proposed", "superseded"}:
            raise ValueError(f"decision cannot be approved in status: {decision['status']}")
        updated = self.storage.approve_decision(decision_id, actor)
        self.event_bus.publish("decision.approved", {"decision_id": decision_id, "id": decision_id, "approved_by": actor})
        return {"decision": updated, "events": self.storage.list_decision_events(decision_id) or []}

    def reject_decision(self, decision_id: str, actor: str = "operator", reason: str | None = None) -> dict[str, Any]:
        decision = self.storage.get_decision(decision_id)
        if not decision:
            raise ValueError(f"decision not found: {decision_id}")
        if decision["status"] not in {"proposed", "superseded"}:
            raise ValueError(f"decision cannot be rejected in status: {decision['status']}")
        updated = self.storage.reject_decision(decision_id, actor, reason=reason)
        self.event_bus.publish("decision.rejected", {"decision_id": decision_id, "id": decision_id, "rejected_by": actor})
        return {"decision": updated, "events": self.storage.list_decision_events(decision_id) or []}

    def supersede_decision(self, decision_id: str, new_decision_id: str, actor: str = "operator") -> dict[str, Any]:
        decision = self.storage.get_decision(decision_id)
        if not decision:
            raise ValueError(f"decision not found: {decision_id}")
        now = utc_now_iso()
        old_status = decision["status"]
        self.storage.update_decision(decision_id, {"status": "superseded"})
        self.storage.record_decision_event(
            decision_id, "decision_superseded", actor, old_status, "superseded",
            f"superseded_by={new_decision_id}", now,
        )
        self.event_bus.publish("decision.superseded", {"decision_id": decision_id, "superseded_by": new_decision_id})
        return {"decision": self.storage.get_decision(decision_id), "events": self.storage.list_decision_events(decision_id) or []}

    def get_decision_replay(self, decision_id: str) -> dict[str, Any]:
        decision = self.storage.get_decision(decision_id)
        if not decision:
            raise ValueError(f"decision not found: {decision_id}")
        events = self.storage.list_decision_events(decision_id) or []
        messages = []
        if decision.get("linked_message_ids"):
            for mid in decision["linked_message_ids"]:
                msg = self.storage.get_conversation(mid)
                if msg:
                    messages.extend(msg.get("messages", []))
        return {
            "decision": decision,
            "events": events,
            "messages": messages,
        }

    # ── Handoffs ──────────────────────────────────────────────────────────

    def create_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        from_agent = str(payload.get("from_agent") or payload.get("actor") or "operator").strip() or "operator"
        to_agent = str(payload.get("to_agent", "")).strip()
        if not to_agent:
            raise ValueError("to_agent required")
        summary = str(payload.get("summary", "")).strip()
        if not summary:
            raise ValueError("summary required")
        room_id = str(payload.get("room_id") or payload.get("room_name") or "").strip() or None
        task_id = str(payload.get("task_id") or "").strip() or None
        goal_id = str(payload.get("goal_id") or "").strip() or None
        raw_questions = payload.get("open_questions") or []
        raw_risks = payload.get("risks") or []
        open_questions = raw_questions if isinstance(raw_questions, str) else [str(x) for x in raw_questions]
        risks = raw_risks if isinstance(raw_risks, str) else [str(x) for x in raw_risks]
        recommended_next_step = str(payload.get("recommended_next_step") or payload.get("next") or "").strip()
        raw_confidence = payload.get("confidence")
        confidence = int(raw_confidence) if raw_confidence not in (None, "") else None
        linked_message_ids = [str(x) for x in (payload.get("linked_message_ids") or [])]
        linked_decision_ids = [str(x) for x in (payload.get("linked_decision_ids") or [])]
        now = utc_now_iso()
        handoff_id = str(payload.get("id") or payload.get("handoff_id") or "").strip() or new_id()
        handoff = self.storage.create_handoff(
            handoff_id=handoff_id,
            from_agent=from_agent,
            to_agent=to_agent,
            task_id=task_id,
            room_id=room_id,
            goal_id=goal_id,
            summary=summary,
            open_questions=open_questions,
            risks=risks,
            recommended_next_step=recommended_next_step,
            confidence=confidence,
            linked_message_ids=linked_message_ids,
            linked_decision_ids=linked_decision_ids,
            created_at=now,
        )
        self.storage.append_handoff_event(
            handoff_id, "created", from_agent,
            {"status": "pending", "to_agent": to_agent}, now,
        )
        self.event_bus.publish("handoff.created", {"handoff_id": handoff_id, "from_agent": from_agent, "to_agent": to_agent})
        return {"handoff": handoff, "events": self.storage.list_handoff_events(handoff_id) or []}

    def accept_handoff(self, handoff_id: str, actor: str = "operator") -> dict[str, Any]:
        handoff = self.storage.get_handoff(handoff_id)
        if not handoff:
            raise ValueError(f"handoff not found: {handoff_id}")
        if handoff["status"] != "pending":
            raise ValueError(f"handoff cannot be accepted in status: {handoff['status']}")
        now = utc_now_iso()
        updated = self.storage.accept_handoff(handoff_id, actor, now)
        self.event_bus.publish("handoff.accepted", {"handoff_id": handoff_id, "accepted_by": actor})
        return {"handoff": updated, "events": self.storage.list_handoff_events(handoff_id) or []}

    def reject_handoff(self, handoff_id: str, actor: str = "operator", reason: str | None = None) -> dict[str, Any]:
        handoff = self.storage.get_handoff(handoff_id)
        if not handoff:
            raise ValueError(f"handoff not found: {handoff_id}")
        if handoff["status"] != "pending":
            raise ValueError(f"handoff cannot be rejected in status: {handoff['status']}")
        now = utc_now_iso()
        updated = self.storage.reject_handoff(handoff_id, actor, reason=reason, created_at=now)
        self.event_bus.publish("handoff.rejected", {"handoff_id": handoff_id, "rejected_by": actor})
        return {"handoff": updated, "events": self.storage.list_handoff_events(handoff_id) or []}

    def complete_handoff(self, handoff_id: str, actor: str = "operator") -> dict[str, Any]:
        handoff = self.storage.get_handoff(handoff_id)
        if not handoff:
            raise ValueError(f"handoff not found: {handoff_id}")
        if handoff["status"] != "accepted":
            raise ValueError(f"handoff cannot be completed in status: {handoff['status']}")
        now = utc_now_iso()
        updated = self.storage.complete_handoff(handoff_id, actor, now)
        self.event_bus.publish("handoff.completed", {"handoff_id": handoff_id, "completed_by": actor})
        return {"handoff": updated, "events": self.storage.list_handoff_events(handoff_id) or []}

    # ── Flight Recorder ───────────────────────────────────────────────────

    def get_replay(self, replay_id: str) -> dict[str, Any]:
        goal_run = self.storage.get_goal_run(replay_id)
        if goal_run:
            events = self.storage.list_goal_events(replay_id) or []
            task = self.storage.get_task(goal_run.get("linked_task_id")) if goal_run.get("linked_task_id") else None
            messages = [
                message for message in self.storage.get_room_messages(goal_run["room_name"], limit=200)
                if message.get("conversation_id") == replay_id
            ]
            return {
                "type": "goal_run",
                "run": goal_run,
                "events": events,
                "task": task,
                "messages": messages,
            }
        team_run = self.storage.get_team_run(replay_id)
        if team_run:
            events = self.storage.list_team_events(replay_id) or []
            messages = self.storage.get_room_messages(team_run["room_name"], limit=200)
            return {
                "type": "team_run",
                "run": team_run,
                "events": events,
                "messages": [
                    message for message in messages
                    if message.get("metadata", {}).get("team_run_id") == replay_id
                    or message.get("metadata", {}).get("team_task")
                ],
            }
        decision = self.storage.get_decision(replay_id)
        if decision:
            return self.get_decision_replay(replay_id) | {"type": "decision"}
        raise ValueError(f"replay not found: {replay_id}")

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        return self.get_replay(incident_id)

    def get_latest_incident(self) -> dict[str, Any] | None:
        failed_goals = self.storage.list_goal_runs(limit=100)
        failed_goal = next(
            (g for g in failed_goals if g.get("status") == "failed"),
            None,
        )
        failed_teams = self.storage.list_team_runs(limit=100)
        failed_team = next(
            (t for t in failed_teams if t.get("status") in {"blocked", "failed", "completed_with_final_failure"}),
            None,
        )
        if not failed_goal and not failed_team:
            return None
        if not failed_goal:
            return self.get_replay(failed_team["team_run_id"])
        if not failed_team:
            return self.get_replay(failed_goal["goal_run_id"])
        goal_ts = failed_goal.get("started_at") or ""
        team_ts = failed_team.get("started_at") or ""
        if goal_ts >= team_ts:
            return self.get_replay(failed_goal["goal_run_id"])
        return self.get_replay(failed_team["team_run_id"])
