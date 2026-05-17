from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass(slots=True)
class FabricMessage:
    source: str
    target: str
    body: str
    conversation_id: str | None = None
    message_id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=utc_now_iso)
    message_type: str = "message"
    subject: str | None = None
    priority: str = "normal"
    reply_to: str | None = None
    hop_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "FabricMessage":
        if not self.conversation_id:
            self.conversation_id = self.message_id
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AdapterReply:
    adapter_id: str
    ok: bool
    body: str
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int | None = None
    external_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
