from __future__ import annotations

from pathlib import Path
from threading import Lock
import json
import sqlite3
import uuid

from .models import AdapterReply, FabricMessage, utc_now_iso


AGENT_STATUSES = {"configured", "online", "idle", "working", "blocked", "offline", "disabled"}
AGENT_COST_TIERS = {"cheap", "medium", "premium", "local"}
USAGE_RISKS = {"low", "medium", "high"}
AGENT_PROFILE_ROLES = {"owner", "reviewer", "guardrail", "token_police", "summary", "ops"}
SHARED_MEMORY_STATUSES = {"proposed", "peer_approved", "rejected", "archived"}
DECISION_STATUSES = {"proposed", "approved", "rejected", "superseded"}
HANDOFF_STATUSES = {"pending", "accepted", "rejected", "completed"}
SHARED_MEMORY_TYPES = {
    "fact", "decision", "preference", "rule", "lesson", "technical_note", "project_context",
}

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

CREATE TABLE IF NOT EXISTS shared_memory (
    memory_id TEXT PRIMARY KEY,
    room_name TEXT NULL,
    workspace TEXT NULL,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TEXT,
    reviewed_by TEXT NULL,
    review_result TEXT NULL,
    review_reason TEXT NULL,
    reviewed_at TEXT NULL,
    approved_by TEXT NULL,
    approved_at TEXT NULL,
    source_team_run_id TEXT NULL,
    source_task_id TEXT NULL,
    source_message_id TEXT NULL,
    token_cost_estimate INTEGER DEFAULT 0,
    use_count INTEGER DEFAULT 0,
    last_used_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS memory_events (
    event_id TEXT PRIMARY KEY,
    room_name TEXT,
    memory_id TEXT,
    event_type TEXT,
    actor TEXT NOT NULL,
    field_changed TEXT,
    old_value TEXT,
    new_value TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE,
    FOREIGN KEY(memory_id) REFERENCES shared_memory(memory_id) ON DELETE CASCADE
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
    last_message_at TEXT,
    cost_tier TEXT NOT NULL DEFAULT 'medium',
    preferred_roles_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    speed INTEGER NOT NULL DEFAULT 5,
    trust INTEGER NOT NULL DEFAULT 5
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

CREATE TABLE IF NOT EXISTS goal_runs (
    goal_run_id TEXT PRIMARY KEY,
    room_name TEXT NOT NULL,
    source_goal TEXT NOT NULL,
    status TEXT NOT NULL,
    threshold INTEGER NOT NULL,
    max_rounds INTEGER NOT NULL,
    current_round INTEGER NOT NULL,
    owner_agent TEXT NULL,
    reviewers TEXT,
    participants TEXT,
    token_police_agent TEXT NULL,
    guardrail_agent TEXT NULL,
    success_criteria TEXT,
    latest_score INTEGER DEFAULT 0,
    final_report TEXT,
    token_budget_chars INTEGER DEFAULT 4000,
    estimated_context_chars INTEGER DEFAULT 0,
    guardrail_status TEXT,
    linked_task_id TEXT NULL,
    linked_team_run_ids TEXT,
    started_at TEXT,
    completed_at TEXT NULL,
    created_by TEXT,
    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE,
    FOREIGN KEY(linked_task_id) REFERENCES tasks(task_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS goal_events (
    event_id TEXT PRIMARY KEY,
    goal_run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(goal_run_id) REFERENCES goal_runs(goal_run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runtime_registry (
    runtime_id TEXT PRIMARY KEY,
    runtime_type TEXT NOT NULL,
    adapter_type TEXT NOT NULL DEFAULT 'unsupported',
    version TEXT NOT NULL DEFAULT '',
    command_json TEXT NOT NULL DEFAULT '[]',
    working_dir TEXT NOT NULL DEFAULT '',
    timeout INTEGER NOT NULL DEFAULT 90,
    cost_profile TEXT NOT NULL DEFAULT 'medium',
    usage_risk TEXT NOT NULL DEFAULT 'medium',
    preferred_roles_json TEXT NOT NULL DEFAULT '[]',
    avoid_roles_json TEXT NOT NULL DEFAULT '[]',
    supported_modes_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_packs (
    workspace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    rooms_json TEXT NOT NULL DEFAULT '[]',
    agents_json TEXT NOT NULL DEFAULT '[]',
    memory_json TEXT NOT NULL DEFAULT '[]',
    skills_json TEXT NOT NULL DEFAULT '[]',
    goals_json TEXT NOT NULL DEFAULT '[]',
    repos_json TEXT NOT NULL DEFAULT '[]',
    governance_json TEXT NOT NULL DEFAULT '{}',
    runtime_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_target ON messages(target);
CREATE INDEX IF NOT EXISTS idx_deliveries_message_id ON deliveries(message_id);
CREATE INDEX IF NOT EXISTS idx_dead_letters_message_id ON dead_letters(message_id);
CREATE INDEX IF NOT EXISTS idx_room_members_room_name ON room_members(room_name);
CREATE INDEX IF NOT EXISTS idx_room_memory_room_name ON room_memory(room_name);
CREATE INDEX IF NOT EXISTS idx_memory_events_room_name ON memory_events(room_name);
CREATE INDEX IF NOT EXISTS idx_memory_events_created_at ON memory_events(created_at);
CREATE INDEX IF NOT EXISTS idx_shared_memory_status ON shared_memory(status);
CREATE INDEX IF NOT EXISTS idx_shared_memory_room ON shared_memory(room_name);
CREATE INDEX IF NOT EXISTS idx_shared_memory_workspace ON shared_memory(workspace);
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
CREATE INDEX IF NOT EXISTS idx_goal_runs_room ON goal_runs(room_name);
CREATE INDEX IF NOT EXISTS idx_goal_runs_status ON goal_runs(status);
CREATE INDEX IF NOT EXISTS idx_goal_events_run ON goal_events(goal_run_id);
CREATE INDEX IF NOT EXISTS idx_goal_events_created ON goal_events(created_at);
CREATE INDEX IF NOT EXISTS idx_runtime_registry_type ON runtime_registry(runtime_type);
CREATE INDEX IF NOT EXISTS idx_workspace_packs_name ON workspace_packs(name);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    decision_id TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    timestamp TEXT,
    room_id TEXT,
    room_name TEXT,
    task_id TEXT,
    goal_id TEXT,
    proposed_by TEXT,
    approved_by TEXT,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    reasoning TEXT NOT NULL DEFAULT '',
    options_considered TEXT NOT NULL DEFAULT '',
    selected_option TEXT,
    risk TEXT NOT NULL DEFAULT '',
    confidence INTEGER NULL,
    linked_runtime_ids_json TEXT NOT NULL DEFAULT '[]',
    linked_message_ids_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS decision_events (
    event_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(decision_id) REFERENCES decisions(decision_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS handoffs (
    id TEXT PRIMARY KEY,
    handoff_id TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    room_id TEXT,
    room_name TEXT,
    task_id TEXT,
    goal_id TEXT,
    from_agent TEXT,
    to_agent TEXT,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    open_questions TEXT NOT NULL DEFAULT '',
    risks TEXT NOT NULL DEFAULT '',
    recommended_next_step TEXT NOT NULL DEFAULT '',
    confidence INTEGER NULL,
    linked_message_ids_json TEXT NOT NULL DEFAULT '[]',
    linked_decision_ids_json TEXT NOT NULL DEFAULT '[]',
    accepted_at TEXT,
    rejected_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS handoff_events (
    id TEXT PRIMARY KEY,
    event_id TEXT UNIQUE,
    handoff_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(handoff_id) REFERENCES handoffs(handoff_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_decisions_room ON decisions(room_name);
CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_decision_events_decision ON decision_events(decision_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_room ON handoffs(room_name);
CREATE INDEX IF NOT EXISTS idx_handoffs_status ON handoffs(status);
CREATE INDEX IF NOT EXISTS idx_handoffs_agents ON handoffs(from_agent, to_agent);
CREATE INDEX IF NOT EXISTS idx_handoffs_created ON handoffs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_handoff_events_handoff ON handoff_events(handoff_id);
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
        runtime_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(runtime_registry)").fetchall()
        }
        runtime_additions = {
            "adapter_type": "TEXT NOT NULL DEFAULT 'unsupported'",
            "usage_risk": "TEXT NOT NULL DEFAULT 'medium'",
            "preferred_roles_json": "TEXT NOT NULL DEFAULT '[]'",
            "avoid_roles_json": "TEXT NOT NULL DEFAULT '[]'",
        }
        for column, definition in runtime_additions.items():
            if column not in runtime_columns:
                self._conn.execute(f"ALTER TABLE runtime_registry ADD COLUMN {column} {definition}")
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
            "cost_tier": "TEXT NOT NULL DEFAULT 'medium'",
            "usage_risk": "TEXT NOT NULL DEFAULT 'medium'",
            "preferred_roles_json": "TEXT NOT NULL DEFAULT '[]'",
            "avoid_roles_json": "TEXT NOT NULL DEFAULT '[]'",
            "capabilities_json": "TEXT NOT NULL DEFAULT '[]'",
            "speed": "INTEGER NOT NULL DEFAULT 5",
            "trust": "INTEGER NOT NULL DEFAULT 5",
        }
        for column, definition in agent_additions.items():
            if column not in agent_columns:
                self._conn.execute(f"ALTER TABLE agents ADD COLUMN {column} {definition}")
        memory_event_info = self._conn.execute("PRAGMA table_info(memory_events)").fetchall()
        memory_event_notnull = {row["name"]: bool(row["notnull"]) for row in memory_event_info}
        if memory_event_notnull.get("room_name") or memory_event_notnull.get("field_changed"):
            self._conn.executescript(
                """
                CREATE TABLE memory_events_new (
                    event_id TEXT PRIMARY KEY,
                    room_name TEXT,
                    memory_id TEXT,
                    event_type TEXT,
                    actor TEXT NOT NULL,
                    field_changed TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    details TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(room_name) REFERENCES rooms(name) ON DELETE CASCADE,
                    FOREIGN KEY(memory_id) REFERENCES shared_memory(memory_id) ON DELETE CASCADE
                );
                INSERT INTO memory_events_new (
                    event_id, room_name, memory_id, event_type, actor,
                    field_changed, old_value, new_value, details, created_at
                )
                SELECT
                    event_id, room_name, NULL, NULL, actor,
                    field_changed, old_value, new_value, NULL, created_at
                FROM memory_events;
                DROP TABLE memory_events;
                ALTER TABLE memory_events_new RENAME TO memory_events;
                CREATE INDEX IF NOT EXISTS idx_memory_events_room_name ON memory_events(room_name);
                CREATE INDEX IF NOT EXISTS idx_memory_events_memory_id ON memory_events(memory_id);
                CREATE INDEX IF NOT EXISTS idx_memory_events_created_at ON memory_events(created_at);
                """
            )
            memory_event_info = self._conn.execute("PRAGMA table_info(memory_events)").fetchall()
        memory_event_columns = {row["name"] for row in memory_event_info}
        memory_event_additions = {
            "memory_id": "TEXT",
            "event_type": "TEXT",
            "details": "TEXT",
        }
        for column, definition in memory_event_additions.items():
            if column not in memory_event_columns:
                self._conn.execute(f"ALTER TABLE memory_events ADD COLUMN {column} {definition}")
        shared_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(shared_memory)").fetchall()
        }
        shared_additions = {
            "token_cost_estimate": "INTEGER DEFAULT 0",
            "use_count": "INTEGER DEFAULT 0",
            "last_used_at": "TEXT",
        }
        for column, definition in shared_additions.items():
            if column not in shared_columns:
                self._conn.execute(f"ALTER TABLE shared_memory ADD COLUMN {column} {definition}")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_events_memory_id ON memory_events(memory_id)")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_registry (
                runtime_id TEXT PRIMARY KEY,
                runtime_type TEXT NOT NULL,
                adapter_type TEXT NOT NULL DEFAULT 'unsupported',
                version TEXT NOT NULL DEFAULT '',
                command_json TEXT NOT NULL DEFAULT '[]',
                working_dir TEXT NOT NULL DEFAULT '',
                timeout INTEGER NOT NULL DEFAULT 90,
                cost_profile TEXT NOT NULL DEFAULT 'medium',
                usage_risk TEXT NOT NULL DEFAULT 'medium',
                preferred_roles_json TEXT NOT NULL DEFAULT '[]',
                avoid_roles_json TEXT NOT NULL DEFAULT '[]',
                supported_modes_json TEXT NOT NULL DEFAULT '[]',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_packs (
                workspace_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                rooms_json TEXT NOT NULL DEFAULT '[]',
                agents_json TEXT NOT NULL DEFAULT '[]',
                memory_json TEXT NOT NULL DEFAULT '[]',
                skills_json TEXT NOT NULL DEFAULT '[]',
                goals_json TEXT NOT NULL DEFAULT '[]',
                repos_json TEXT NOT NULL DEFAULT '[]',
                governance_json TEXT NOT NULL DEFAULT '{}',
                runtime_refs_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._migrate_decision_schema()
        self._migrate_handoff_schema()

    def _migrate_decision_schema(self) -> None:
        columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(decisions)").fetchall()
        }
        additions = {
            "id": "TEXT",
            "decision_id": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "room_id": "TEXT",
            "room_name": "TEXT",
            "reason": "TEXT NOT NULL DEFAULT ''",
            "reasoning": "TEXT NOT NULL DEFAULT ''",
            "options_considered": "TEXT NOT NULL DEFAULT ''",
            "selected_option": "TEXT",
            "risk": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in columns:
                self._conn.execute(f"ALTER TABLE decisions ADD COLUMN {column} {definition}")
        self._conn.execute("UPDATE decisions SET id = decision_id WHERE (id IS NULL OR id = '') AND decision_id IS NOT NULL")
        self._conn.execute("UPDATE decisions SET decision_id = id WHERE (decision_id IS NULL OR decision_id = '') AND id IS NOT NULL")
        self._conn.execute("UPDATE decisions SET created_at = timestamp WHERE (created_at IS NULL OR created_at = '') AND timestamp IS NOT NULL")
        self._conn.execute("UPDATE decisions SET timestamp = created_at WHERE (timestamp IS NULL OR timestamp = '') AND created_at IS NOT NULL")
        self._conn.execute("UPDATE decisions SET updated_at = created_at WHERE (updated_at IS NULL OR updated_at = '') AND created_at IS NOT NULL")
        self._conn.execute("UPDATE decisions SET room_id = room_name WHERE (room_id IS NULL OR room_id = '') AND room_name IS NOT NULL")
        self._conn.execute("UPDATE decisions SET room_name = room_id WHERE (room_name IS NULL OR room_name = '') AND room_id IS NOT NULL")
        self._conn.execute("UPDATE decisions SET reason = reasoning WHERE reason = '' AND reasoning != ''")
        self._conn.execute("UPDATE decisions SET reasoning = reason WHERE reasoning = '' AND reason != ''")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_room_id ON decisions(room_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at DESC)")

    def _migrate_handoff_schema(self) -> None:
        columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(handoffs)").fetchall()
        }
        additions = {
            "id": "TEXT",
            "handoff_id": "TEXT",
            "updated_at": "TEXT",
            "room_id": "TEXT",
            "room_name": "TEXT",
            "task_id": "TEXT",
            "goal_id": "TEXT",
            "from_agent": "TEXT",
            "to_agent": "TEXT",
            "open_questions": "TEXT NOT NULL DEFAULT ''",
            "risks": "TEXT NOT NULL DEFAULT ''",
            "linked_message_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "linked_decision_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "accepted_at": "TEXT",
            "rejected_at": "TEXT",
            "completed_at": "TEXT",
        }
        for column, definition in additions.items():
            if column not in columns:
                self._conn.execute(f"ALTER TABLE handoffs ADD COLUMN {column} {definition}")
        self._conn.execute("UPDATE handoffs SET id = handoff_id WHERE (id IS NULL OR id = '') AND handoff_id IS NOT NULL")
        self._conn.execute("UPDATE handoffs SET handoff_id = id WHERE (handoff_id IS NULL OR handoff_id = '') AND id IS NOT NULL")
        self._conn.execute("UPDATE handoffs SET updated_at = created_at WHERE (updated_at IS NULL OR updated_at = '') AND created_at IS NOT NULL")
        self._conn.execute("UPDATE handoffs SET room_id = room_name WHERE (room_id IS NULL OR room_id = '') AND room_name IS NOT NULL")
        self._conn.execute("UPDATE handoffs SET room_name = room_id WHERE (room_name IS NULL OR room_name = '') AND room_id IS NOT NULL")
        if "open_questions_json" in columns:
            self._conn.execute("UPDATE handoffs SET open_questions = open_questions_json WHERE open_questions = '' AND open_questions_json != ''")
        if "risks_json" in columns:
            self._conn.execute("UPDATE handoffs SET risks = risks_json WHERE risks = '' AND risks_json != ''")
        event_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(handoff_events)").fetchall()
        }
        if "id" not in event_columns:
            self._conn.execute("ALTER TABLE handoff_events ADD COLUMN id TEXT")
        if "event_id" not in event_columns:
            self._conn.execute("ALTER TABLE handoff_events ADD COLUMN event_id TEXT")
        self._conn.execute("UPDATE handoff_events SET id = event_id WHERE (id IS NULL OR id = '') AND event_id IS NOT NULL")
        self._conn.execute("UPDATE handoff_events SET event_id = id WHERE (event_id IS NULL OR event_id = '') AND id IS NOT NULL")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_room_id ON handoffs(room_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_created_at ON handoffs(created_at DESC)")

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

    def save_delivery(
        self,
        message_id: str,
        reply: AdapterReply,
        created_at: str,
        attempts: int = 1,
        status: str | None = None,
        quality: str | None = None,
    ) -> None:
        delivery_status = status or ("acknowledged" if reply.ok else "failed")
        raw = dict(reply.raw or {})
        if quality:
            raw["quality"] = quality
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
                    delivery_status,
                    1 if reply.ok else 0,
                    reply.body or "",
                    reply.error,
                    reply.duration_ms,
                    reply.external_reference,
                    attempts,
                    json.dumps(raw, ensure_ascii=False),
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

    def _message_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        raw = data.pop("metadata_json", "{}") or "{}"
        try:
            data["metadata"] = json.loads(raw)
        except json.JSONDecodeError:
            data["metadata"] = {}
        return data

    def get_message(self, message_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return self._message_from_row(row) if row else None

    def list_messages_by_ids(self, message_ids: list[str]) -> list[dict]:
        ids = [message_id for message_id in dict.fromkeys(message_ids) if message_id]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *
                FROM messages
                WHERE message_id IN ({placeholders})
                ORDER BY timestamp ASC, message_id ASC
                """,
                ids,
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

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
            "messages": [self._message_from_row(row) for row in msg_rows],
            "deliveries": [dict(row) for row in del_rows],
            "dead_letters": [dict(row) for row in dead_rows],
        }

    def list_deliveries_for_messages(self, message_ids: list[str]) -> list[dict]:
        ids = [message_id for message_id in dict.fromkeys(message_ids) if message_id]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *
                FROM deliveries
                WHERE message_id IN ({placeholders})
                ORDER BY created_at ASC, delivery_id ASC
                """,
                ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_dead_letters_for_messages(self, message_ids: list[str]) -> list[dict]:
        ids = [message_id for message_id in dict.fromkeys(message_ids) if message_id]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *
                FROM dead_letters
                WHERE message_id IN ({placeholders})
                ORDER BY created_at ASC, dead_letter_id ASC
                """,
                ids,
            ).fetchall()
        return [dict(row) for row in rows]

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

    def latest_incident_anchor(self) -> dict | None:
        with self._lock:
            dead = self._conn.execute(
                """
                SELECT 'dead_letter' AS incident_type, dead_letter_id AS incident_id,
                       message_id, adapter_id, reason, created_at
                FROM dead_letters
                ORDER BY created_at DESC, dead_letter_id DESC
                LIMIT 1
                """
            ).fetchone()
            failed = self._conn.execute(
                """
                SELECT 'delivery' AS incident_type, delivery_id AS incident_id,
                       message_id, adapter_id, COALESCE(error, status) AS reason,
                       created_at
                FROM deliveries
                WHERE ok = 0 OR status IN ('failed', 'timeout', 'empty_reply')
                ORDER BY created_at DESC, delivery_id DESC
                LIMIT 1
                """
            ).fetchone()
        candidates = [dict(row) for row in (dead, failed) if row is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.get("created_at") or "", int(item.get("incident_id") or 0)))

    # ── flight summary ───────────────────────────────────────────────────

    def count_dead_letters(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS count FROM dead_letters").fetchone()
        return int(row["count"] if row else 0)

    def count_shared_memory(self, status: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS count FROM shared_memory"
        params: tuple = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return int(row["count"] if row else 0)

    # ── runtime registry ─────────────────────────────────────────────────

    def _runtime_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["command"] = json.loads(data.pop("command_json") or "[]")
        data["supported_modes"] = json.loads(data.pop("supported_modes_json") or "[]")
        data["capabilities"] = json.loads(data.pop("capabilities_json") or "[]")
        data["preferred_roles"] = json.loads(data.pop("preferred_roles_json") or "[]")
        data["avoid_roles"] = json.loads(data.pop("avoid_roles_json") or "[]")
        data["cost_tier"] = data.get("cost_profile") or "medium"
        data["enabled"] = bool(data.get("enabled"))
        return data

    def upsert_runtime(self, runtime: dict, updated_at: str | None = None) -> dict:
        runtime_id = str(runtime.get("runtime_id") or runtime.get("adapter_id") or "").strip()
        if not runtime_id:
            raise ValueError("runtime_id required")
        runtime_type = str(runtime.get("runtime_type") or runtime.get("type") or "unknown").strip() or "unknown"
        command = runtime.get("command") or []
        if isinstance(command, str):
            command = [command]
        supported_modes = runtime.get("supported_modes") or []
        capabilities = runtime.get("capabilities") or []
        preferred_roles = runtime.get("preferred_roles") or []
        avoid_roles = runtime.get("avoid_roles") or []
        cost_tier = str(runtime.get("cost_tier") or runtime.get("cost_profile") or "medium")
        usage_risk = str(runtime.get("usage_risk") or "medium")
        now = updated_at or utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO runtime_registry (
                    runtime_id, runtime_type, adapter_type, version, command_json, working_dir,
                    timeout, cost_profile, usage_risk, preferred_roles_json, avoid_roles_json,
                    supported_modes_json, capabilities_json, enabled, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runtime_id) DO UPDATE SET
                    runtime_type = excluded.runtime_type,
                    adapter_type = excluded.adapter_type,
                    version = excluded.version,
                    command_json = excluded.command_json,
                    working_dir = excluded.working_dir,
                    timeout = excluded.timeout,
                    cost_profile = excluded.cost_profile,
                    usage_risk = excluded.usage_risk,
                    preferred_roles_json = excluded.preferred_roles_json,
                    avoid_roles_json = excluded.avoid_roles_json,
                    supported_modes_json = excluded.supported_modes_json,
                    capabilities_json = excluded.capabilities_json,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    runtime_id,
                    runtime_type,
                    str(runtime.get("adapter_type") or runtime.get("type") or runtime_type),
                    str(runtime.get("version") or ""),
                    json.dumps([str(item) for item in command], ensure_ascii=False),
                    str(runtime.get("working_dir") or runtime.get("cwd") or ""),
                    int(runtime.get("timeout") or runtime.get("timeout_seconds") or 90),
                    cost_tier,
                    usage_risk,
                    json.dumps([str(item) for item in preferred_roles], ensure_ascii=False),
                    json.dumps([str(item) for item in avoid_roles], ensure_ascii=False),
                    json.dumps([str(item) for item in supported_modes], ensure_ascii=False),
                    json.dumps([str(item) for item in capabilities], ensure_ascii=False),
                    1 if runtime.get("enabled", True) else 0,
                    now,
                ),
            )
        item = self.get_runtime(runtime_id)
        assert item is not None
        return item

    def get_runtime(self, runtime_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runtime_registry WHERE runtime_id = ?", (runtime_id,)).fetchone()
        return self._runtime_from_row(row) if row else None

    def list_runtimes(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM runtime_registry ORDER BY runtime_id ASC").fetchall()
        return [self._runtime_from_row(row) for row in rows]

    # ── workspace packs ──────────────────────────────────────────────────

    def _workspace_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        for key in ("rooms", "agents", "memory", "skills", "goals", "repos", "runtime_refs"):
            data[key] = json.loads(data.pop(f"{key}_json") or "[]")
        data["governance"] = json.loads(data.pop("governance_json") or "{}")
        return data

    def upsert_workspace_pack(self, name: str, pack: dict | None = None, *, workspace_id: str | None = None) -> dict:
        now = utc_now_iso()
        pack = pack or {}
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO workspace_packs (
                    workspace_id, name, rooms_json, agents_json, memory_json,
                    skills_json, goals_json, repos_json, governance_json,
                    runtime_refs_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    rooms_json = excluded.rooms_json,
                    agents_json = excluded.agents_json,
                    memory_json = excluded.memory_json,
                    skills_json = excluded.skills_json,
                    goals_json = excluded.goals_json,
                    repos_json = excluded.repos_json,
                    governance_json = excluded.governance_json,
                    runtime_refs_json = excluded.runtime_refs_json,
                    updated_at = excluded.updated_at
                """,
                (
                    workspace_id or str(uuid.uuid4()),
                    name,
                    json.dumps(pack.get("rooms") or [], ensure_ascii=False),
                    json.dumps(pack.get("agents") or [], ensure_ascii=False),
                    json.dumps(pack.get("memory") or [], ensure_ascii=False),
                    json.dumps(pack.get("skills") or [], ensure_ascii=False),
                    json.dumps(pack.get("goals") or [], ensure_ascii=False),
                    json.dumps(pack.get("repos") or [], ensure_ascii=False),
                    json.dumps(pack.get("governance") or {}, ensure_ascii=False),
                    json.dumps(pack.get("runtime_refs") or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
        item = self.get_workspace_pack(name)
        assert item is not None
        return item

    def get_workspace_pack(self, name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM workspace_packs WHERE name = ?", (name,)).fetchone()
        return self._workspace_from_row(row) if row else None

    def list_workspace_packs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM workspace_packs ORDER BY updated_at DESC, name ASC").fetchall()
        return [self._workspace_from_row(row) for row in rows]

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

    # ── shared memory ─────────────────────────────────────────────────────

    def _memory_from_row(self, row: sqlite3.Row) -> dict:
        return dict(row)

    def _record_memory_event_locked(
        self,
        memory_id: str,
        event_type: str,
        actor: str | None,
        details: dict | str | None,
        created_at: str,
    ) -> None:
        if isinstance(details, dict):
            detail_text = json.dumps(details, ensure_ascii=False)
        else:
            detail_text = details
        self._conn.execute(
            """
            INSERT INTO memory_events (
                event_id, room_name, memory_id, event_type, actor,
                field_changed, old_value, new_value, details, created_at
            )
            SELECT ?, room_name, ?, ?, ?, NULL, NULL, NULL, ?, ?
            FROM shared_memory
            WHERE memory_id = ?
            """,
            (str(uuid.uuid4()), memory_id, event_type, actor or "system", detail_text, created_at, memory_id),
        )

    def record_shared_memory_event(
        self,
        memory_id: str,
        event_type: str,
        *,
        actor: str | None = None,
        details: dict | str | None = None,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM shared_memory WHERE memory_id = ?", (memory_id,)).fetchone() is None:
                return
            self._record_memory_event_locked(memory_id, event_type, actor, details, created_at or utc_now_iso())

    def find_duplicate_memory(self, content: str, *, room_name: str | None = None, workspace: str | None = None) -> dict | None:
        normalized = " ".join(str(content or "").split()).lower()
        if not normalized:
            return None
        like = f"%{normalized}%"
        clauses = ["LOWER(content) = ? OR LOWER(content) LIKE ?"]
        params: list[object] = [normalized, like]
        if room_name is not None:
            clauses.append("(room_name = ? OR room_name IS NULL)")
            params.append(room_name)
        if workspace is not None:
            clauses.append("(workspace = ? OR workspace IS NULL)")
            params.append(workspace)
        sql = f"""
            SELECT *
            FROM shared_memory
            WHERE status != 'archived' AND ({') AND ('.join(clauses)})
            ORDER BY created_at DESC
            LIMIT 1
        """
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return self._memory_from_row(row) if row else None

    def create_shared_memory(
        self,
        *,
        memory_id: str,
        room_name: str | None,
        workspace: str | None,
        memory_type: str,
        content: str,
        status: str,
        confidence: int,
        created_by: str | None,
        created_at: str,
        source_team_run_id: str | None = None,
        source_task_id: str | None = None,
        source_message_id: str | None = None,
    ) -> dict:
        if memory_type not in SHARED_MEMORY_TYPES:
            raise ValueError(f"invalid memory_type: {memory_type}")
        if status not in SHARED_MEMORY_STATUSES:
            raise ValueError(f"invalid memory status: {status}")
        token_cost = max(1, len(content) // 4) if content else 0
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO shared_memory (
                    memory_id, room_name, workspace, memory_type, content, status,
                    confidence, created_by, created_at, source_team_run_id,
                    source_task_id, source_message_id, token_cost_estimate,
                    use_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    memory_id,
                    room_name,
                    workspace,
                    memory_type,
                    content,
                    status,
                    int(confidence),
                    created_by,
                    created_at,
                    source_team_run_id,
                    source_task_id,
                    source_message_id,
                    token_cost,
                ),
            )
            self._record_memory_event_locked(
                memory_id,
                "memory_proposed",
                created_by,
                {"memory_type": memory_type, "status": status, "confidence": int(confidence)},
                created_at,
            )
        memory = self.get_shared_memory(memory_id)
        assert memory is not None
        return memory

    def get_shared_memory(self, memory_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM shared_memory WHERE memory_id = ?", (memory_id,)).fetchone()
        return self._memory_from_row(row) if row else None

    def list_shared_memory(
        self,
        *,
        status: str | None = None,
        room_name: str | None = None,
        workspace: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if room_name is not None:
            clauses.append("room_name = ?")
            params.append(room_name)
        if workspace is not None:
            clauses.append("workspace = ?")
            params.append(workspace)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *
                FROM shared_memory
                {where}
                ORDER BY created_at DESC, memory_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def search_shared_memory(self, query: str, *, limit: int = 50) -> list[dict]:
        term = f"%{str(query or '').strip().lower()}%"
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM shared_memory
                WHERE LOWER(content) LIKE ?
                   OR LOWER(memory_type) LIKE ?
                   OR LOWER(COALESCE(room_name, '')) LIKE ?
                   OR LOWER(COALESCE(workspace, '')) LIKE ?
                ORDER BY
                  CASE status WHEN 'peer_approved' THEN 0 WHEN 'proposed' THEN 1 ELSE 2 END,
                  created_at DESC
                LIMIT ?
                """,
                (term, term, term, term, limit),
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def update_shared_memory(self, memory_id: str, fields: dict, *, actor: str, event_type: str) -> dict | None:
        if not fields:
            return self.get_shared_memory(memory_id)
        allowed = {
            "room_name", "workspace", "memory_type", "content", "status", "confidence",
            "reviewed_by", "review_result", "review_reason", "reviewed_at",
            "approved_by", "approved_at", "source_team_run_id", "source_task_id",
            "source_message_id", "token_cost_estimate", "use_count", "last_used_at",
        }
        clean = {key: value for key, value in fields.items() if key in allowed}
        if "memory_type" in clean and clean["memory_type"] not in SHARED_MEMORY_TYPES:
            raise ValueError(f"invalid memory_type: {clean['memory_type']}")
        if "status" in clean and clean["status"] not in SHARED_MEMORY_STATUSES:
            raise ValueError(f"invalid memory status: {clean['status']}")
        if "content" in clean:
            clean["token_cost_estimate"] = max(1, len(str(clean["content"])) // 4) if clean["content"] else 0
        if not clean:
            return self.get_shared_memory(memory_id)
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE shared_memory SET {assignments} WHERE memory_id = ?",
                [*clean.values(), memory_id],
            )
            if cur.rowcount == 0:
                return None
            self._record_memory_event_locked(memory_id, event_type, actor, clean, utc_now_iso())
        return self.get_shared_memory(memory_id)

    def list_shared_memory_events(self, memory_id: str | None = None, limit: int = 100) -> list[dict] | None:
        if memory_id and self.get_shared_memory(memory_id) is None:
            return None
        params: list[object] = []
        where = "WHERE memory_id IS NOT NULL"
        if memory_id:
            where += " AND memory_id = ?"
            params.append(memory_id)
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT event_id, memory_id, event_type, actor, details, created_at
                FROM memory_events
                {where}
                ORDER BY created_at ASC, rowid ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def select_shared_memory_for_injection(
        self,
        *,
        room_name: str | None,
        workspace: str | None,
        max_items: int,
        max_chars: int,
        min_confidence: int,
    ) -> list[dict]:
        clauses = ["status = 'peer_approved'", "confidence >= ?"]
        params: list[object] = [int(min_confidence)]
        if room_name:
            clauses.append("(room_name = ? OR room_name IS NULL)")
            params.append(room_name)
        else:
            clauses.append("room_name IS NULL")
        if workspace:
            clauses.append("(workspace = ? OR workspace IS NULL)")
            params.append(workspace)
        else:
            clauses.append("workspace IS NULL")
        params.append(max(max_items * 4, max_items))
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *,
                  CASE WHEN room_name = ? THEN 0 WHEN workspace = ? THEN 1 ELSE 2 END AS scope_rank
                FROM shared_memory
                WHERE {' AND '.join(clauses)}
                ORDER BY scope_rank ASC, COALESCE(last_used_at, approved_at, created_at) DESC, created_at DESC
                LIMIT ?
                """,
                [room_name, workspace, *params],
            ).fetchall()
        selected: list[dict] = []
        used_chars = 0
        for row in rows:
            memory = self._memory_from_row(row)
            line_len = len(f"- {memory.get('memory_type')}: {memory.get('content')}")
            if selected and used_chars + line_len > max_chars:
                continue
            if line_len > max_chars:
                continue
            selected.append(memory)
            used_chars += line_len
            if len(selected) >= max_items:
                break
        return selected

    def mark_shared_memory_used(self, memory_ids: list[str], *, actor: str = "synkraken") -> None:
        now = utc_now_iso()
        with self._lock, self._conn:
            for memory_id in memory_ids:
                cur = self._conn.execute(
                    """
                    UPDATE shared_memory
                    SET use_count = COALESCE(use_count, 0) + 1,
                        last_used_at = ?
                    WHERE memory_id = ?
                    """,
                    (now, memory_id),
                )
                if cur.rowcount:
                    self._record_memory_event_locked(memory_id, "memory_used", actor, None, now)

    def _normalize_agent_profile(self, fields: dict) -> dict:
        clean: dict[str, object] = {}
        if "cost_tier" in fields:
            cost_tier = str(fields.get("cost_tier") or "medium").strip().lower()
            if cost_tier not in AGENT_COST_TIERS:
                raise ValueError(f"invalid cost_tier: {cost_tier}")
            clean["cost_tier"] = cost_tier
        if "usage_risk" in fields:
            usage_risk = str(fields.get("usage_risk") or "medium").strip().lower()
            if usage_risk not in USAGE_RISKS:
                raise ValueError(f"invalid usage_risk: {usage_risk}")
            clean["usage_risk"] = usage_risk
        for field_name, column_name in (
            ("preferred_roles", "preferred_roles_json"),
            ("avoid_roles", "avoid_roles_json"),
        ):
            if field_name not in fields:
                continue
            roles = fields.get(field_name) or []
            if not isinstance(roles, list):
                raise ValueError(f"{field_name} must be a list")
            normalized_roles = []
            for role in roles:
                role_text = str(role).strip().lower()
                if not role_text:
                    continue
                if role_text not in AGENT_PROFILE_ROLES:
                    raise ValueError(f"invalid {field_name} role: {role_text}")
                if role_text not in normalized_roles:
                    normalized_roles.append(role_text)
            clean[column_name] = json.dumps(normalized_roles, ensure_ascii=False)
        if "capabilities" in fields:
            capabilities = fields.get("capabilities") or []
            if not isinstance(capabilities, list):
                raise ValueError("capabilities must be a list")
            normalized_caps = []
            for capability in capabilities:
                cap_text = " ".join(str(capability).strip().lower().split())
                if cap_text and cap_text not in normalized_caps:
                    normalized_caps.append(cap_text)
            clean["capabilities_json"] = json.dumps(normalized_caps, ensure_ascii=False)
        for key in ("speed", "trust"):
            if key in fields:
                value = int(fields.get(key))
                if value < 1 or value > 10:
                    raise ValueError(f"{key} must be between 1 and 10")
                clean[key] = value
        return clean

    def _agent_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        try:
            data["preferred_roles"] = json.loads(data.pop("preferred_roles_json") or "[]")
        except Exception:
            data["preferred_roles"] = []
        try:
            data["avoid_roles"] = json.loads(data.pop("avoid_roles_json") or "[]")
        except Exception:
            data["avoid_roles"] = []
        try:
            data["capabilities"] = json.loads(data.pop("capabilities_json") or "[]")
        except Exception:
            data["capabilities"] = []
        data["speed"] = int(data.get("speed") or 5)
        data["trust"] = int(data.get("trust") or 5)
        return data

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
                    profile = self._normalize_agent_profile({
                        key: agent[key]
                        for key in ("cost_tier", "usage_risk", "preferred_roles", "avoid_roles", "capabilities", "speed", "trust")
                        if key in agent
                    })
                    self._conn.execute(
                        """
                        INSERT INTO agents (
                            adapter_id, runtime_name, adapter_type, enabled,
                            status, last_seen_at, runtime, cost_tier, usage_risk,
                            preferred_roles_json, avoid_roles_json, capabilities_json, speed, trust
                        ) VALUES (?, ?, ?, ?, 'configured', NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            adapter_id,
                            agent.get("runtime_name") or adapter_id,
                            agent.get("type") or "unknown",
                            1 if enabled else 0,
                            runtime,
                            profile.get("cost_tier", "medium"),
                            profile.get("usage_risk", "medium"),
                            profile.get("preferred_roles_json", "[]"),
                            profile.get("avoid_roles_json", "[]"),
                            profile.get("capabilities_json", "[]"),
                            profile.get("speed", 5),
                            profile.get("trust", 5),
                        ),
                    )
                    current = {"status": "configured"}
                else:
                    profile = self._normalize_agent_profile({
                        key: agent[key]
                        for key in ("cost_tier", "usage_risk", "preferred_roles", "avoid_roles", "capabilities", "speed", "trust")
                        if key in agent
                    })
                    assignments = ["runtime_name = ?", "adapter_type = ?", "enabled = ?", "runtime = ?"]
                    values: list[object] = [
                        agent.get("runtime_name") or adapter_id,
                        agent.get("type") or "unknown",
                        1 if enabled else 0,
                        runtime,
                    ]
                    for key, value in profile.items():
                        assignments.append(f"{key} = ?")
                        values.append(value)
                    values.append(adapter_id)
                    self._conn.execute(
                        """
                        UPDATE agents SET
                        """ + ", ".join(assignments) + """
                        WHERE adapter_id = ?
                        """,
                        values,
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
                       current_room, last_message_at, cost_tier, usage_risk,
                       preferred_roles_json, avoid_roles_json, capabilities_json, speed, trust
                FROM agents
                ORDER BY adapter_id ASC
                """
            ).fetchall()
        return [self._agent_from_row(row) for row in rows]

    def get_agent(self, adapter_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT adapter_id, adapter_id AS agent_id, runtime_name, adapter_type AS type, enabled,
                       status, last_seen_at, runtime, current_task_id,
                       current_room, last_message_at, cost_tier, usage_risk,
                       preferred_roles_json, avoid_roles_json, capabilities_json, speed, trust
                FROM agents
                WHERE adapter_id = ?
                """,
                (adapter_id,),
            ).fetchone()
        return self._agent_from_row(row) if row else None

    def update_agent_profile(self, adapter_id: str, fields: dict, actor: str = "operator") -> dict | None:
        clean = self._normalize_agent_profile(fields)
        if not clean:
            return self.get_agent(adapter_id)
        with self._lock, self._conn:
            before = self._conn.execute("SELECT * FROM agents WHERE adapter_id = ?", (adapter_id,)).fetchone()
            if before is None:
                return None
            assignments = ", ".join(f"{key} = ?" for key in clean)
            cur = self._conn.execute(
                f"UPDATE agents SET {assignments}, last_seen_at = ? WHERE adapter_id = ?",
                [*clean.values(), utc_now_iso(), adapter_id],
            )
            if cur.rowcount == 0:
                return None
            self._save_agent_event(
                adapter_id,
                "profile_updated",
                json.dumps(self._agent_from_row(before), ensure_ascii=False),
                json.dumps(fields, ensure_ascii=False),
                utc_now_iso(),
            )
        return self.get_agent(adapter_id)

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
                       message_type, subject, priority, reply_to, hop_count, body, metadata_json
                FROM (
                    SELECT message_id, conversation_id, source, target, timestamp,
                           message_type, subject, priority, reply_to, hop_count, body, metadata_json
                    FROM messages
                    WHERE target = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                ORDER BY timestamp ASC
                """,
                (target, limit),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

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

    # ── goal mode ─────────────────────────────────────────────────────────

    def _goal_run_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["reviewers"] = json.loads(data.get("reviewers") or "[]")
        data["participants"] = json.loads(data.get("participants") or "[]")
        data["linked_team_run_ids"] = json.loads(data.get("linked_team_run_ids") or "[]")
        return data

    def create_goal_run(
        self,
        *,
        goal_run_id: str,
        room_name: str,
        source_goal: str,
        status: str,
        threshold: int,
        max_rounds: int,
        current_round: int,
        participants: list[str],
        token_budget_chars: int,
        linked_task_id: str | None,
        started_at: str,
        created_by: str,
    ) -> dict:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO goal_runs (
                    goal_run_id, room_name, source_goal, status, threshold,
                    max_rounds, current_round, owner_agent, reviewers,
                    participants, token_police_agent, guardrail_agent,
                    success_criteria, latest_score, final_report,
                    token_budget_chars, estimated_context_chars,
                    guardrail_status, linked_task_id, linked_team_run_ids,
                    started_at, completed_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, '[]', ?, NULL, NULL, '', 0, '', ?, 0, '', ?, '[]', ?, NULL, ?)
                """,
                (
                    goal_run_id,
                    room_name,
                    source_goal,
                    status,
                    threshold,
                    max_rounds,
                    current_round,
                    json.dumps(participants, ensure_ascii=False),
                    token_budget_chars,
                    linked_task_id,
                    started_at,
                    created_by,
                ),
            )
        run = self.get_goal_run(goal_run_id)
        assert run is not None
        return run

    def update_goal_run(self, goal_run_id: str, fields: dict) -> dict | None:
        if not fields:
            return self.get_goal_run(goal_run_id)
        clean: dict[str, object] = {}
        allowed = {
            "room_name", "source_goal", "status", "threshold", "max_rounds",
            "current_round", "owner_agent", "reviewers", "participants",
            "token_police_agent", "guardrail_agent", "success_criteria",
            "latest_score", "final_report", "token_budget_chars",
            "estimated_context_chars", "guardrail_status", "linked_task_id",
            "linked_team_run_ids", "started_at", "completed_at", "created_by",
        }
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"reviewers", "participants", "linked_team_run_ids"}:
                clean[key] = json.dumps(value or [], ensure_ascii=False)
            else:
                clean[key] = value
        if not clean:
            return self.get_goal_run(goal_run_id)
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE goal_runs SET {assignments} WHERE goal_run_id = ?",
                [*clean.values(), goal_run_id],
            )
            if cur.rowcount == 0:
                return None
        return self.get_goal_run(goal_run_id)

    def get_goal_run(self, goal_run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM goal_runs WHERE goal_run_id = ?",
                (goal_run_id,),
            ).fetchone()
        return self._goal_run_from_row(row) if row else None

    def list_goal_runs(self, room_name: str | None = None, limit: int = 25) -> list[dict]:
        sql = "SELECT * FROM goal_runs"
        params: list[object] = []
        if room_name:
            sql += " WHERE room_name = ?"
            params.append(room_name)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._goal_run_from_row(row) for row in rows]

    def record_goal_event(
        self,
        goal_run_id: str,
        event_type: str,
        *,
        actor: str | None = None,
        details: str | dict | None = None,
        created_at: str | None = None,
    ) -> None:
        if isinstance(details, dict):
            detail_text = json.dumps(details, ensure_ascii=False)
        else:
            detail_text = details
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM goal_runs WHERE goal_run_id = ?", (goal_run_id,)).fetchone() is None:
                return
            self._conn.execute(
                """
                INSERT INTO goal_events (event_id, goal_run_id, event_type, actor, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), goal_run_id, event_type, actor, detail_text, created_at or utc_now_iso()),
            )

    def list_goal_events(self, goal_run_id: str, limit: int = 200) -> list[dict] | None:
        if self.get_goal_run(goal_run_id) is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, goal_run_id, event_type, actor, details, created_at
                FROM goal_events
                WHERE goal_run_id = ?
                ORDER BY created_at ASC, rowid ASC
                LIMIT ?
                """,
                (goal_run_id, limit),
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

    # ── decisions ────────────────────────────────────────────────────────

    def _decision_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        decision_id = data.get("id") or data.get("decision_id")
        created_at = data.get("created_at") or data.get("timestamp")
        room_id = data.get("room_id") or data.get("room_name")
        reason = data.get("reason") or data.get("reasoning") or ""
        data["id"] = decision_id
        data["decision_id"] = decision_id
        data["created_at"] = created_at
        data["updated_at"] = data.get("updated_at") or created_at
        data["timestamp"] = created_at
        data["room_id"] = room_id
        data["room_name"] = room_id
        data["reason"] = reason
        data["reasoning"] = reason
        data["linked_runtime_ids"] = json.loads(data.pop("linked_runtime_ids_json") or "[]")
        data["linked_message_ids"] = json.loads(data.pop("linked_message_ids_json") or "[]")
        return data

    def create_decision(
        self,
        *,
        title: str,
        summary: str = "",
        linked_runtime_ids: list[str] | None = None,
        linked_message_ids: list[str] | None = None,
        decision_id: str | None = None,
        id: str | None = None,
        room_id: str | None = None,
        room_name: str | None = None,
        task_id: str | None = None,
        goal_id: str | None = None,
        proposed_by: str | None = None,
        reason: str = "",
        reasoning: str = "",
        options_considered: str = "",
        selected_option: str | None = None,
        risk: str = "",
        confidence: int | None = None,
        created_at: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        record_id = id or decision_id or str(uuid.uuid4())
        now = created_at or timestamp or utc_now_iso()
        room = room_id or room_name
        rationale = reason or reasoning
        if confidence is not None:
            confidence = max(0, min(100, int(confidence)))
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO decisions (
                    id, decision_id, created_at, updated_at, timestamp, room_id, room_name,
                    task_id, goal_id, proposed_by, approved_by, status, title, summary,
                    reason, reasoning, options_considered, selected_option, risk, confidence,
                    linked_runtime_ids_json, linked_message_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id, record_id, now, now, now, room, room, task_id, goal_id, proposed_by,
                    title, summary, rationale, rationale, options_considered, selected_option,
                    risk, confidence,
                    json.dumps(linked_runtime_ids or [], ensure_ascii=False),
                    json.dumps(linked_message_ids or [], ensure_ascii=False),
                ),
            )
        decision = self.get_decision(record_id)
        assert decision is not None
        return decision

    def get_decision(self, decision_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM decisions WHERE id = ? OR decision_id = ?",
                (decision_id, decision_id),
            ).fetchone()
        return self._decision_from_row(row) if row else None

    def list_decisions(
        self,
        room_id: str | None = None,
        room_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        room = room_id or room_name
        if room is not None:
            clauses.append("(room_id = ? OR room_name = ?)")
            params.extend([room, room])
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM decisions {where} ORDER BY COALESCE(created_at, timestamp) DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._decision_from_row(row) for row in rows]

    def latest_decision(self, room_id: str | None = None, status: str | None = None) -> dict | None:
        decisions = self.list_decisions(room_id=room_id, status=status, limit=1)
        return decisions[0] if decisions else None

    def update_decision(self, decision_id: str, fields: dict) -> dict | None:
        if not fields:
            return self.get_decision(decision_id)
        allowed = {
            "room_id", "room_name", "task_id", "goal_id", "approved_by", "status",
            "title", "summary", "reason", "reasoning", "options_considered", "selected_option",
            "risk", "confidence", "linked_runtime_ids", "linked_message_ids",
        }
        clean: dict[str, object] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in ("linked_runtime_ids", "linked_message_ids"):
                clean[f"{key}_json"] = json.dumps(value or [], ensure_ascii=False)
            elif key in {"room_id", "room_name"}:
                clean["room_id"] = value
                clean["room_name"] = value
            elif key in {"reason", "reasoning"}:
                clean["reason"] = value
                clean["reasoning"] = value
            else:
                clean[key] = value
        if not clean:
            return self.get_decision(decision_id)
        clean["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE decisions SET {assignments} WHERE id = ? OR decision_id = ?",
                [*clean.values(), decision_id, decision_id],
            )
            if cur.rowcount == 0:
                return None
        return self.get_decision(decision_id)

    def approve_decision(self, decision_id: str, actor: str, created_at: str | None = None) -> dict | None:
        decision = self.get_decision(decision_id)
        if decision is None:
            return None
        now = created_at or utc_now_iso()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                UPDATE decisions
                SET status = 'approved', approved_by = ?, updated_at = ?
                WHERE id = ? OR decision_id = ?
                """,
                (actor, now, decision_id, decision_id),
            )
            if cur.rowcount == 0:
                return None
            self._append_decision_event_locked(
                decision["id"], "approved", actor,
                {"old_status": decision.get("status"), "new_status": "approved"}, now,
            )
        return self.get_decision(decision_id)

    def reject_decision(
        self,
        decision_id: str,
        actor: str,
        *,
        reason: str | None = None,
        created_at: str | None = None,
    ) -> dict | None:
        decision = self.get_decision(decision_id)
        if decision is None:
            return None
        now = created_at or utc_now_iso()
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                UPDATE decisions
                SET status = 'rejected', approved_by = ?, updated_at = ?
                WHERE id = ? OR decision_id = ?
                """,
                (actor, now, decision_id, decision_id),
            )
            if cur.rowcount == 0:
                return None
            self._append_decision_event_locked(
                decision["id"], "rejected", actor,
                {"old_status": decision.get("status"), "new_status": "rejected", "reason": reason or ""}, now,
            )
        return self.get_decision(decision_id)

    def _append_decision_event_locked(
        self,
        decision_id: str,
        event_type: str,
        actor: str | None,
        details: dict | str | None,
        created_at: str,
    ) -> None:
        detail_text = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
        self._conn.execute(
            """
            INSERT INTO decision_events (event_id, decision_id, event_type, actor, old_value, new_value, details, created_at)
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (str(uuid.uuid4()), decision_id, event_type, actor or "system", detail_text, created_at),
        )

    def append_decision_event(
        self,
        decision_id: str,
        event_type: str,
        actor: str | None = None,
        details: dict | str | None = None,
        created_at: str | None = None,
    ) -> None:
        decision = self.get_decision(decision_id)
        if decision is None:
            return
        with self._lock, self._conn:
            self._append_decision_event_locked(decision["id"], event_type, actor, details, created_at or utc_now_iso())

    def record_decision_event(
        self,
        decision_id: str,
        event_type: str,
        actor: str,
        old_value: str | None,
        new_value: str | None,
        details: str | None,
        created_at: str,
    ) -> None:
        detail = details
        if old_value is not None or new_value is not None:
            detail = {"old_value": old_value, "new_value": new_value, "details": details}
        self.append_decision_event(decision_id, event_type, actor, detail, created_at)

    def list_decision_events(self, decision_id: str) -> list[dict] | None:
        decision = self.get_decision(decision_id)
        if decision is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, decision_id, event_type, actor, old_value, new_value, details, created_at
                FROM decision_events
                WHERE decision_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (decision["id"],),
            ).fetchall()
        return [dict(row) for row in rows]

    # ── handoffs ──────────────────────────────────────────────────────────

    def _handoff_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        handoff_id = data.get("id") or data.get("handoff_id")
        room_id = data.get("room_id") or data.get("room_name")
        data["id"] = handoff_id
        data["handoff_id"] = handoff_id
        data["room_id"] = room_id
        data["room_name"] = room_id
        open_questions_raw = data.get("open_questions") or data.pop("open_questions_json", "") or "[]"
        risks_raw = data.get("risks") or data.pop("risks_json", "") or "[]"
        data["open_questions"] = json.loads(open_questions_raw) if open_questions_raw.startswith("[") else open_questions_raw
        data["risks"] = json.loads(risks_raw) if risks_raw.startswith("[") else risks_raw
        data["linked_message_ids"] = json.loads(data.pop("linked_message_ids_json", "[]") or "[]")
        data["linked_decision_ids"] = json.loads(data.pop("linked_decision_ids_json", "[]") or "[]")
        return data

    def create_handoff(
        self,
        *,
        handoff_id: str | None = None,
        id: str | None = None,
        from_agent: str | None = None,
        to_agent: str | None = None,
        task_id: str | None = None,
        room_id: str | None = None,
        room_name: str | None = None,
        goal_id: str | None = None,
        summary: str,
        open_questions: list[str] | str | None = None,
        risks: list[str] | str | None = None,
        recommended_next_step: str = "",
        confidence: int | None = None,
        linked_message_ids: list[str] | None = None,
        linked_decision_ids: list[str] | None = None,
        created_at: str | None = None,
    ) -> dict:
        record_id = id or handoff_id or str(uuid.uuid4())
        now = created_at or utc_now_iso()
        room = room_id or room_name
        questions_text = (
            open_questions
            if isinstance(open_questions, str)
            else json.dumps(open_questions or [], ensure_ascii=False)
        )
        risks_text = risks if isinstance(risks, str) else json.dumps(risks or [], ensure_ascii=False)
        if confidence is not None:
            confidence = max(0, min(100, int(confidence)))
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO handoffs (
                    id, handoff_id, created_at, updated_at, room_id, room_name, task_id,
                    goal_id, from_agent, to_agent, status, summary, open_questions, risks,
                    recommended_next_step, confidence, linked_message_ids_json,
                    linked_decision_ids_json, accepted_at, rejected_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    record_id, record_id, now, now, room, room, task_id, goal_id,
                    from_agent, to_agent, summary, questions_text, risks_text,
                    recommended_next_step, confidence,
                    json.dumps(linked_message_ids or [], ensure_ascii=False),
                    json.dumps(linked_decision_ids or [], ensure_ascii=False),
                ),
            )
        handoff = self.get_handoff(record_id)
        assert handoff is not None
        return handoff

    def get_handoff(self, handoff_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM handoffs WHERE id = ? OR handoff_id = ?",
                (handoff_id, handoff_id),
            ).fetchone()
        return self._handoff_from_row(row) if row else None

    def list_handoffs(
        self,
        room_id: str | None = None,
        room_name: str | None = None,
        status: str | None = None,
        agent: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        room = room_id or room_name
        if room is not None:
            clauses.append("(room_id = ? OR room_name = ?)")
            params.extend([room, room])
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if agent is not None:
            clauses.append("(from_agent = ? OR to_agent = ?)")
            params.extend([agent, agent])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM handoffs {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._handoff_from_row(row) for row in rows]

    def update_handoff(self, handoff_id: str, fields: dict) -> dict | None:
        if not fields:
            return self.get_handoff(handoff_id)
        allowed = {
            "from_agent", "to_agent", "task_id", "room_id", "room_name", "goal_id",
            "summary", "open_questions", "risks", "recommended_next_step", "confidence",
            "status", "linked_message_ids", "linked_decision_ids", "accepted_at",
            "rejected_at", "completed_at",
        }
        clean: dict[str, object] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in ("open_questions", "risks"):
                clean[key] = value if isinstance(value, str) else json.dumps(value or [], ensure_ascii=False)
            elif key in ("linked_message_ids", "linked_decision_ids"):
                clean[f"{key}_json"] = json.dumps(value or [], ensure_ascii=False)
            elif key in {"room_id", "room_name"}:
                clean["room_id"] = value
                clean["room_name"] = value
            else:
                clean[key] = value
        if not clean:
            return self.get_handoff(handoff_id)
        clean["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE handoffs SET {assignments} WHERE id = ? OR handoff_id = ?",
                [*clean.values(), handoff_id, handoff_id],
            )
            if cur.rowcount == 0:
                return None
        return self.get_handoff(handoff_id)

    def latest_handoff(self, room_id: str | None = None, status: str | None = None) -> dict | None:
        handoffs = self.list_handoffs(room_id=room_id, status=status, limit=1)
        return handoffs[0] if handoffs else None

    def accept_handoff(self, handoff_id: str, actor: str, created_at: str | None = None) -> dict | None:
        handoff = self.get_handoff(handoff_id)
        if handoff is None:
            return None
        now = created_at or utc_now_iso()
        updated = self.update_handoff(handoff_id, {"status": "accepted", "accepted_at": now})
        self.append_handoff_event(
            handoff_id, "accepted", actor,
            {"old_status": handoff.get("status"), "new_status": "accepted"}, now,
        )
        return updated

    def reject_handoff(
        self,
        handoff_id: str,
        actor: str,
        *,
        reason: str | None = None,
        created_at: str | None = None,
    ) -> dict | None:
        handoff = self.get_handoff(handoff_id)
        if handoff is None:
            return None
        now = created_at or utc_now_iso()
        updated = self.update_handoff(handoff_id, {"status": "rejected", "rejected_at": now})
        self.append_handoff_event(
            handoff_id, "rejected", actor,
            {"old_status": handoff.get("status"), "new_status": "rejected", "reason": reason or ""}, now,
        )
        return updated

    def complete_handoff(self, handoff_id: str, actor: str, created_at: str | None = None) -> dict | None:
        handoff = self.get_handoff(handoff_id)
        if handoff is None:
            return None
        now = created_at or utc_now_iso()
        updated = self.update_handoff(handoff_id, {"status": "completed", "completed_at": now})
        self.append_handoff_event(
            handoff_id, "completed", actor,
            {"old_status": handoff.get("status"), "new_status": "completed"}, now,
        )
        return updated

    def record_handoff_event(
        self,
        handoff_id: str,
        event_type: str,
        actor: str | None,
        details: str | None,
        created_at: str,
    ) -> None:
        self.append_handoff_event(handoff_id, event_type, actor, details, created_at)

    def append_handoff_event(
        self,
        handoff_id: str,
        event_type: str,
        actor: str | None = None,
        details: dict | str | None = None,
        created_at: str | None = None,
    ) -> None:
        handoff = self.get_handoff(handoff_id)
        if handoff is None:
            return
        event_id = str(uuid.uuid4())
        detail_text = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO handoff_events (id, event_id, handoff_id, event_type, actor, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, event_id, handoff["id"], event_type, actor or "system", detail_text, created_at or utc_now_iso()),
            )

    def list_handoff_events(self, handoff_id: str) -> list[dict] | None:
        handoff = self.get_handoff(handoff_id)
        if handoff is None:
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, handoff_id, event_type, actor, details, created_at
                FROM handoff_events
                WHERE handoff_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (handoff["id"],),
            ).fetchall()
        return [dict(row) for row in rows]
