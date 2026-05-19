from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from queue import Queue
from threading import Lock
from typing import Any
import json
import re
import time

from .adapters import build_adapter
from .models import AdapterReply, FabricMessage, new_id, utc_now_iso
from .router import resolve_targets
from .storage import Storage


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
        routing = config.get("routing", {})
        self.max_hops = int(routing.get("max_hops", 4))
        self.retry_limit = int(routing.get("retry_limit", 1))
        self.retry_backoff_seconds = int(routing.get("retry_backoff_seconds", 1))
        self.started_at = utc_now_iso()

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "timestamp": utc_now_iso(),
            "started_at": self.started_at,
            "adapters": {adapter_id: adapter.health() for adapter_id, adapter in self.adapters.items()},
        }

    def list_agents(self) -> list[dict[str, Any]]:
        return self.storage.list_agents()

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
            body=self._with_room_memory(body, memory_context),
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
        haystack = f"{adapter_config.get('role', '')} {capabilities}".lower()
        terms = {term for term in re.findall(r"[a-z0-9_]+", question.lower()) if len(term) > 3}
        return sum(1 for term in terms if term in haystack)

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
                reviewer_votes.items(),
                key=lambda item: (-item[1], order.get(item[0], 999)),
            )
            if agent != owner
        ]
        if not reviewers:
            reviewers = [agent for agent in agents if agent != owner][:1]
        return owner, reviewers[: max(1, min(2, len(reviewers)))], dict(owner_votes), dict(reviewer_votes)

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
        memory_context = self._room_memory_context(room_name)
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
            memory_context = self._room_memory_context(room_name)

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
                body=self._with_room_memory(prompt, memory_context),
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
        memory_context = self._room_memory_context(memory_room)
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
                delivery_message.body = self._with_room_memory(delivery_message.body, memory_context)
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
            },
            "deliveries": deliveries,
            "dead_letters": dead_letters,
        }
