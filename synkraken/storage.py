from __future__ import annotations

from pathlib import Path
from threading import Lock
import json
import sqlite3

from .models import AdapterReply, FabricMessage


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    message_type TEXT NOT NULL,
    subject TEXT,
    priority TEXT NOT NULL,
    reply_to TEXT,
    hop_count INTEGER NOT NULL,
    body TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    status TEXT NOT NULL,
    ok INTEGER NOT NULL,
    body TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER,
    external_reference TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(message_id) REFERENCES messages(message_id)
);

CREATE TABLE IF NOT EXISTS dead_letters (
    dead_letter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS room_members (
    room_name TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (room_name, adapter_id),
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_target ON messages(target);
CREATE INDEX IF NOT EXISTS idx_deliveries_message_id ON deliveries(message_id);
CREATE INDEX IF NOT EXISTS idx_dead_letters_message_id ON dead_letters(message_id);
CREATE INDEX IF NOT EXISTS idx_room_members_room_name ON room_members(room_name);
"""


class Storage:
    def __init__(self, sqlite_path: str | Path) -> None:
        self.sqlite_path = Path(sqlite_path).expanduser().resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(SCHEMA)

    def save_message(self, message: FabricMessage) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO messages (
                    message_id, conversation_id, source, target, timestamp,
                    message_type, subject, priority, reply_to, hop_count,
                    body, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.conversation_id,
                    message.source,
                    message.target,
                    message.timestamp,
                    message.message_type,
                    message.subject,
                    message.priority,
                    message.reply_to,
                    message.hop_count,
                    message.body,
                    json.dumps(message.metadata, ensure_ascii=False),
                ),
            )

    def save_delivery(self, message_id: str, reply: AdapterReply, created_at: str, attempts: int = 1) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO deliveries (
                    message_id, adapter_id, status, ok, body, error, duration_ms,
                    external_reference, attempts, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    reply.adapter_id,
                    "acknowledged" if reply.ok else "failed",
                    1 if reply.ok else 0,
                    reply.body,
                    reply.error,
                    reply.duration_ms,
                    reply.external_reference,
                    attempts,
                    json.dumps(reply.raw, ensure_ascii=False),
                    created_at,
                ),
            )

    def save_dead_letter(self, message_id: str, adapter_id: str, reason: str, payload: dict, created_at: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO dead_letters (
                    message_id, adapter_id, reason, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    adapter_id,
                    reason,
                    json.dumps(payload, ensure_ascii=False),
                    created_at,
                ),
            )

    def get_conversation(self, conversation_id: str) -> dict:
        with self._lock:
            msg_rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC, message_id ASC",
                (conversation_id,),
            ).fetchall()
            del_rows = self._conn.execute(
                "SELECT * FROM deliveries WHERE message_id IN (SELECT message_id FROM messages WHERE conversation_id = ?) ORDER BY delivery_id ASC",
                (conversation_id,),
            ).fetchall()
            dead_rows = self._conn.execute(
                "SELECT * FROM dead_letters WHERE message_id IN (SELECT message_id FROM messages WHERE conversation_id = ?) ORDER BY dead_letter_id ASC",
                (conversation_id,),
            ).fetchall()
        return {
            "conversation_id": conversation_id,
            "messages": [dict(row) for row in msg_rows],
            "deliveries": [dict(row) for row in del_rows],
            "dead_letters": [dict(row) for row in dead_rows],
        }

    def list_recent_conversations(self, limit: int = 10) -> dict:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT conversation_id,
                       MAX(timestamp) AS last_timestamp,
                       COUNT(*) AS message_count,
                       MIN(source) AS sample_source,
                       MIN(target) AS sample_target,
                       MIN(substr(body, 1, 120)) AS preview
                FROM messages
                GROUP BY conversation_id
                ORDER BY last_timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"conversations": [dict(row) for row in rows]}

    def list_recent_deliveries(self, limit: int = 10) -> dict:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT delivery_id, message_id, adapter_id, status, ok, error,
                       duration_ms, attempts, created_at, substr(body, 1, 160) AS body_preview
                FROM deliveries
                ORDER BY delivery_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"deliveries": [dict(row) for row in rows]}

    def list_dead_letters(self, limit: int = 10) -> dict:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT dead_letter_id, message_id, adapter_id, reason, created_at
                FROM dead_letters
                ORDER BY dead_letter_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"dead_letters": [dict(row) for row in rows]}

    # ── rooms ──────────────────────────────────────────────────────────────

    def create_room(self, name: str, description: str, created_at: str,
                    members: list[str] | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO rooms (name, description, created_at) VALUES (?, ?, ?)",
                (name, description or '', created_at),
            )
            for adapter_id in (members or []):
                self._conn.execute(
                    "INSERT OR IGNORE INTO room_members (room_name, adapter_id, joined_at) VALUES (?, ?, ?)",
                    (name, adapter_id, created_at),
                )

    def delete_room(self, name: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM room_members WHERE room_name = ?", (name,))
            self._conn.execute("DELETE FROM rooms WHERE name = ?", (name,))

    def room_exists(self, name: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM rooms WHERE name = ?", (name,)
            ).fetchone()
        return row is not None

    def add_room_member(self, name: str, adapter_id: str, joined_at: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO room_members (room_name, adapter_id, joined_at) VALUES (?, ?, ?)",
                (name, adapter_id, joined_at),
            )

    def remove_room_member(self, name: str, adapter_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM room_members WHERE room_name = ? AND adapter_id = ?",
                (name, adapter_id),
            )

    def get_room_members(self, name: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT adapter_id FROM room_members WHERE room_name = ? ORDER BY joined_at ASC",
                (name,),
            ).fetchall()
        return [row["adapter_id"] for row in rows]

    def get_room(self, name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT name, description, created_at FROM rooms WHERE name = ?",
                (name,),
            ).fetchone()
            if not row:
                return None
            members = self._conn.execute(
                "SELECT adapter_id, joined_at FROM room_members WHERE room_name = ? ORDER BY joined_at ASC",
                (name,),
            ).fetchall()
        return {
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
            "members": [dict(m) for m in members],
        }

    def list_rooms(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT r.name, r.description, r.created_at,
                       (SELECT COUNT(*) FROM room_members rm WHERE rm.room_name = r.name) AS member_count,
                       (SELECT MAX(timestamp) FROM messages WHERE target = 'room:' || r.name) AS last_activity
                FROM rooms r
                ORDER BY COALESCE(
                    (SELECT MAX(timestamp) FROM messages WHERE target = 'room:' || r.name),
                    r.created_at
                ) DESC
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_room_messages(self, name: str, limit: int = 50) -> list[dict]:
        target = f"room:{name}"
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT message_id, conversation_id, source, target, timestamp,
                       message_type, subject, priority, reply_to, hop_count, body
                FROM messages
                WHERE target = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (target, limit),
            ).fetchall()
        return [dict(row) for row in rows]
