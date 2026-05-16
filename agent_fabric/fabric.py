from __future__ import annotations

from datetime import datetime, timezone
from queue import Queue
from threading import Lock
from typing import Any
import time

from .adapters import build_adapter
from .models import FabricMessage, utc_now_iso
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
        for adapter_id, adapter_config in config.get("adapters", {}).items():
            if adapter_config.get("enabled", True):
                self.adapters[adapter_id] = build_adapter(adapter_id, adapter_config)
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
        return [adapter.health() for adapter in self.adapters.values()]

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = FabricMessage(
            source=str(payload["source"]),
            target=str(payload["target"]),
            body=str(payload["body"]),
            conversation_id=payload.get("conversation_id"),
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
        targets = resolve_targets(message.source, message.target, self.adapters.keys())
        deliveries: list[dict[str, Any]] = []
        dead_letters: list[dict[str, Any]] = []
        for target_id in targets:
            adapter = self.adapters[target_id]
            runtime_name = adapter.health().get('runtime_name', target_id)
            last_reply = None
            for attempt in range(1, self.retry_limit + 2):
                self.event_bus.publish('typing.started', {
                    'adapter_id': target_id,
                    'runtime_name': runtime_name,
                    'message_id': message.message_id,
                    'conversation_id': message.conversation_id,
                })
                reply = adapter.send(message)
                self.event_bus.publish('typing.stopped', {
                    'adapter_id': target_id,
                    'runtime_name': runtime_name,
                    'message_id': message.message_id,
                    'conversation_id': message.conversation_id,
                    'ok': reply.ok,
                })
                last_reply = reply
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
                    'status': 'acknowledged' if reply.ok else 'failed',
                    'body_preview': (reply.body or '')[:160],
                }
                deliveries.append(delivery_payload)
                self.event_bus.publish('delivery.recorded', delivery_payload)
                if reply.ok:
                    break
                if attempt <= self.retry_limit:
                    time.sleep(self.retry_backoff_seconds)
            if last_reply is not None and not last_reply.ok:
                dead_payload = {
                    'message': message.to_dict(),
                    'reply': last_reply.to_dict(),
                }
                self.storage.save_dead_letter(
                    message.message_id,
                    target_id,
                    reason=last_reply.error or 'delivery_failed',
                    payload=dead_payload,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                dead_letter = {
                    'adapter_id': target_id,
                    'reason': last_reply.error or 'delivery_failed',
                    'message_id': message.message_id,
                    'conversation_id': message.conversation_id,
                }
                dead_letters.append(dead_letter)
                self.event_bus.publish('dead-letter.recorded', dead_letter)
        return {
            "message": message.to_dict(),
            "deliveries": deliveries,
            "dead_letters": dead_letters,
        }
