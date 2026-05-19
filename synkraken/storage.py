from __future__ import annotations

from pathlib import Path
from threading import Lock
import json
import sqlite3
import uuid

from .models import AdapterReply, FabricMessage, utc_now_iso


AGENT_STATUSES = {"configured", "online", "idle", "working", "blocked", "offline", "disabled"}


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

CREATE TABLE IF NOT EXISTS room_memory (
    memory_id TEXT PRIMARY KEY,
    room_name TEXT NOT NULL UNIQUE,
    purpose TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    rules TEXT NOT NULL DEFAULT '',
    constraints TEXT NOT NULL DEFAULT '',
    current_focus TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_events (
    event_id TEXT PRIMARY KEY,
    room_name TEXT NOT NULL,
    actor TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agents (
    adapter_id TEXT PRIMARY KEY,
    runtime_name TEXT NOT NULL,
    adapter_type TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'configured',
    last_seen_at TEXT,
    runtime TEXT NOT NULL DEFAULT '',
    current_task_id TEXT,
    current_room TEXT,
    last_message_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_events (
    event_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(agent_id) REFERENCES agents(adapter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS room_members (
    room_name TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    left_at TEXT,
    PRIMARY KEY (room_name, adapter_id),
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    room_name TEXT,
    assigned_agent_id TEXT,
    source_message_id TEXT,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE SET NULL,
    FOREIGN KEY(assigned_agent_id) REFERENCES agents(adapter_id) ON DELETE SET NULL,
    FOREIGN KEY(source_message_id) REFERENCES messages(message_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS task_comments (
    comment_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_runs (
    team_run_id TEXT PRIMARY KEY,
    task_id TEXT,
    room_name TEXT NOT NULL,
    source_prompt TEXT NOT NULL,
    owner_agent TEXT,
    reviewers_json TEXT NOT NULL,
    participants_json TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    final_report TEXT NOT NULL DEFAULT '',
    approved_by TEXT,
    approval_required INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE SET NULL,
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS team_events (
    event_id TEXT PRIMARY KEY,
    team_run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    detail TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(team_run_id) REFERENCES team_runs(team_run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_target ON messages(target);
CREATE INDEX IF NOT EXISTS idx_deliveries_message_id ON deliveries(message_id);
CREATE INDEX IF NOT EXISTS idx_dead_letters_message_id ON dead_letters(message_id);
CREATE INDEX IF NOT EXISTS idx_room_members_room_name ON room_members(room_name);
CREATE INDEX IF NOT EXISTS idx_room_memory_room_name ON room_memory(room_name);
CREATE INDEX IF NOT EXISTS idx_memory_events_room_name ON memory_events(room_name);
CREATE INDEX IF NOT EXISTS idx_memory_events_created_at ON memory_events(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_events_agent_id ON agent_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_created_at ON agent_events(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_room_name ON tasks(room_name);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_agent_id ON tasks(assigned_agent_id);
CREATE INDEX IF NOT EXISTS idx_task_comments_task_id ON task_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_task_events_created ON task_events(created_at);
CREATE INDEX IF NOT EXISTS idx_team_runs_room ON team_runs(room_name);
CREATE INDEX IF NOT EXISTS idx_team_runs_status ON team_runs(status);
CREATE INDEX IF NOT EXISTS idx_team_events_run ON team_events(team_run_id);
CREATE INDEX IF NOT EXISTS idx_team_events_created ON team_events(created_at);
"""


class Storage:
    def __init__(self, sqlite_path: str | Path) -> None:
        self.sqlite_path = Path(sqlite_path).expanduser().resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._conn:
            self._conn.executescript(SCHEMA)
            self._migrate_schema()

    def _migrate_schema(self) -> None:
        task_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "created_by" not in task_columns:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN created_by TEXT NOT NULL DEFAULT 'system'")
        if "updated_by" not in task_columns:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN updated_by TEXT NOT NULL DEFAULT 'system'")
        agent_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(agents)").fetchall()
        }
        agent_additions = {
            "status": "TEXT NOT NULL DEFAULT 'configured'",
            "last_seen_at": "TEXT",
            "runtime": "TEXT NOT NULL DEFAULT ''",
            "current_task_id": "TEXT",
            "current_room": "TEXT",
            "last_message_at": "TEXT",
        }
        for column, definition in agent_additions.items():
            if column not in agent_columns:
                self._conn.execute(f"ALTER TABLE agents ADD COLUMN {column} {definition}")

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

    def _empty_room_memory(self, room_name: str) -> dict:
        return {
            "memory_id": None,
            "room_name": room_name,
            "room": room_name,
            "purpose": "",
            "objective": "",
            "rules": "",
            "constraints": "",
            "current_focus": "",
            "notes": "",
            "created_at": None,
            "updated_at": None,
            "updated_by": None,
        }

    def get_room_memory(self, room_name: str) -> dict | None:
        if not self.room_exists(room_name):
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT memory_id, room_name, purpose, objective, rules, constraints,
                       current_focus, notes, created_at, updated_at, updated_by
                FROM room_memory
                WHERE room_name = ?
                """,
                (room_name,),
            ).fetchone()
        if not row:
            return self._empty_room_memory(room_name)
        data = dict(row)
        data["room"] = data["room_name"]
        return data

    def upsert_room_memory(self, room_name: str, fields: dict, actor: str, updated_at: str) -> dict | None:
        allowed = {"purpose", "objective", "rules", "constraints", "current_focus", "notes"}
        clean = {key: str(value or "") for key, value in fields.items() if key in allowed}
        if not clean and not self.room_exists(room_name):
            return None
        if not clean:
            return self.get_room_memory(room_name)
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM rooms WHERE name = ?", (room_name,)).fetchone() is None:
                return None
            row = self._conn.execute("SELECT * FROM room_memory WHERE room_name = ?", (room_name,)).fetchone()
            if row is None:
                memory_id = str(uuid.uuid4())
                self._conn.execute(
                    """
                    INSERT INTO room_memory (
                        memory_id, room_name, purpose, objective, rules, constraints,
                        current_focus, notes, created_at, updated_at, updated_by
                    ) VALUES (?, ?, '', '', '', '', '', '', ?, ?, ?)
                    """,
                    (memory_id, room_name, updated_at, updated_at, actor),
                )
                before = {
                    "purpose": "", "objective": "", "rules": "",
                    "constraints": "", "current_focus": "", "notes": "",
                }
            else:
                before = dict(row)
            changed = {key: value for key, value in clean.items() if str(before.get(key) or "") != value}
            if changed:
                assignments = [f"{key} = ?" for key in changed]
                assignments.extend(["updated_at = ?", "updated_by = ?"])
                self._conn.execute(
                    f"UPDATE room_memory SET {', '.join(assignments)} WHERE room_name = ?",
                    [*changed.values(), updated_at, actor, room_name],
                )
                for key, value in changed.items():
                    self._conn.execute(
                        """
                        INSERT INTO memory_events (
                            event_id, room_name, actor, field_changed,
                            old_value, new_value, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), room_name, actor, key, str(before.get(key) or ""), value, updated_at),
                    )
        return self.get_room_memory(room_name)

    def list_room_memory_events(self, room_name: str, limit: int = 50) -> list[dict] | None:
        if not self.room_exists(room_name):
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, room_name, actor, field_changed, old_value, new_value, created_at
                FROM memory_events
                WHERE room_name = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (room_name, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def sync_agents(self, agents: list[dict]) -> None:
        seen = {str(agent["adapter_id"]) for agent in agents}
        now = utc_now_iso()
        with self._lock, self._conn:
            existing = {
                row["adapter_id"]: dict(row)
                for row in self._conn.execute("SELECT * FROM agents").fetchall()
            }
            for agent in agents:
                adapter_id = str(agent["adapter_id"])
                enabled = bool(agent.get("enabled", True))
                runtime = str(agent.get("runtime") or agent.get("type") or "unknown")
                target_status = "online" if enabled else "disabled"
                current = existing.get(adapter_id)
                if current is None:
                    self._conn.execute(
                        """
                        INSERT INTO agents (
                            adapter_id, runtime_name, adapter_type, enabled,
                            status, last_seen_at, runtime
                        ) VALUES (?, ?, ?, ?, 'configured', NULL, ?)
                        """,
                        (
                            adapter_id,
                            agent.get("runtime_name") or adapter_id,
                            agent.get("type") or "unknown",
                            1 if enabled else 0,
                            runtime,
                        ),
                    )
                    current = {"status": "configured"}
                else:
                    self._conn.execute(
                        """
                        UPDATE agents
                        SET runtime_name = ?, adapter_type = ?, enabled = ?, runtime = ?
                        WHERE adapter_id = ?
                        """,
                        (
                            agent.get("runtime_name") or adapter_id,
                            agent.get("type") or "unknown",
                            1 if enabled else 0,
                            runtime,
                            adapter_id,
                        ),
                    )
                if current.get("status") != target_status:
                    self._conn.execute(
                        "UPDATE agents SET status = ?, last_seen_at = ? WHERE adapter_id = ?",
                        (target_status, now, adapter_id),
                    )
                    self._save_agent_event(adapter_id, "status_changed", current.get("status"), target_status, now)
                elif enabled:
                    self._conn.execute(
                        "UPDATE agents SET last_seen_at = ? WHERE adapter_id = ?",
                        (now, adapter_id),
                    )
            for adapter_id, current in existing.items():
                if adapter_id in seen:
                    continue
                if current.get("status") != "offline":
                    self._conn.execute(
                        "UPDATE agents SET status = 'offline', enabled = 0, last_seen_at = ? WHERE adapter_id = ?",
                        (now, adapter_id),
                    )
                    self._save_agent_event(adapter_id, "status_changed", current.get("status"), "offline", now)

    def list_agents(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT adapter_id, adapter_id AS agent_id, runtime_name, adapter_type AS type, enabled,
                       status, last_seen_at, runtime, current_task_id,
                       current_room, last_message_at
                FROM agents
                ORDER BY adapter_id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_agent(self, adapter_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT adapter_id, adapter_id AS agent_id, runtime_name, adapter_type AS type, enabled,
                       status, last_seen_at, runtime, current_task_id,
                       current_room, last_message_at
                FROM agents
                WHERE adapter_id = ?
                """,
                (adapter_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_agent_events(self, adapter_id: str, limit: int = 50) -> list[dict] | None:
        if self.get_agent(adapter_id) is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, agent_id, event_type, old_value, new_value, created_at
                FROM agent_events
                WHERE agent_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (adapter_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_agent_presence(
        self,
        adapter_id: str,
        *,
        status: str | None = None,
        current_task_id: str | None | object = ...,
        current_room: str | None | object = ...,
        last_message_at: str | None = None,
        event_type: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        seen_at: str | None = None,
    ) -> dict | None:
        now = seen_at or utc_now_iso()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM agents WHERE adapter_id = ?", (adapter_id,)).fetchone()
            if row is None:
                return None
            before = dict(row)
            updates: dict[str, object] = {"last_seen_at": now}
            if status is not None:
                if status not in AGENT_STATUSES:
                    raise ValueError(f"invalid agent status: {status}")
                updates["status"] = status
            if current_task_id is not ...:
                updates["current_task_id"] = current_task_id
            if current_room is not ...:
                updates["current_room"] = current_room
            if last_message_at is not None:
                updates["last_message_at"] = last_message_at
            assignments = ", ".join(f"{key} = ?" for key in updates)
            self._conn.execute(
                f"UPDATE agents SET {assignments} WHERE adapter_id = ?",
                [*updates.values(), adapter_id],
            )
            if status is not None and before.get("status") != status:
                self._save_agent_event(adapter_id, "status_changed", before.get("status"), status, now)
            if event_type is not None:
                self._save_agent_event(adapter_id, event_type, old_value, new_value, now)
        return self.get_agent(adapter_id)

    def record_agent_event(
        self,
        adapter_id: str,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM agents WHERE adapter_id = ?", (adapter_id,)).fetchone() is None:
                return
            self._save_agent_event(adapter_id, event_type, old_value, new_value, created_at or utc_now_iso())

    def _save_agent_event(
        self,
        adapter_id: str,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
        created_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO agent_events (event_id, agent_id, event_type, old_value, new_value, created_at)
            SELECT ?, ?, ?, ?, ?, ?
            WHERE EXISTS (SELECT 1 FROM agents WHERE adapter_id = ?)
            """,
            (str(uuid.uuid4()), adapter_id, event_type, old_value, new_value, created_at, adapter_id),
        )

    def create_room(self, name: str, description: str, created_at: str,
                    members: list[str] | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO rooms (name, description, created_at) VALUES (?, ?, ?)",
                (name, description or '', created_at),
            )
            for adapter_id in (members or []):
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO room_members (room_name, adapter_id, joined_at) VALUES (?, ?, ?)",
                    (name, adapter_id, created_at),
                )
                if cur.rowcount:
                    self._conn.execute(
                        "UPDATE agents SET current_room = ?, last_seen_at = ? WHERE adapter_id = ?",
                        (name, created_at, adapter_id),
                    )
                    self._save_agent_event(adapter_id, "room_joined", None, name, created_at)

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
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO room_members (room_name, adapter_id, joined_at) VALUES (?, ?, ?)",
                (name, adapter_id, joined_at),
            )
            if cur.rowcount:
                self._conn.execute(
                    "UPDATE agents SET current_room = ?, last_seen_at = ? WHERE adapter_id = ?",
                    (name, joined_at, adapter_id),
                )
                self._save_agent_event(adapter_id, "room_joined", None, name, joined_at)

    def remove_room_member(self, name: str, adapter_id: str) -> None:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM room_members WHERE room_name = ? AND adapter_id = ?",
                (name, adapter_id),
            )
            if cur.rowcount:
                now = utc_now_iso()
                self._conn.execute(
                    "UPDATE agents SET current_room = NULL, last_seen_at = ? WHERE adapter_id = ? AND current_room = ?",
                    (now, adapter_id, name),
                )
                self._save_agent_event(adapter_id, "room_left", name, None, now)

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
                FROM (
                    SELECT message_id, conversation_id, source, target, timestamp,
                           message_type, subject, priority, reply_to, hop_count, body
                    FROM messages
                    WHERE target = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                ORDER BY timestamp ASC
                """,
                (target, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ── tasks ──────────────────────────────────────────────────────────────

    def message_exists(self, message_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM messages WHERE message_id = ?", (message_id,)
            ).fetchone()
        return row is not None

    def create_task(
        self,
        task_id: str,
        title: str,
        description: str,
        status: str,
        priority: str,
        room_name: str | None,
        assigned_agent_id: str | None,
        source_message_id: str | None,
        actor: str,
        created_at: str,
    ) -> dict:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks (
                    task_id, title, description, status, priority, room_name,
                    assigned_agent_id, source_message_id, created_by, updated_by,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    description,
                    status,
                    priority,
                    room_name,
                    assigned_agent_id,
                    source_message_id,
                    actor,
                    actor,
                    created_at,
                    created_at,
                ),
            )
            self._save_task_event(task_id, actor, "created", None, None, created_at)
            if assigned_agent_id:
                self._conn.execute(
                    "UPDATE agents SET current_task_id = ?, last_seen_at = ? WHERE adapter_id = ?",
                    (task_id, created_at, assigned_agent_id),
                )
                self._save_agent_event(assigned_agent_id, "task_assigned", None, task_id, created_at)
        task = self.get_task(task_id)
        assert task is not None
        return task

    def get_task(self, task_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            comments = self._conn.execute(
                "SELECT comment_id, task_id, author, body, created_at FROM task_comments WHERE task_id = ? ORDER BY created_at ASC, comment_id ASC",
                (task_id,),
            ).fetchall()
        if not row:
            return None
        data = dict(row)
        data["comments"] = [dict(comment) for comment in comments]
        return data

    def list_tasks(self, room_name: str | None = None) -> list[dict]:
        sql = "SELECT * FROM tasks"
        params: tuple = ()
        if room_name is not None:
            sql += " WHERE room_name = ?"
            params = (room_name,)
        sql += """
            ORDER BY
              CASE status
                WHEN 'blocked' THEN 0
                WHEN 'in_progress' THEN 1
                WHEN 'open' THEN 2
                WHEN 'done' THEN 3
                ELSE 4
              END,
              CASE priority
                WHEN 'high' THEN 0
                WHEN 'normal' THEN 1
                WHEN 'low' THEN 2
                ELSE 3
              END,
              updated_at DESC
        """
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def update_task(self, task_id: str, fields: dict, actor: str, updated_at: str) -> dict | None:
        if not fields:
            return self.get_task(task_id)
        before = self.get_task(task_id)
        if before is None:
            return None
        assignments = [f"{key} = ?" for key in fields]
        assignments.append("updated_by = ?")
        assignments.append("updated_at = ?")
        values = list(fields.values()) + [actor, updated_at, task_id]
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE task_id = ?",
                values,
            )
            if "assigned_agent_id" in fields and fields["assigned_agent_id"] != before["assigned_agent_id"]:
                self._save_task_event(task_id, actor, "assigned", before["assigned_agent_id"], fields["assigned_agent_id"], updated_at)
                if before["assigned_agent_id"]:
                    self._conn.execute(
                        "UPDATE agents SET current_task_id = NULL, last_seen_at = ? WHERE adapter_id = ? AND current_task_id = ?",
                        (updated_at, before["assigned_agent_id"], task_id),
                    )
                if fields["assigned_agent_id"]:
                    self._conn.execute(
                        "UPDATE agents SET current_task_id = ?, last_seen_at = ? WHERE adapter_id = ?",
                        (task_id, updated_at, fields["assigned_agent_id"]),
                    )
                    self._save_agent_event(fields["assigned_agent_id"], "task_assigned", before["assigned_agent_id"], task_id, updated_at)
            if "status" in fields and fields["status"] != before["status"]:
                self._save_task_event(task_id, actor, "status_changed", before["status"], fields["status"], updated_at)
                if fields["status"] == "blocked":
                    self._save_task_event(task_id, actor, "blocked", before["status"], "blocked", updated_at)
                if fields["status"] == "done":
                    self._save_task_event(task_id, actor, "completed", before["status"], "done", updated_at)
                    assigned = fields.get("assigned_agent_id", before["assigned_agent_id"])
                    if assigned:
                        self._conn.execute(
                            "UPDATE agents SET current_task_id = NULL, last_seen_at = ? WHERE adapter_id = ? AND current_task_id = ?",
                            (updated_at, assigned, task_id),
                        )
                        self._save_agent_event(assigned, "task_completed", task_id, "done", updated_at)
            if "priority" in fields and fields["priority"] != before["priority"]:
                self._save_task_event(task_id, actor, "priority_changed", before["priority"], fields["priority"], updated_at)
            generic = {k: v for k, v in fields.items() if k not in {"assigned_agent_id", "status", "priority"} and v != before.get(k)}
            if generic:
                self._save_task_event(
                    task_id,
                    actor,
                    "updated",
                    json.dumps({k: before.get(k) for k in generic}, ensure_ascii=False),
                    json.dumps(generic, ensure_ascii=False),
                    updated_at,
                )
        if cur.rowcount == 0:
            return None
        return self.get_task(task_id)

    def add_task_comment(
        self,
        comment_id: str,
        task_id: str,
        author: str,
        body: str,
        actor: str,
        created_at: str,
    ) -> dict | None:
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO task_comments (comment_id, task_id, author, body, created_at)
                SELECT ?, ?, ?, ?, ?
                WHERE EXISTS (SELECT 1 FROM tasks WHERE task_id = ?)
                """,
                (comment_id, task_id, author, body, created_at, task_id),
            )
            if cur.rowcount == 0:
                return None
            self._conn.execute(
                "UPDATE tasks SET updated_by = ?, updated_at = ? WHERE task_id = ?",
                (actor, created_at, task_id),
            )
            self._save_task_event(task_id, actor, "commented", None, body, created_at)
        task = self.get_task(task_id)
        return task

    def record_task_event(
        self,
        task_id: str,
        actor: str,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM tasks WHERE task_id = ?", (task_id,)).fetchone() is None:
                return
            self._save_task_event(task_id, actor, event_type, old_value, new_value, created_at or utc_now_iso())

    def list_task_events(self, task_id: str) -> list[dict] | None:
        if self.get_task(task_id) is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, task_id, actor, event_type, old_value, new_value, created_at
                FROM task_events
                WHERE task_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ── team governance ────────────────────────────────────────────────────

    def _team_run_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["reviewers"] = json.loads(data.pop("reviewers_json") or "[]")
        data["participants"] = json.loads(data.pop("participants_json") or "[]")
        data["approval_required"] = bool(data["approval_required"])
        return data

    def create_team_run(
        self,
        *,
        team_run_id: str,
        task_id: str | None,
        room_name: str,
        source_prompt: str,
        owner_agent: str | None,
        reviewers: list[str],
        participants: list[str],
        status: str,
        started_at: str,
        final_report: str = "",
        approval_required: bool = False,
    ) -> dict:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO team_runs (
                    team_run_id, task_id, room_name, source_prompt, owner_agent,
                    reviewers_json, participants_json, status, started_at,
                    completed_at, final_report, approved_by, approval_required
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?)
                """,
                (
                    team_run_id,
                    task_id,
                    room_name,
                    source_prompt,
                    owner_agent,
                    json.dumps(reviewers, ensure_ascii=False),
                    json.dumps(participants, ensure_ascii=False),
                    status,
                    started_at,
                    final_report,
                    1 if approval_required else 0,
                ),
            )
        run = self.get_team_run(team_run_id)
        assert run is not None
        return run

    def update_team_run(self, team_run_id: str, fields: dict) -> dict | None:
        if not fields:
            return self.get_team_run(team_run_id)
        clean: dict[str, object] = {}
        for key, value in fields.items():
            if key == "reviewers":
                clean["reviewers_json"] = json.dumps(value or [], ensure_ascii=False)
            elif key == "participants":
                clean["participants_json"] = json.dumps(value or [], ensure_ascii=False)
            elif key == "approval_required":
                clean[key] = 1 if value else 0
            elif key in {"task_id", "room_name", "source_prompt", "owner_agent", "status", "started_at", "completed_at", "final_report", "approved_by"}:
                clean[key] = value
        if not clean:
            return self.get_team_run(team_run_id)
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE team_runs SET {assignments} WHERE team_run_id = ?",
                [*clean.values(), team_run_id],
            )
            if cur.rowcount == 0:
                return None
        return self.get_team_run(team_run_id)

    def get_team_run(self, team_run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM team_runs WHERE team_run_id = ?",
                (team_run_id,),
            ).fetchone()
        return self._team_run_from_row(row) if row else None

    def list_team_runs(self, room_name: str | None = None, limit: int = 25) -> list[dict]:
        sql = "SELECT * FROM team_runs"
        params: list[object] = []
        if room_name:
            sql += " WHERE room_name = ?"
            params.append(room_name)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._team_run_from_row(row) for row in rows]

    def record_team_event(
        self,
        team_run_id: str,
        event_type: str,
        *,
        actor: str | None = None,
        detail: str | None = None,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM team_runs WHERE team_run_id = ?", (team_run_id,)).fetchone() is None:
                return
            self._conn.execute(
                """
                INSERT INTO team_events (event_id, team_run_id, event_type, actor, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), team_run_id, event_type, actor, detail, created_at or utc_now_iso()),
            )

    def list_team_events(self, team_run_id: str, limit: int = 100) -> list[dict] | None:
        if self.get_team_run(team_run_id) is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, team_run_id, event_type, actor, detail, created_at
                FROM team_events
                WHERE team_run_id = ?
                ORDER BY created_at ASC, rowid ASC
                LIMIT ?
                """,
                (team_run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _save_task_event(
        self,
        task_id: str,
        actor: str,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
        created_at: str,
    ) -> None:
        import uuid

        self._conn.execute(
            """
            INSERT INTO task_events (event_id, task_id, actor, event_type, old_value, new_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), task_id, actor, event_type, old_value, new_value, created_at),
        )
