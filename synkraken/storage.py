from __future__ import annotations

from datetime import datetime, timezone
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
SHARED_MEMORY_STATUSES = {"proposed", "approved", "peer_approved", "rejected", "archived"}
DECISION_STATUSES = {"proposed", "approved", "rejected", "superseded"}
HANDOFF_STATUSES = {"pending", "accepted", "rejected", "completed"}
PROPOSAL_STATUSES = {"proposed", "approved", "rejected", "executed", "expired", "cancelled"}
MISSION_STATUSES = {"proposed", "active", "blocked", "review", "completed", "cancelled"}
MISSION_PRIORITIES = {"low", "medium", "high", "critical"}
OUTCOME_STATUSES = {"not_started", "in_progress", "review", "completed", "blocked", "cancelled"}
OUTCOME_CONFIDENCE = {"low", "medium", "high"}
ASSIGNMENT_STATUSES = {"assigned", "in_progress", "waiting", "blocked", "handoff", "review", "completed", "cancelled"}
PROPOSAL_TYPES = {
    "shell", "git", "restart", "delete", "write", "replay", "retry",
    "memory_promotion", "room_summary_promotion", "file_write", "delete_file",
    "room_summarize",
}
RUNTIME_HEALTH_STATUSES = {"healthy", "degraded", "unstable", "failing"}
RUNTIME_REPUTATION_RECENT_WINDOW = 100
RUNTIME_REPUTATION_MIN_SAMPLE_SIZE = 5
LEGACY_SHARED_MEMORY_TYPES = {
    "fact", "decision", "preference", "rule", "lesson", "technical_note", "project_context",
}
SHARED_MEMORY_TYPES = {
    *LEGACY_SHARED_MEMORY_TYPES,
    "operator_note", "room_summary", "decision_memory", "handoff_memory",
    "mission_context", "outcome_context", "assignment_context", "runtime_observation",
}
SHARED_MEMORY_IMPORTANCE = {"low", "medium", "high", "critical"}
SHARED_MEMORY_SCOPES = {"global", "room", "mission", "outcome", "assignment", "runtime"}

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

CREATE TABLE IF NOT EXISTS runtime_reputation (
    runtime_id TEXT PRIMARY KEY,
    total_deliveries INTEGER NOT NULL DEFAULT 0,
    successful_replies INTEGER NOT NULL DEFAULT 0,
    empty_replies INTEGER NOT NULL DEFAULT 0,
    timeouts INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    wrong_identity INTEGER NOT NULL DEFAULT 0,
    suspicious_outputs INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms INTEGER,
    last_seen TEXT,
    last_success TEXT,
    last_failure TEXT,
    latest_delivery_status TEXT NOT NULL DEFAULT '',
    latest_quality TEXT NOT NULL DEFAULT '',
    trust_score INTEGER NOT NULL DEFAULT 100,
    health_status TEXT NOT NULL DEFAULT 'healthy',
    incident_summary TEXT NOT NULL DEFAULT '',
    proposals_created INTEGER NOT NULL DEFAULT 0,
    proposals_rejected INTEGER NOT NULL DEFAULT 0,
    proposals_cancelled INTEGER NOT NULL DEFAULT 0,
    proposals_executed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
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
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    scope_type TEXT NOT NULL DEFAULT 'global',
    scope_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'operator',
    source_id TEXT,
    status TEXT NOT NULL,
    importance TEXT NOT NULL DEFAULT 'medium',
    confidence INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TEXT,
    updated_at TEXT,
    expires_at TEXT,
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
CREATE INDEX IF NOT EXISTS idx_deliveries_adapter_created ON deliveries(adapter_id, created_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_adapter_delivery_id ON deliveries(adapter_id, delivery_id);
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
CREATE INDEX IF NOT EXISTS idx_runtime_reputation_health ON runtime_reputation(health_status);
CREATE INDEX IF NOT EXISTS idx_workspace_packs_name ON workspace_packs(name);

CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '',
    goal TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS mission_workers (
    mission_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (mission_id, adapter_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mission_rooms (
    mission_id TEXT NOT NULL,
    room_name TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (mission_id, room_name),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mission_traces (
    mission_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (mission_id, trace_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mission_incidents (
    mission_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    incident_type TEXT NOT NULL DEFAULT '',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (mission_id, incident_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mission_proposals (
    mission_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (mission_id, proposal_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE,
    FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mission_relationships (
    relationship_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mission_events (
    event_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_updated ON missions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_mission_workers_worker ON mission_workers(adapter_id);
CREATE INDEX IF NOT EXISTS idx_mission_rooms_room ON mission_rooms(room_name);
CREATE INDEX IF NOT EXISTS idx_mission_traces_trace ON mission_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_mission_incidents_incident ON mission_incidents(incident_id);
CREATE INDEX IF NOT EXISTS idx_mission_proposals_proposal ON mission_proposals(proposal_id);
CREATE INDEX IF NOT EXISTS idx_mission_relationships_mission ON mission_relationships(mission_id);
CREATE INDEX IF NOT EXISTS idx_mission_events_created ON mission_events(created_at);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    owner TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outcome_workers (
    outcome_id TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (outcome_id, adapter_id),
    FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outcome_traces (
    outcome_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (outcome_id, trace_id),
    FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outcome_incidents (
    outcome_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    incident_type TEXT NOT NULL DEFAULT '',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (outcome_id, incident_id),
    FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outcome_proposals (
    outcome_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (outcome_id, proposal_id),
    FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE,
    FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outcome_relationships (
    relationship_id TEXT PRIMARY KEY,
    outcome_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS outcome_events (
    event_id TEXT PRIMARY KEY,
    outcome_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_outcomes_mission ON outcomes(mission_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_status ON outcomes(status);
CREATE INDEX IF NOT EXISTS idx_outcomes_updated ON outcomes(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcome_workers_worker ON outcome_workers(adapter_id);
CREATE INDEX IF NOT EXISTS idx_outcome_traces_trace ON outcome_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_outcome_incidents_incident ON outcome_incidents(incident_id);
CREATE INDEX IF NOT EXISTS idx_outcome_proposals_proposal ON outcome_proposals(proposal_id);
CREATE INDEX IF NOT EXISTS idx_outcome_relationships_outcome ON outcome_relationships(outcome_id);
CREATE INDEX IF NOT EXISTS idx_outcome_events_created ON outcome_events(created_at);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    owner_worker TEXT NOT NULL,
    mission_id TEXT,
    outcome_id TEXT,
    room_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignment_contributors (
    assignment_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (assignment_id, worker_id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assignment_events (
    event_id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'operator',
    old_value TEXT,
    new_value TEXT,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assignment_proposals (
    assignment_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (assignment_id, proposal_id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE,
    FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assignment_traces (
    assignment_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (assignment_id, trace_id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status);
CREATE INDEX IF NOT EXISTS idx_assignments_owner ON assignments(owner_worker);
CREATE INDEX IF NOT EXISTS idx_assignments_mission ON assignments(mission_id);
CREATE INDEX IF NOT EXISTS idx_assignments_outcome ON assignments(outcome_id);
CREATE INDEX IF NOT EXISTS idx_assignments_room ON assignments(room_id);
CREATE INDEX IF NOT EXISTS idx_assignments_updated ON assignments(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_assignment_contributors_worker ON assignment_contributors(worker_id);
CREATE INDEX IF NOT EXISTS idx_assignment_events_assignment ON assignment_events(assignment_id);
CREATE INDEX IF NOT EXISTS idx_assignment_events_created ON assignment_events(created_at);
CREATE INDEX IF NOT EXISTS idx_assignment_proposals_proposal ON assignment_proposals(proposal_id);
CREATE INDEX IF NOT EXISTS idx_assignment_traces_trace ON assignment_traces(trace_id);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    decision_id TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    timestamp TEXT,
    room_id TEXT,
    room_name TEXT,
    task_id TEXT,
    assignment_id TEXT,
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

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    proposed_by TEXT NOT NULL,
    approved_by TEXT,
    rejected_by TEXT,
    executed_by TEXT,
    room_id TEXT,
    task_id TEXT,
    goal_id TEXT,
    linked_decision_ids_json TEXT NOT NULL DEFAULT '[]',
    linked_handoff_ids_json TEXT NOT NULL DEFAULT '[]',
    linked_message_ids_json TEXT NOT NULL DEFAULT '[]',
    execution_payload_json TEXT NOT NULL DEFAULT '{}',
    risk_level TEXT NOT NULL DEFAULT 'medium',
    requires_approval INTEGER NOT NULL DEFAULT 1,
    approval_reason TEXT NOT NULL DEFAULT '',
    executed_at TEXT,
    rejected_at TEXT
);

CREATE TABLE IF NOT EXISTS proposal_events (
    event_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_room ON proposals(room_id);
CREATE INDEX IF NOT EXISTS idx_proposals_task ON proposals(task_id);
CREATE INDEX IF NOT EXISTS idx_proposals_goal ON proposals(goal_id);
CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_proposal_events_proposal ON proposal_events(proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposal_events_created ON proposal_events(created_at);
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
            "title": "TEXT NOT NULL DEFAULT ''",
            "body": "TEXT NOT NULL DEFAULT ''",
            "scope_type": "TEXT NOT NULL DEFAULT 'global'",
            "scope_id": "TEXT",
            "source_type": "TEXT NOT NULL DEFAULT 'operator'",
            "source_id": "TEXT",
            "importance": "TEXT NOT NULL DEFAULT 'medium'",
            "updated_at": "TEXT",
            "expires_at": "TEXT",
            "token_cost_estimate": "INTEGER DEFAULT 0",
            "use_count": "INTEGER DEFAULT 0",
            "last_used_at": "TEXT",
        }
        for column, definition in shared_additions.items():
            if column not in shared_columns:
                self._conn.execute(f"ALTER TABLE shared_memory ADD COLUMN {column} {definition}")
        self._conn.execute("UPDATE shared_memory SET body = content WHERE COALESCE(body, '') = ''")
        self._conn.execute("UPDATE shared_memory SET title = substr(content, 1, 80) WHERE COALESCE(title, '') = ''")
        self._conn.execute("UPDATE shared_memory SET status = 'approved' WHERE status = 'peer_approved'")
        self._conn.execute("UPDATE shared_memory SET updated_at = COALESCE(reviewed_at, approved_at, created_at) WHERE updated_at IS NULL")
        self._conn.execute("UPDATE shared_memory SET scope_type = 'room', scope_id = room_name WHERE room_name IS NOT NULL AND (scope_id IS NULL OR scope_id = '')")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_events_memory_id ON memory_events(memory_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_memory_scope ON shared_memory(scope_type, scope_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_memory_importance ON shared_memory(importance)")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_reputation (
                runtime_id TEXT PRIMARY KEY,
                total_deliveries INTEGER NOT NULL DEFAULT 0,
                successful_replies INTEGER NOT NULL DEFAULT 0,
                empty_replies INTEGER NOT NULL DEFAULT 0,
                timeouts INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                wrong_identity INTEGER NOT NULL DEFAULT 0,
                suspicious_outputs INTEGER NOT NULL DEFAULT 0,
                avg_duration_ms INTEGER,
                last_seen TEXT,
                last_success TEXT,
                last_failure TEXT,
                latest_delivery_status TEXT NOT NULL DEFAULT '',
                latest_quality TEXT NOT NULL DEFAULT '',
                trust_score INTEGER NOT NULL DEFAULT 100,
                health_status TEXT NOT NULL DEFAULT 'healthy',
                incident_summary TEXT NOT NULL DEFAULT '',
                proposals_created INTEGER NOT NULL DEFAULT 0,
                proposals_rejected INTEGER NOT NULL DEFAULT 0,
                proposals_cancelled INTEGER NOT NULL DEFAULT 0,
                proposals_executed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        reputation_columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(runtime_reputation)").fetchall()
        }
        for column in ("proposals_created", "proposals_rejected", "proposals_cancelled", "proposals_executed"):
            if column not in reputation_columns:
                self._conn.execute(f"ALTER TABLE runtime_reputation ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_adapter_created ON deliveries(adapter_id, created_at)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_adapter_delivery_id ON deliveries(adapter_id, delivery_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_reputation_health ON runtime_reputation(health_status)")
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
        self._migrate_proposal_schema()
        self._migrate_mission_schema()
        self._migrate_outcome_schema()
        self._migrate_assignment_schema()

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
            "assignment_id": "TEXT",
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
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_assignment ON handoffs(assignment_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_handoffs_created_at ON handoffs(created_at DESC)")

    def _migrate_proposal_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proposals (
                proposal_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                proposal_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '',
                proposed_by TEXT NOT NULL,
                approved_by TEXT,
                rejected_by TEXT,
                executed_by TEXT,
                room_id TEXT,
                task_id TEXT,
                goal_id TEXT,
                linked_decision_ids_json TEXT NOT NULL DEFAULT '[]',
                linked_handoff_ids_json TEXT NOT NULL DEFAULT '[]',
                linked_message_ids_json TEXT NOT NULL DEFAULT '[]',
                execution_payload_json TEXT NOT NULL DEFAULT '{}',
                risk_level TEXT NOT NULL DEFAULT 'medium',
                requires_approval INTEGER NOT NULL DEFAULT 1,
                approval_reason TEXT NOT NULL DEFAULT '',
                executed_at TEXT,
                rejected_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proposal_events (
                event_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_room ON proposals(room_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_task ON proposals(task_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_goal ON proposals(goal_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_created ON proposals(created_at DESC)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposal_events_proposal ON proposal_events(proposal_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_proposal_events_created ON proposal_events(created_at)")

    def _migrate_mission_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS missions (
                mission_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                priority TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT '',
                goal TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                risk_level TEXT NOT NULL DEFAULT 'medium'
            );
            CREATE TABLE IF NOT EXISTS mission_workers (
                mission_id TEXT NOT NULL,
                adapter_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL,
                PRIMARY KEY (mission_id, adapter_id),
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mission_rooms (
                mission_id TEXT NOT NULL,
                room_name TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (mission_id, room_name),
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mission_traces (
                mission_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (mission_id, trace_id),
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mission_incidents (
                mission_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                incident_type TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL,
                PRIMARY KEY (mission_id, incident_id),
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mission_proposals (
                mission_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (mission_id, proposal_id),
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE,
                FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mission_relationships (
                relationship_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                observed_at TEXT NOT NULL,
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mission_events (
                event_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
            CREATE INDEX IF NOT EXISTS idx_missions_updated ON missions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_mission_workers_worker ON mission_workers(adapter_id);
            CREATE INDEX IF NOT EXISTS idx_mission_rooms_room ON mission_rooms(room_name);
            CREATE INDEX IF NOT EXISTS idx_mission_traces_trace ON mission_traces(trace_id);
            CREATE INDEX IF NOT EXISTS idx_mission_incidents_incident ON mission_incidents(incident_id);
            CREATE INDEX IF NOT EXISTS idx_mission_proposals_proposal ON mission_proposals(proposal_id);
            CREATE INDEX IF NOT EXISTS idx_mission_relationships_mission ON mission_relationships(mission_id);
            CREATE INDEX IF NOT EXISTS idx_mission_events_created ON mission_events(created_at);
            """
        )

    def _migrate_outcome_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS outcomes (
                outcome_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                confidence TEXT NOT NULL DEFAULT 'medium',
                owner TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS outcome_workers (
                outcome_id TEXT NOT NULL,
                adapter_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL,
                PRIMARY KEY (outcome_id, adapter_id),
                FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS outcome_traces (
                outcome_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (outcome_id, trace_id),
                FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS outcome_incidents (
                outcome_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                incident_type TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL,
                PRIMARY KEY (outcome_id, incident_id),
                FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS outcome_proposals (
                outcome_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (outcome_id, proposal_id),
                FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE,
                FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS outcome_relationships (
                relationship_id TEXT PRIMARY KEY,
                outcome_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                observed_at TEXT NOT NULL,
                FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS outcome_events (
                event_id TEXT PRIMARY KEY,
                outcome_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(outcome_id) REFERENCES outcomes(outcome_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_outcomes_mission ON outcomes(mission_id);
            CREATE INDEX IF NOT EXISTS idx_outcomes_status ON outcomes(status);
            CREATE INDEX IF NOT EXISTS idx_outcomes_updated ON outcomes(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_outcome_workers_worker ON outcome_workers(adapter_id);
            CREATE INDEX IF NOT EXISTS idx_outcome_traces_trace ON outcome_traces(trace_id);
            CREATE INDEX IF NOT EXISTS idx_outcome_incidents_incident ON outcome_incidents(incident_id);
            CREATE INDEX IF NOT EXISTS idx_outcome_proposals_proposal ON outcome_proposals(proposal_id);
            CREATE INDEX IF NOT EXISTS idx_outcome_relationships_outcome ON outcome_relationships(outcome_id);
            CREATE INDEX IF NOT EXISTS idx_outcome_events_created ON outcome_events(created_at);
            """
        )

    def _migrate_assignment_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                assignment_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                owner_worker TEXT NOT NULL,
                mission_id TEXT,
                outcome_id TEXT,
                room_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assignment_contributors (
                assignment_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (assignment_id, worker_id),
                FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS assignment_events (
                event_id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'operator',
                old_value TEXT,
                new_value TEXT,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS assignment_proposals (
                assignment_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (assignment_id, proposal_id),
                FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE,
                FOREIGN KEY(proposal_id) REFERENCES proposals(proposal_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS assignment_traces (
                assignment_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (assignment_id, trace_id),
                FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status);
            CREATE INDEX IF NOT EXISTS idx_assignments_owner ON assignments(owner_worker);
            CREATE INDEX IF NOT EXISTS idx_assignments_mission ON assignments(mission_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_outcome ON assignments(outcome_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_room ON assignments(room_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_updated ON assignments(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_assignment_contributors_worker ON assignment_contributors(worker_id);
            CREATE INDEX IF NOT EXISTS idx_assignment_events_assignment ON assignment_events(assignment_id);
            CREATE INDEX IF NOT EXISTS idx_assignment_events_created ON assignment_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_assignment_proposals_proposal ON assignment_proposals(proposal_id);
            CREATE INDEX IF NOT EXISTS idx_assignment_traces_trace ON assignment_traces(trace_id);
            """
        )

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
        self.recompute_runtime_health(reply.adapter_id)

    def _delivery_quality_from_raw(self, raw_json: str | None) -> str:
        if not raw_json:
            return ""
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError:
            return ""
        return str(raw.get("quality") or "").strip()

    def _delivery_row_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        data["quality"] = self._delivery_quality_from_raw(data.get("raw_json"))
        return data

    def _runtime_health_status(
        self,
        trust_score: int,
        *,
        recent_timeouts: int,
        recent_empty_replies: int,
        recent_failures: int,
        recent_wrong_identity: int,
        sample_size: int = RUNTIME_REPUTATION_MIN_SAMPLE_SIZE,
        latest_status: str = "",
        min_sample_size: int = RUNTIME_REPUTATION_MIN_SAMPLE_SIZE,
    ) -> str:
        severe = recent_timeouts + recent_failures
        if sample_size < min_sample_size:
            if latest_status in {"timeout", "failed", "blocked"}:
                return "unstable" if severe >= 2 else "degraded"
            if recent_wrong_identity or recent_empty_replies or trust_score < 90:
                return "degraded"
            return "healthy"

        if (
            recent_timeouts >= 5
            or recent_failures >= 6
            or recent_empty_replies >= 6
            or (trust_score < 35 and (recent_timeouts >= 3 or recent_failures >= 3 or recent_empty_replies >= 5))
        ):
            return "failing"
        if recent_timeouts >= 3 or recent_failures >= 4 or recent_empty_replies >= 4 or recent_wrong_identity >= 3:
            return "unstable"
        if recent_wrong_identity or recent_empty_replies >= 2:
            status = "degraded"
        elif trust_score < 70:
            status = "unstable"
        elif trust_score < 90:
            status = "degraded"
        else:
            status = "healthy"
        return status

    def _runtime_incident_summary(self, runtime_id: str, counts: dict[str, int], health_status: str) -> str:
        if health_status == "healthy":
            return ""
        issues = []
        labels = [
            ("timeouts", "timeouts"),
            ("empty_replies", "empty replies"),
            ("wrong_identity", "wrong identity replies"),
            ("suspicious_outputs", "suspicious outputs"),
            ("failures", "failures"),
        ]
        for key, label in labels:
            if counts.get(key, 0):
                issues.append(f"{counts[key]} {label}")
        return f"{runtime_id} {health_status}: {', '.join(issues[:2])} in recent deliveries" if issues else ""

    def recompute_runtime_health(self, runtime_id: str, limit: int = RUNTIME_REPUTATION_RECENT_WINDOW) -> dict:
        recent_window = max(1, min(int(limit), RUNTIME_REPUTATION_RECENT_WINDOW))
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT delivery_id, status, ok, duration_ms, raw_json, created_at
                FROM deliveries
                WHERE adapter_id = ?
                ORDER BY delivery_id DESC
                LIMIT ?
                """,
                (runtime_id, recent_window),
            ).fetchall()
            rows = list(reversed(rows))
            total_row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM deliveries WHERE adapter_id = ?",
                (runtime_id,),
            ).fetchone()
            total = int(total_row["count"] if total_row else len(rows))
            successful = 0
            empty = 0
            timeouts = 0
            failures = 0
            wrong_identity = 0
            suspicious = 0
            durations = []
            last_seen = None
            last_success = None
            last_failure = None
            latest_status = ""
            latest_quality = ""
            for row in rows:
                status = str(row["status"] or "")
                quality = self._delivery_quality_from_raw(row["raw_json"])
                ok = bool(row["ok"])
                created_at = row["created_at"]
                last_seen = created_at
                latest_status = status
                latest_quality = quality
                try:
                    duration_ms = int(row["duration_ms"]) if row["duration_ms"] is not None else None
                except (TypeError, ValueError):
                    duration_ms = None
                if duration_ms is not None:
                    durations.append(duration_ms)
                if ok and status not in {"empty_reply", "timeout", "failed", "blocked"}:
                    successful += 1
                    last_success = created_at
                if status == "empty_reply":
                    empty += 1
                    last_failure = created_at
                if status == "timeout":
                    timeouts += 1
                    last_failure = created_at
                if (not ok) or status in {"failed", "blocked"}:
                    failures += 1
                    last_failure = created_at
                if status == "wrong_identity" or quality == "wrong_identity":
                    wrong_identity += 1
                    last_failure = created_at
                if status == "suspicious_output" or quality == "suspicious_output":
                    suspicious += 1
                    last_failure = created_at
            recent = rows[-recent_window:]
            recent_counts = {
                "timeouts": sum(1 for row in recent if str(row["status"] or "") == "timeout"),
                "empty_replies": sum(1 for row in recent if str(row["status"] or "") == "empty_reply"),
                "failures": sum(1 for row in recent if (not bool(row["ok"])) or str(row["status"] or "") in {"failed", "blocked"}),
                "wrong_identity": sum(
                    1 for row in recent
                    if str(row["status"] or "") == "wrong_identity"
                    or self._delivery_quality_from_raw(row["raw_json"]) == "wrong_identity"
                ),
                "suspicious_outputs": sum(
                    1 for row in recent
                    if str(row["status"] or "") == "suspicious_output"
                    or self._delivery_quality_from_raw(row["raw_json"]) == "suspicious_output"
                ),
            }
            avg_duration = int(sum(durations) / len(durations)) if durations else None
            trust_score = 100
            trust_score += min(successful, 8)
            trust_score -= empty * 10
            trust_score -= timeouts * 18
            trust_score -= failures * 15
            trust_score -= wrong_identity * 8
            trust_score -= suspicious * 6
            trust_score = max(0, min(100, trust_score))
            health_status = self._runtime_health_status(
                trust_score,
                recent_timeouts=recent_counts["timeouts"],
                recent_empty_replies=recent_counts["empty_replies"],
                recent_failures=recent_counts["failures"],
                recent_wrong_identity=recent_counts["wrong_identity"],
                sample_size=len(rows),
                latest_status=latest_status,
            )
            incident_summary = self._runtime_incident_summary(runtime_id, recent_counts, health_status)
            proposal_row = self._conn.execute(
                """
                SELECT
                  COUNT(*) AS created,
                  SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                  SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
                  SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) AS executed
                FROM proposals
                WHERE proposed_by = ?
                   OR approved_by = ?
                   OR rejected_by = ?
                   OR executed_by = ?
                """,
                (runtime_id, runtime_id, runtime_id, runtime_id),
            ).fetchone()
            proposal_counts = {
                "created": int(proposal_row["created"] or 0) if proposal_row else 0,
                "rejected": int(proposal_row["rejected"] or 0) if proposal_row else 0,
                "cancelled": int(proposal_row["cancelled"] or 0) if proposal_row else 0,
                "executed": int(proposal_row["executed"] or 0) if proposal_row else 0,
            }
            now = utc_now_iso()
            self._conn.execute(
                """
                INSERT INTO runtime_reputation (
                    runtime_id, total_deliveries, successful_replies, empty_replies,
                    timeouts, failures, wrong_identity, suspicious_outputs,
                    avg_duration_ms, last_seen, last_success, last_failure,
                    latest_delivery_status, latest_quality, trust_score,
                    health_status, incident_summary, proposals_created,
                    proposals_rejected, proposals_cancelled, proposals_executed,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runtime_id) DO UPDATE SET
                    total_deliveries = excluded.total_deliveries,
                    successful_replies = excluded.successful_replies,
                    empty_replies = excluded.empty_replies,
                    timeouts = excluded.timeouts,
                    failures = excluded.failures,
                    wrong_identity = excluded.wrong_identity,
                    suspicious_outputs = excluded.suspicious_outputs,
                    avg_duration_ms = excluded.avg_duration_ms,
                    last_seen = excluded.last_seen,
                    last_success = excluded.last_success,
                    last_failure = excluded.last_failure,
                    latest_delivery_status = excluded.latest_delivery_status,
                    latest_quality = excluded.latest_quality,
                    trust_score = excluded.trust_score,
                    health_status = excluded.health_status,
                    incident_summary = excluded.incident_summary,
                    proposals_created = excluded.proposals_created,
                    proposals_rejected = excluded.proposals_rejected,
                    proposals_cancelled = excluded.proposals_cancelled,
                    proposals_executed = excluded.proposals_executed,
                    updated_at = excluded.updated_at
                """,
                (
                    runtime_id, total, successful, empty, timeouts, failures,
                    wrong_identity, suspicious, avg_duration, last_seen,
                    last_success, last_failure, latest_status, latest_quality,
                    trust_score, health_status, incident_summary,
                    proposal_counts["created"], proposal_counts["rejected"],
                    proposal_counts["cancelled"], proposal_counts["executed"], now,
                ),
            )
        reputation = self.get_runtime_reputation(runtime_id)
        assert reputation is not None
        return reputation

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

    def get_delivery(self, delivery_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM deliveries WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
        return self._delivery_row_from_row(row) if row else None

    def get_dead_letter(self, dead_letter_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM dead_letters WHERE dead_letter_id = ?",
                (dead_letter_id,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["payload"] = json.loads(data.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            data["payload"] = {}
        return data

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
        return [self._delivery_row_from_row(row) for row in rows]

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
                       duration_ms, attempts, raw_json, created_at, substr(body, 1, 160) AS body_preview
                FROM deliveries
                ORDER BY delivery_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"deliveries": [self._delivery_row_from_row(row) for row in rows]}

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

    def get_runtime_reputation(self, runtime_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runtime_reputation WHERE runtime_id = ?",
                (runtime_id,),
            ).fetchone()
        if row is None:
            with self._lock:
                has_delivery = self._conn.execute(
                    "SELECT 1 FROM deliveries WHERE adapter_id = ? LIMIT 1",
                    (runtime_id,),
                ).fetchone()
            if has_delivery:
                return self.recompute_runtime_health(runtime_id)
            agent = self.get_agent(runtime_id)
            runtime = self.get_runtime(runtime_id)
            if not agent and not runtime:
                return None
            return {
                "runtime_id": runtime_id,
                "total_deliveries": 0,
                "successful_replies": 0,
                "empty_replies": 0,
                "timeouts": 0,
                "failures": 0,
                "wrong_identity": 0,
                "suspicious_outputs": 0,
                "avg_duration_ms": None,
                "last_seen": None,
                "last_success": None,
                "last_failure": None,
                "latest_delivery_status": "",
                "latest_quality": "",
                "trust_score": 100,
                "health_status": "healthy",
                "incident_summary": "",
                "proposals_created": 0,
                "proposals_rejected": 0,
                "proposals_cancelled": 0,
                "proposals_executed": 0,
                "updated_at": None,
            }
        return dict(row)

    def get_all_runtime_reputations(self) -> list[dict]:
        runtime_ids = {
            str(agent["adapter_id"])
            for agent in self.list_agents()
        }
        runtime_ids.update(str(runtime["runtime_id"]) for runtime in self.list_runtimes())
        with self._lock:
            reputation_ids = [
                str(row["runtime_id"])
                for row in self._conn.execute("SELECT runtime_id FROM runtime_reputation").fetchall()
            ]
        runtime_ids.update(reputation_ids)
        return [
            reputation for runtime_id in sorted(runtime_ids)
            if (reputation := self.get_runtime_reputation(runtime_id)) is not None
        ]

    def _runtime_proposal_counts(self, runtime_id: str) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                  COUNT(*) AS created,
                  SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                  SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
                  SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) AS executed
                FROM proposals
                WHERE proposed_by = ?
                   OR approved_by = ?
                   OR rejected_by = ?
                   OR executed_by = ?
                """,
                (runtime_id, runtime_id, runtime_id, runtime_id),
            ).fetchone()
        return {
            "proposals_created": int(row["created"] or 0) if row else 0,
            "proposals_rejected": int(row["rejected"] or 0) if row else 0,
            "proposals_cancelled": int(row["cancelled"] or 0) if row else 0,
            "proposals_executed": int(row["executed"] or 0) if row else 0,
        }

    def _workforce_runtime_sections(self) -> tuple[list[str], list[dict], list[dict]]:
        agents = self.list_agents()
        runtimes = {str(runtime["runtime_id"]): runtime for runtime in self.list_runtimes()}
        agent_ids = {str(agent["adapter_id"]) for agent in agents}
        enabled_agent_ids = [
            str(agent["adapter_id"])
            for agent in agents
            if bool(agent.get("enabled"))
        ]
        disabled = []
        for agent in agents:
            adapter_id = str(agent["adapter_id"])
            if bool(agent.get("enabled")):
                continue
            runtime = runtimes.get(adapter_id, {})
            disabled.append({
                "runtime_id": adapter_id,
                "runtime_name": agent.get("runtime_name") or runtime.get("runtime_id") or adapter_id,
                "runtime_type": agent.get("type") or runtime.get("runtime_type") or runtime.get("adapter_type") or "unknown",
                "reason": "disabled",
            })
        registry_only = []
        for runtime_id, runtime in runtimes.items():
            if runtime_id in agent_ids:
                continue
            target = registry_only if bool(runtime.get("enabled", True)) else disabled
            target.append({
                "runtime_id": runtime_id,
                "runtime_name": runtime.get("display_name") or runtime_id,
                "runtime_type": runtime.get("runtime_type") or runtime.get("adapter_type") or "unknown",
                "reason": "registry-only" if target is registry_only else "disabled",
            })
        return enabled_agent_ids, registry_only, disabled

    def workforce_summary(self) -> dict:
        enabled_agent_ids, registry_only, disabled = self._workforce_runtime_sections()
        reputations = [
            reputation for runtime_id in sorted(enabled_agent_ids)
            if (reputation := self.get_runtime_reputation(runtime_id)) is not None
        ]
        counts = {status: 0 for status in ("healthy", "degraded", "unstable", "failing")}
        for reputation in reputations:
            status = str(reputation.get("health_status") or "healthy")
            if status in counts:
                counts[status] += 1
        top_trusted = sorted(
            reputations,
            key=lambda item: (-int(item.get("trust_score") or 0), str(item.get("runtime_id") or "")),
        )[:3]
        most_unstable = sorted(
            [item for item in reputations if item.get("health_status") in {"unstable", "failing", "degraded"}],
            key=lambda item: (int(item.get("trust_score") or 100), str(item.get("runtime_id") or "")),
        )[:3]
        incidents = [
            item["incident_summary"] for item in reputations
            if item.get("incident_summary")
        ]
        return {
            "summary": counts,
            "top_trusted": [item["runtime_id"] for item in top_trusted],
            "most_unstable": [item["runtime_id"] for item in most_unstable],
            "recent_incidents": incidents[:5],
            "runtimes": reputations,
            "enabled_workers": len(enabled_agent_ids),
            "registry_only": registry_only,
            "disabled_runtimes": disabled,
            "available_but_inactive": registry_only + disabled,
        }

    @staticmethod
    def _parse_activity_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _presence_seconds_since(now: datetime, timestamp: str | None) -> int | None:
        parsed = Storage._parse_activity_timestamp(timestamp)
        if parsed is None:
            return None
        return max(0, int((now - parsed).total_seconds()))

    @staticmethod
    def _runtime_attention_reason(reputation: dict, enabled: bool, registry_only: bool) -> str:
        if registry_only:
            return "Runtime is discovered but not configured as an active worker."
        if not enabled:
            return "Worker is disabled or offline."
        quality = str(reputation.get("latest_quality") or "")
        if quality == "empty":
            return "Empty replies detected."
        if quality == "wrong_identity":
            return "Identity mismatch in recent replies."
        if int(reputation.get("timeouts") or 0) > 0:
            return "Timeout history detected."
        if int(reputation.get("failures") or 0) > 0:
            return "Recent delivery failures detected."
        if int(reputation.get("trust_score") or 100) < 50:
            return "Trust score is low."
        if str(reputation.get("health_status") or "healthy") in {"degraded", "unstable", "failing"}:
            return str(reputation.get("incident_summary") or "Runtime health needs attention.")
        return ""

    @staticmethod
    def _runtime_suggested_action(presence_state: str, attention_reason: str, current_room: str | None) -> str:
        if presence_state in {"active", "idle"}:
            return "No action needed."
        if presence_state == "watching":
            return "Monitor room activity."
        if "Empty replies" in attention_reason:
            return "Remove from active rooms unless needed."
        if "Identity mismatch" in attention_reason:
            return "Inspect latest trace before relying on replies."
        if "Timeout" in attention_reason:
            return "Restart adapter if this worker is needed."
        if "delivery failures" in attention_reason:
            return "Inspect latest trace or remove from active rooms."
        if presence_state == "unavailable":
            return "Enable or configure the runtime before assigning work."
        if current_room:
            return f"Check #{current_room} before assigning more work."
        return "Review before assigning work."

    def _latest_runtime_activity(self, runtime_id: str) -> dict | None:
        candidates: list[dict] = []
        with self._lock:
            delivery = self._conn.execute(
                """
                SELECT d.delivery_id, d.adapter_id, d.status, d.ok, d.error, d.created_at,
                       d.body, m.target, m.conversation_id
                FROM deliveries d
                LEFT JOIN messages m ON m.message_id = d.message_id
                WHERE d.adapter_id = ?
                ORDER BY d.created_at DESC, d.delivery_id DESC
                LIMIT 1
                """,
                (runtime_id,),
            ).fetchone()
            message = self._conn.execute(
                """
                SELECT message_id, conversation_id, source, target, timestamp, body
                FROM messages
                WHERE source = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (runtime_id,),
            ).fetchone()
            proposal = self._conn.execute(
                """
                SELECT proposal_id, title, room_id, status, proposed_by, created_at, updated_at
                FROM proposals
                WHERE proposed_by = ? OR approved_by = ? OR rejected_by = ? OR executed_by = ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT 1
                """,
                (runtime_id, runtime_id, runtime_id, runtime_id),
            ).fetchone()
            handoff = self._conn.execute(
                """
                SELECT handoff_id, room_id, task_id, from_agent, to_agent, status, created_at, updated_at
                FROM handoffs
                WHERE from_agent = ? OR to_agent = ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT 1
                """,
                (runtime_id, runtime_id),
            ).fetchone()
            decision = self._conn.execute(
                """
                SELECT decision_id, title, room_id, status, proposed_by, approved_by, created_at, updated_at
                FROM decisions
                WHERE proposed_by = ? OR approved_by = ?
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT 1
                """,
                (runtime_id, runtime_id),
            ).fetchone()
            dead_letter = self._conn.execute(
                """
                SELECT dead_letter_id, adapter_id, reason, created_at
                FROM dead_letters
                WHERE adapter_id = ?
                ORDER BY created_at DESC, dead_letter_id DESC
                LIMIT 1
                """,
                (runtime_id,),
            ).fetchone()
        if delivery:
            target = str(delivery["target"] or "")
            room = target.removeprefix("room:") if target.startswith("room:") else None
            ok = bool(delivery["ok"])
            candidates.append({
                "activity_type": "delivery",
                "summary": f"{runtime_id} replied in #{room}" if ok and room else f"{runtime_id} replied" if ok else f"{runtime_id} delivery failed",
                "timestamp": delivery["created_at"],
                "room_id": room,
                "goal_id": None,
                "task_id": None,
                "severity": "info" if ok else "warning",
            })
        if message:
            target = str(message["target"] or "")
            room = target.removeprefix("room:") if target.startswith("room:") else None
            candidates.append({
                "activity_type": "message",
                "summary": f"{runtime_id} sent a message in #{room}" if room else f"{runtime_id} sent a message to {target}",
                "timestamp": message["timestamp"],
                "room_id": room,
                "goal_id": None,
                "task_id": None,
                "severity": "info",
            })
        if proposal:
            title = str(proposal["title"] or "proposal")
            candidates.append({
                "activity_type": "proposal",
                "summary": f"{runtime_id} updated proposal: {title}",
                "timestamp": proposal["updated_at"] or proposal["created_at"],
                "room_id": proposal["room_id"],
                "goal_id": None,
                "task_id": None,
                "severity": "info" if proposal["status"] in {"approved", "executed"} else "notice",
            })
        if handoff:
            peer = handoff["to_agent"] if handoff["from_agent"] == runtime_id else handoff["from_agent"]
            candidates.append({
                "activity_type": "handoff",
                "summary": f"{runtime_id} handoff with {peer}",
                "timestamp": handoff["updated_at"] or handoff["created_at"],
                "room_id": handoff["room_id"],
                "goal_id": None,
                "task_id": handoff["task_id"],
                "severity": "info",
            })
        if decision:
            title = str(decision["title"] or "decision")
            candidates.append({
                "activity_type": "decision",
                "summary": f"{runtime_id} touched decision: {title}",
                "timestamp": decision["updated_at"] or decision["created_at"],
                "room_id": decision["room_id"],
                "goal_id": None,
                "task_id": None,
                "severity": "info",
            })
        if dead_letter:
            candidates.append({
                "activity_type": "dead_letter",
                "summary": f"Dead letter recorded for {runtime_id}: {dead_letter['reason']}",
                "timestamp": dead_letter["created_at"],
                "room_id": None,
                "goal_id": None,
                "task_id": None,
                "severity": "warning",
            })
        candidates = [item for item in candidates if item.get("timestamp")]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: self._parse_activity_timestamp(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
        )

    def workforce_presence(self, active_window_seconds: int = 300) -> dict:
        now = datetime.now(timezone.utc)
        agents = {str(agent["adapter_id"]): agent for agent in self.list_agents()}
        runtimes = {str(runtime["runtime_id"]): runtime for runtime in self.list_runtimes()}
        reputations = {str(item["runtime_id"]): item for item in self.get_all_runtime_reputations()}
        runtime_ids = sorted(set(agents) | set(runtimes) | set(reputations))
        workers = []
        for runtime_id in runtime_ids:
            agent = agents.get(runtime_id, {})
            runtime = runtimes.get(runtime_id, {})
            reputation = reputations.get(runtime_id) or self.get_runtime_reputation(runtime_id) or {}
            registry_only = runtime_id in runtimes and runtime_id not in agents
            enabled = bool(agent.get("enabled", runtime.get("enabled", True))) and not registry_only
            health_status = str(reputation.get("health_status") or "healthy")
            activity = self._latest_runtime_activity(runtime_id) or {}
            latest_at = activity.get("timestamp") or agent.get("last_message_at") or reputation.get("last_seen")
            idle_for_seconds = self._presence_seconds_since(now, latest_at)
            current_room = agent.get("current_room") or activity.get("room_id") or None
            current_mission = self.current_mission_for_worker(runtime_id)
            current_outcome = self.current_outcome_for_worker(runtime_id)
            assignment_state = self.worker_assignments(runtime_id, limit=100)
            assignment_counts = assignment_state["counts"]
            attention_reason = self._runtime_attention_reason(reputation, enabled, registry_only)
            needs_attention = bool(attention_reason) and (
                registry_only
                or not enabled
                or health_status in {"degraded", "unstable", "failing"}
                or int(reputation.get("trust_score") or 100) < 50
            )
            recent_success = self._presence_seconds_since(now, reputation.get("last_success"))
            if not enabled:
                presence_state = "unavailable"
            elif needs_attention:
                presence_state = "needs_attention"
            elif recent_success is not None and recent_success <= active_window_seconds:
                presence_state = "active"
            elif idle_for_seconds is not None and idle_for_seconds <= active_window_seconds:
                presence_state = "active"
            elif current_room and health_status in {"healthy", "degraded"}:
                presence_state = "watching"
            elif health_status in {"healthy", "degraded"}:
                presence_state = "idle"
            else:
                presence_state = "unknown"
            if activity:
                summary = str(activity.get("summary") or "Recent activity recorded.")
                activity_type = str(activity.get("activity_type") or "activity")
            else:
                summary = "No recent activity recorded."
                activity_type = "runtime_health"
            if needs_attention:
                current_activity = "Needs attention"
            elif presence_state == "active" and activity_type == "proposal":
                current_activity = "Reviewing proposal"
            elif presence_state == "active" and activity_type == "delivery":
                current_activity = "Reply generated"
            elif presence_state == "active" and current_room:
                current_activity = "Working in room"
            elif presence_state == "watching":
                current_activity = "Watching room"
            elif presence_state == "idle":
                current_activity = "Idle"
            elif presence_state == "unavailable":
                current_activity = "Unavailable"
            else:
                current_activity = "Awaiting activity"
            workers.append({
                "runtime_id": runtime_id,
                "display_name": agent.get("runtime_name") or runtime.get("display_name") or runtime_id,
                "runtime_type": agent.get("type") or runtime.get("runtime_type") or runtime.get("adapter_type") or "unknown",
                "status": agent.get("status") or ("enabled" if enabled else "disabled"),
                "health_status": health_status,
                "trust_score": int(reputation.get("trust_score") or agent.get("trust") or 100),
                "presence_state": presence_state,
                "current_room": current_room,
                "current_mission": current_mission,
                "current_outcome": current_outcome,
                "assignment_counts": assignment_counts,
                "current_assignment_count": assignment_counts["owned"] + assignment_counts["contributor"],
                "owned_assignments": assignment_state["owned"],
                "contributor_assignments": assignment_state["contributing"],
                "assignments_waiting": assignment_counts["waiting"],
                "assignments_blocked": assignment_counts["blocked"],
                "assignments_in_review": assignment_counts["review"],
                "current_task_id": agent.get("current_task_id"),
                "current_goal_id": activity.get("goal_id"),
                "latest_activity_type": activity_type,
                "latest_activity_summary": summary,
                "latest_activity_at": latest_at,
                "current_activity": current_activity,
                "last_meaningful_action": summary,
                "seconds_since_activity": idle_for_seconds,
                "last_success_at": reputation.get("last_success"),
                "last_failure_at": reputation.get("last_failure"),
                "idle_for_seconds": idle_for_seconds,
                "needs_attention": needs_attention,
                "attention_reason": attention_reason if needs_attention else "",
                "suggested_action": self._runtime_suggested_action(presence_state, attention_reason, current_room),
            })
        summary_counts = {state: 0 for state in ("active", "idle", "watching", "needs_attention", "unavailable", "unknown")}
        for worker in workers:
            summary_counts[str(worker["presence_state"])] += 1
        attention_worker = next((worker for worker in workers if worker["needs_attention"]), None)
        active_worker = next((worker for worker in workers if worker["presence_state"] == "active"), None)
        if attention_worker:
            highest_priority = f"{attention_worker['display_name']}: {attention_worker['attention_reason']}"
            suggested_next_action = str(attention_worker["suggested_action"])
        elif active_worker:
            highest_priority = str(active_worker["latest_activity_summary"])
            suggested_next_action = "Monitor active work."
        else:
            highest_priority = "No active issues detected."
            suggested_next_action = "Assign work when ready."
        return {
            "summary": {
                "total": len(workers),
                **summary_counts,
                "highest_priority": highest_priority,
                "suggested_next_action": suggested_next_action,
            },
            "workers": workers,
            "recent_activity": self.list_recent_activity(limit=12)["activity"],
        }

    def list_recent_activity(self, limit: int = 50) -> dict:
        limit = max(1, min(int(limit), 200))
        records: list[dict] = []
        with self._lock:
            messages = self._conn.execute(
                """
                SELECT message_id, conversation_id, source, target, timestamp, message_type, subject
                FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            deliveries = self._conn.execute(
                """
                SELECT d.delivery_id, d.adapter_id, d.status, d.ok, d.error, d.created_at, m.target
                FROM deliveries d
                LEFT JOIN messages m ON m.message_id = d.message_id
                ORDER BY d.created_at DESC, d.delivery_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            proposals = self._conn.execute(
                """
                SELECT proposal_id, title, room_id, status, proposed_by, created_at, updated_at
                FROM proposals
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            handoffs = self._conn.execute(
                """
                SELECT handoff_id, room_id, task_id, from_agent, to_agent, status, created_at, updated_at
                FROM handoffs
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            decisions = self._conn.execute(
                """
                SELECT decision_id, title, room_id, status, proposed_by, approved_by, created_at, updated_at
                FROM decisions
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            dead_letters = self._conn.execute(
                """
                SELECT dead_letter_id, adapter_id, reason, created_at
                FROM dead_letters
                ORDER BY created_at DESC, dead_letter_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            assignment_events = self._conn.execute(
                """
                SELECT ae.event_id, ae.assignment_id, ae.event_type, ae.actor, ae.created_at,
                       a.title, a.status, a.owner_worker, a.mission_id, a.outcome_id, a.room_id
                FROM assignment_events ae
                LEFT JOIN assignments a ON a.assignment_id = ae.assignment_id
                ORDER BY ae.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        for row in messages:
            target = str(row["target"] or "")
            room_id = target.removeprefix("room:") if target.startswith("room:") else None
            records.append({
                "activity_id": row["message_id"],
                "timestamp": row["timestamp"],
                "actor": row["source"],
                "actor_type": "runtime" if row["source"] != "operator" else "operator",
                "activity_type": "message",
                "summary": f"{row['source']} sent a message in #{room_id}" if room_id else f"{row['source']} sent a message to {target}",
                "room_id": room_id,
                "task_id": None,
                "goal_id": None,
                "proposal_id": None,
                "trace_id": row["conversation_id"],
                "severity": "info",
            })
        for row in deliveries:
            target = str(row["target"] or "")
            room_id = target.removeprefix("room:") if target.startswith("room:") else None
            ok = bool(row["ok"])
            records.append({
                "activity_id": str(row["delivery_id"]),
                "timestamp": row["created_at"],
                "actor": row["adapter_id"],
                "actor_type": "runtime",
                "activity_type": "delivery",
                "summary": f"{row['adapter_id']} replied in #{room_id}" if ok and room_id else f"{row['adapter_id']} replied" if ok else f"{row['adapter_id']} delivery failed",
                "room_id": room_id,
                "task_id": None,
                "goal_id": None,
                "proposal_id": None,
                "trace_id": None,
                "severity": "info" if ok else "warning",
            })
        for row in proposals:
            records.append({
                "activity_id": row["proposal_id"],
                "timestamp": row["updated_at"] or row["created_at"],
                "actor": row["proposed_by"],
                "actor_type": "runtime",
                "activity_type": "proposal",
                "summary": f"{row['proposed_by']} proposed: {row['title']}",
                "room_id": row["room_id"],
                "task_id": None,
                "goal_id": None,
                "proposal_id": row["proposal_id"],
                "trace_id": None,
                "severity": "info" if row["status"] in {"approved", "executed"} else "notice",
            })
        for row in handoffs:
            records.append({
                "activity_id": row["handoff_id"],
                "timestamp": row["updated_at"] or row["created_at"],
                "actor": row["from_agent"],
                "actor_type": "runtime",
                "activity_type": "handoff",
                "summary": f"{row['from_agent']} handed off to {row['to_agent']}",
                "room_id": row["room_id"],
                "task_id": row["task_id"],
                "goal_id": None,
                "proposal_id": None,
                "trace_id": None,
                "severity": "info" if row["status"] != "rejected" else "warning",
            })
        for row in decisions:
            actor = row["approved_by"] or row["proposed_by"]
            records.append({
                "activity_id": row["decision_id"],
                "timestamp": row["updated_at"] or row["created_at"],
                "actor": actor,
                "actor_type": "runtime" if actor != "operator" else "operator",
                "activity_type": "decision",
                "summary": f"Decision {row['status']}: {row['title']}",
                "room_id": row["room_id"],
                "task_id": None,
                "goal_id": None,
                "proposal_id": None,
                "trace_id": None,
                "severity": "info" if row["status"] == "approved" else "notice",
            })
        for row in dead_letters:
            records.append({
                "activity_id": row["dead_letter_id"],
                "timestamp": row["created_at"],
                "actor": row["adapter_id"],
                "actor_type": "runtime",
                "activity_type": "dead_letter",
                "summary": f"Dead letter recorded for {row['adapter_id']}: {row['reason']}",
                "room_id": None,
                "task_id": None,
                "goal_id": None,
                "proposal_id": None,
                "trace_id": None,
                "severity": "warning",
            })
        for row in assignment_events:
            actor = str(row["actor"] or "operator")
            title = self._activity_summary_subject(row["title"], "assignment")
            records.append({
                "activity_id": row["event_id"],
                "timestamp": row["created_at"],
                "actor": actor,
                "actor_type": "operator" if actor == "operator" else "runtime",
                "activity_type": str(row["event_type"] or "assignment"),
                "summary": f"Assignment {row['event_type']}: {title}",
                "room_id": row["room_id"],
                "task_id": None,
                "goal_id": None,
                "proposal_id": None,
                "trace_id": None,
                "mission_id": row["mission_id"],
                "outcome_id": row["outcome_id"],
                "assignment_id": row["assignment_id"],
                "severity": "warning" if row["status"] == "blocked" else "info",
            })
        records = [record for record in records if record.get("timestamp")]
        records.sort(
            key=lambda item: self._parse_activity_timestamp(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        records = self._attach_outcomes_to_activity(self._attach_missions_to_activity(records))
        return {"activity": records[:limit]}

    @staticmethod
    def _activity_room_from_target(target: str | None) -> str | None:
        value = str(target or "")
        return value.removeprefix("room:") if value.startswith("room:") else None

    @staticmethod
    def _activity_summary_subject(value: str | None, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        return text if len(text) <= 90 else f"{text[:87]}..."

    def list_live_activity(
        self,
        limit: int = 50,
        *,
        runtime: str | None = None,
        room: str | None = None,
        event_type: str | None = None,
        mission: str | None = None,
        outcome: str | None = None,
        assignment: str | None = None,
        active_missions: bool = False,
    ) -> dict:
        limit = max(1, min(int(limit), 200))
        scan_limit = min(500, limit * 5)
        runtime_filter = str(runtime or "").strip()
        room_filter = str(room or "").strip().removeprefix("#")
        event_filter = str(event_type or "").strip()
        mission_filter = str(mission or "").strip()
        outcome_filter = str(outcome or "").strip()
        assignment_filter = str(assignment or "").strip()
        records: list[dict] = []
        with self._lock:
            messages = self._conn.execute(
                """
                SELECT message_id, conversation_id, source, target, timestamp, body, metadata_json
                FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            deliveries = self._conn.execute(
                """
                SELECT d.delivery_id, d.adapter_id, d.status, d.ok, d.error, d.created_at,
                       d.duration_ms, m.target, m.conversation_id
                FROM deliveries d
                LEFT JOIN messages m ON m.message_id = d.message_id
                ORDER BY d.created_at DESC, d.delivery_id DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            proposals = self._conn.execute(
                """
                SELECT proposal_id, title, summary, room_id, status, proposed_by, created_at, updated_at
                FROM proposals
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            proposal_events = self._conn.execute(
                """
                SELECT pe.event_id, pe.proposal_id, pe.event_type, pe.actor, pe.created_at,
                       p.title, p.room_id, p.proposed_by
                FROM proposal_events pe
                LEFT JOIN proposals p ON p.proposal_id = pe.proposal_id
                ORDER BY pe.created_at DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            handoffs = self._conn.execute(
                """
                SELECT handoff_id, room_id, task_id, from_agent, to_agent, status, summary, created_at, updated_at
                FROM handoffs
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            decisions = self._conn.execute(
                """
                SELECT decision_id, title, room_id, status, proposed_by, approved_by, created_at, updated_at
                FROM decisions
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            dead_letters = self._conn.execute(
                """
                SELECT dead_letter_id, adapter_id, reason, created_at
                FROM dead_letters
                ORDER BY created_at DESC, dead_letter_id DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            assignment_events = self._conn.execute(
                """
                SELECT ae.event_id, ae.assignment_id, ae.event_type, ae.actor, ae.created_at,
                       a.title, a.status, a.owner_worker, a.mission_id, a.outcome_id, a.room_id
                FROM assignment_events ae
                LEFT JOIN assignments a ON a.assignment_id = ae.assignment_id
                ORDER BY ae.created_at DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
        for row in messages:
            row_room = self._activity_room_from_target(row["target"])
            actor = str(row["source"] or "unknown")
            target = str(row["target"] or "")
            records.append({
                "activity_id": row["message_id"],
                "runtime": actor if actor != "operator" and not actor.startswith("synkraken-") else None,
                "room": row_room,
                "event_type": "message",
                "timestamp": row["timestamp"],
                "summary": f"{actor} posted in #{row_room}" if row_room else f"{actor} sent message to {target}",
                "actor": actor,
                "actor_type": "operator" if actor == "operator" else "system" if actor.startswith("synkraken-") else "runtime",
                "severity": "info",
                "trace_id": row["conversation_id"],
            })
        for row in deliveries:
            row_room = self._activity_room_from_target(row["target"])
            actor = str(row["adapter_id"] or "runtime")
            status = str(row["status"] or "")
            ok = bool(row["ok"])
            if status == "timeout" or str(row["error"] or "").lower().find("timeout") >= 0:
                summary = f"{actor} timeout"
                kind = "timeout"
                severity = "warning"
            elif ok:
                summary = f"{actor} replied in #{row_room}" if row_room else f"{actor} replied"
                kind = "reply"
                severity = "info"
            else:
                summary = f"{actor} delivery failed"
                kind = "delivery_failed"
                severity = "warning"
            records.append({
                "activity_id": str(row["delivery_id"]),
                "runtime": actor,
                "room": row_room,
                "event_type": kind,
                "timestamp": row["created_at"],
                "summary": summary,
                "actor": actor,
                "actor_type": "runtime",
                "severity": severity,
                "trace_id": row["conversation_id"],
            })
        for row in proposals:
            actor = str(row["proposed_by"] or "runtime")
            title = self._activity_summary_subject(row["title"] or row["summary"], "proposal")
            status = str(row["status"] or "proposed")
            records.append({
                "activity_id": row["proposal_id"],
                "runtime": actor if actor != "operator" else None,
                "room": row["room_id"],
                "event_type": "proposal",
                "timestamp": row["updated_at"] or row["created_at"],
                "summary": f"{actor} created proposal: {title}" if status == "proposed" else f"{actor} updated proposal: {title}",
                "actor": actor,
                "actor_type": "operator" if actor == "operator" else "runtime",
                "severity": "notice" if status == "proposed" else "info",
                "proposal_id": row["proposal_id"],
            })
        for row in proposal_events:
            actor = str(row["actor"] or "operator")
            raw_type = str(row["event_type"] or "proposal_event")
            title = self._activity_summary_subject(row["title"], "proposal")
            if actor == "operator" and raw_type in {"approved", "proposal_approved", "approve"}:
                summary = f"Operator approved proposal: {title}"
                kind = "proposal_approved"
            elif actor == "operator" and raw_type in {"rejected", "proposal_rejected", "reject"}:
                summary = f"Operator rejected proposal: {title}"
                kind = "proposal_rejected"
            elif actor == "operator" and raw_type in {"executed", "proposal_executed", "execute"}:
                summary = f"Operator executed proposal: {title}"
                kind = "proposal_executed"
            elif raw_type in {"proposed", "proposal_created", "created"}:
                summary = f"{actor} created proposal: {title}"
                kind = "proposal"
            else:
                summary = f"{actor} recorded proposal event: {raw_type}"
                kind = raw_type
            records.append({
                "activity_id": row["event_id"],
                "runtime": None if actor == "operator" else actor,
                "room": row["room_id"],
                "event_type": kind,
                "timestamp": row["created_at"],
                "summary": summary,
                "actor": actor,
                "actor_type": "operator" if actor == "operator" else "runtime",
                "severity": "info" if "approved" in kind or "executed" in kind else "notice",
                "proposal_id": row["proposal_id"],
            })
        for row in handoffs:
            actor = str(row["from_agent"] or "runtime")
            records.append({
                "activity_id": row["handoff_id"],
                "runtime": actor,
                "room": row["room_id"],
                "event_type": "handoff",
                "timestamp": row["updated_at"] or row["created_at"],
                "summary": f"{actor} handed off to {row['to_agent']}",
                "actor": actor,
                "actor_type": "runtime",
                "severity": "info" if row["status"] != "rejected" else "warning",
                "task_id": row["task_id"],
            })
        for row in decisions:
            actor = str(row["approved_by"] or row["proposed_by"] or "operator")
            records.append({
                "activity_id": row["decision_id"],
                "runtime": None if actor == "operator" else actor,
                "room": row["room_id"],
                "event_type": "decision",
                "timestamp": row["updated_at"] or row["created_at"],
                "summary": f"Decision {row['status']}: {self._activity_summary_subject(row['title'], 'decision')}",
                "actor": actor,
                "actor_type": "operator" if actor == "operator" else "runtime",
                "severity": "info" if row["status"] == "approved" else "notice",
            })
        for row in dead_letters:
            actor = str(row["adapter_id"] or "runtime")
            records.append({
                "activity_id": str(row["dead_letter_id"]),
                "runtime": actor,
                "room": None,
                "event_type": "dead_letter",
                "timestamp": row["created_at"],
                "summary": f"{actor} dead letter: {row['reason']}",
                "actor": actor,
                "actor_type": "runtime",
                "severity": "warning",
                "incident_id": str(row["dead_letter_id"]),
            })
        for row in assignment_events:
            actor = str(row["actor"] or "operator")
            raw_type = str(row["event_type"] or "assignment")
            title = self._activity_summary_subject(row["title"], "assignment")
            records.append({
                "activity_id": row["event_id"],
                "runtime": None if actor == "operator" else actor,
                "room": row["room_id"],
                "event_type": f"assignment_{raw_type}" if not raw_type.startswith("assignment") else raw_type,
                "timestamp": row["created_at"],
                "summary": f"Assignment {raw_type}: {title}",
                "actor": actor,
                "actor_type": "operator" if actor == "operator" else "runtime",
                "severity": "warning" if row["status"] == "blocked" else "info",
                "mission_id": row["mission_id"],
                "mission_ids": [row["mission_id"]] if row["mission_id"] else [],
                "outcome_id": row["outcome_id"],
                "outcome_ids": [row["outcome_id"]] if row["outcome_id"] else [],
                "assignment_id": row["assignment_id"],
                "assignment_ids": [row["assignment_id"]] if row["assignment_id"] else [],
            })
        records = self._attach_outcomes_to_activity(self._attach_missions_to_activity(records))
        active_mission_ids: set[str] = set()
        if active_missions:
            with self._lock:
                active_mission_ids = {
                    str(row["mission_id"])
                    for row in self._conn.execute("SELECT mission_id FROM missions WHERE status = 'active'").fetchall()
                }
        filtered = []
        for record in records:
            if not record.get("timestamp"):
                continue
            if runtime_filter and record.get("runtime") != runtime_filter and record.get("actor") != runtime_filter:
                continue
            if room_filter and record.get("room") != room_filter:
                continue
            if event_filter and record.get("event_type") != event_filter:
                continue
            if mission_filter and mission_filter not in (record.get("mission_ids") or []):
                continue
            if outcome_filter and outcome_filter not in (record.get("outcome_ids") or []):
                continue
            if assignment_filter and assignment_filter not in (record.get("assignment_ids") or []) and record.get("assignment_id") != assignment_filter:
                continue
            if active_missions and not (active_mission_ids & set(record.get("mission_ids") or [])):
                continue
            filtered.append(record)
        filtered.sort(
            key=lambda item: self._parse_activity_timestamp(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        now = datetime.now(timezone.utc)
        recent_window = [
            item for item in filtered
            if (self._presence_seconds_since(now, item.get("timestamp")) or 10**9) <= 900
        ]
        active_now = sorted({
            str(item.get("runtime"))
            for item in recent_window
            if item.get("runtime")
        })
        return {
            "activity": filtered[:limit],
            "summary": {
                "active_workers": len(active_now),
                "active_worker_ids": active_now,
                "recent_events": len(recent_window),
                "last_activity_at": filtered[0]["timestamp"] if filtered else None,
                "last_activity_seconds_ago": self._presence_seconds_since(now, filtered[0]["timestamp"]) if filtered else None,
            },
            "filters": {
                "runtime": runtime_filter or None,
                "room": room_filter or None,
                "event_type": event_filter or None,
                "mission": mission_filter or None,
                "outcome": outcome_filter or None,
                "assignment": assignment_filter or None,
                "active_missions": active_missions,
            },
        }

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

    def list_canvas_relationships(self, limit: int = 500) -> list[dict]:
        relationships: list[dict] = []
        seen: set[str] = set()

        def tone_for_status(status: str | None, risk: str | None = None) -> str:
            clean_status = str(status or "").lower()
            clean_risk = str(risk or "").lower()
            if clean_status in {"rejected", "cancelled", "expired", "failed", "timeout"}:
                return "failing"
            if clean_risk in {"high", "critical"}:
                return "failing"
            if clean_status in {"proposed", "approved"}:
                return "pending"
            if clean_risk in {"medium", "moderate"}:
                return "pending"
            return "normal"

        def add(
            *,
            source_type: str,
            source_id: str,
            target_type: str,
            target_id: str,
            kind: str,
            tone: str,
            evidence: dict,
            observed_at: str | None,
        ) -> None:
            if not source_id or not target_id:
                return
            relationship_id = f"{source_type}:{source_id}:{kind}:{target_type}:{target_id}"
            if relationship_id in seen:
                return
            seen.add(relationship_id)
            relationships.append({
                "id": relationship_id,
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
                "kind": kind,
                "tone": tone,
                "status": tone,
                "evidence": evidence,
                "observed_at": observed_at,
            })

        proposals = self.list_proposals(limit=limit)
        for proposal in proposals:
            proposal_id = str(proposal.get("proposal_id") or "")
            tone = tone_for_status(str(proposal.get("status") or ""), str(proposal.get("risk_level") or ""))
            evidence = {
                "table": "proposals",
                "proposal_id": proposal_id,
                "status": proposal.get("status"),
                "risk_level": proposal.get("risk_level"),
            }
            add(
                source_type="proposal-detail",
                source_id=proposal_id,
                target_type="runtime",
                target_id=str(proposal.get("proposed_by") or ""),
                kind="proposed_by",
                tone=tone,
                evidence=evidence,
                observed_at=str(proposal.get("created_at") or ""),
            )
            add(
                source_type="proposal-queue",
                source_id="primary",
                target_type="proposal-detail",
                target_id=proposal_id,
                kind="contains_proposal",
                tone=tone,
                evidence=evidence,
                observed_at=str(proposal.get("created_at") or ""),
            )
            room_id = str(proposal.get("room_id") or "")
            if room_id:
                add(
                    source_type="room",
                    source_id=room_id,
                    target_type="proposal-detail",
                    target_id=proposal_id,
                    kind="has_proposal",
                    tone=tone,
                    evidence=evidence | {"room_id": room_id},
                    observed_at=str(proposal.get("created_at") or ""),
                )
                add(
                    source_type="proposal-detail",
                    source_id=proposal_id,
                    target_type="room",
                    target_id=room_id,
                    kind="in_room",
                    tone=tone,
                    evidence=evidence | {"room_id": room_id},
                    observed_at=str(proposal.get("created_at") or ""),
                )
            for message_id in proposal.get("linked_message_ids") or []:
                add(
                    source_type="proposal-detail",
                    source_id=proposal_id,
                    target_type="trace",
                    target_id=str(message_id),
                    kind="linked_message_trace",
                    tone=tone,
                    evidence=evidence | {"message_id": message_id},
                    observed_at=str(proposal.get("created_at") or ""),
                )

        for dead_letter in self.list_dead_letters(limit=limit).get("dead_letters", []):
            dead_letter_id = str(dead_letter.get("dead_letter_id") or "")
            message_id = str(dead_letter.get("message_id") or "")
            adapter_id = str(dead_letter.get("adapter_id") or "")
            evidence = {
                "table": "dead_letters",
                "dead_letter_id": dead_letter_id,
                "message_id": message_id,
                "adapter_id": adapter_id,
                "reason": dead_letter.get("reason"),
            }
            add(
                source_type="dead-letter",
                source_id="primary",
                target_type="trace",
                target_id=message_id,
                kind="failed_message_trace",
                tone="failing",
                evidence=evidence,
                observed_at=str(dead_letter.get("created_at") or ""),
            )
            add(
                source_type="trace",
                source_id=message_id,
                target_type="dead-letter",
                target_id="primary",
                kind="has_dead_letter",
                tone="failing",
                evidence=evidence,
                observed_at=str(dead_letter.get("created_at") or ""),
            )
            add(
                source_type="dead-letter",
                source_id="primary",
                target_type="runtime",
                target_id=adapter_id,
                kind="failed_runtime",
                tone="failing",
                evidence=evidence,
                observed_at=str(dead_letter.get("created_at") or ""),
            )

        for reputation in self.get_all_runtime_reputations():
            status = str(reputation.get("health_status") or "healthy")
            if status not in {"degraded", "unstable", "failing"}:
                continue
            runtime_id = str(reputation.get("runtime_id") or "")
            tone = "failing" if status in {"unstable", "failing"} else "pending"
            add(
                source_type="runtime",
                source_id=runtime_id,
                target_type="incident",
                target_id="primary",
                kind="has_runtime_incident",
                tone=tone,
                evidence={
                    "table": "runtime_reputation",
                    "runtime_id": runtime_id,
                    "health_status": status,
                    "incident_summary": reputation.get("incident_summary"),
                },
                observed_at=str(reputation.get("updated_at") or reputation.get("last_failure") or ""),
            )

        anchor = self.latest_incident_anchor()
        if anchor:
            message_id = str(anchor.get("message_id") or "")
            adapter_id = str(anchor.get("adapter_id") or "")
            tone = "failing"
            evidence = {"source": "latest_incident_anchor"} | anchor
            add(
                source_type="incident",
                source_id="primary",
                target_type="trace",
                target_id=message_id,
                kind="latest_incident_trace",
                tone=tone,
                evidence=evidence,
                observed_at=str(anchor.get("created_at") or ""),
            )
            add(
                source_type="incident",
                source_id="primary",
                target_type="runtime",
                target_id=adapter_id,
                kind="latest_incident_runtime",
                tone=tone,
                evidence=evidence,
                observed_at=str(anchor.get("created_at") or ""),
            )
            add(
                source_type="incident",
                source_id="primary",
                target_type="dead-letter",
                target_id="primary",
                kind="latest_incident_dead_letter",
                tone=tone,
                evidence=evidence,
                observed_at=str(anchor.get("created_at") or ""),
            )

        for mission in self.list_missions(limit=limit):
            mission_id = str(mission.get("mission_id") or "")
            status = str(mission.get("status") or "")
            tone = "failing" if status == "blocked" else "pending" if status in {"proposed", "review"} else "normal"
            mission_evidence = {
                "table": "missions",
                "mission_id": mission_id,
                "status": status,
                "priority": mission.get("priority"),
            }
            for worker in mission.get("workers") or []:
                add(
                    source_type="mission",
                    source_id=mission_id,
                    target_type="runtime",
                    target_id=str(worker.get("adapter_id") or ""),
                    kind="involves_worker",
                    tone=tone,
                    evidence=mission_evidence | {"adapter_id": worker.get("adapter_id")},
                    observed_at=str(worker.get("linked_at") or mission.get("updated_at") or ""),
                )
            for room in mission.get("rooms") or []:
                add(
                    source_type="mission",
                    source_id=mission_id,
                    target_type="room",
                    target_id=str(room.get("room_name") or ""),
                    kind="uses_room",
                    tone=tone,
                    evidence=mission_evidence | {"room_name": room.get("room_name")},
                    observed_at=str(room.get("linked_at") or mission.get("updated_at") or ""),
                )
            for proposal in mission.get("proposals") or []:
                add(
                    source_type="mission",
                    source_id=mission_id,
                    target_type="proposal-detail",
                    target_id=str(proposal.get("proposal_id") or ""),
                    kind="has_proposal",
                    tone=tone_for_status(str(proposal.get("status") or ""), str(proposal.get("risk_level") or "")),
                    evidence=mission_evidence | {"proposal_id": proposal.get("proposal_id")},
                    observed_at=str(proposal.get("linked_at") or proposal.get("updated_at") or ""),
                )
            for incident in mission.get("incidents") or []:
                add(
                    source_type="mission",
                    source_id=mission_id,
                    target_type="incident",
                    target_id="primary",
                    kind="impacted_by_incident",
                    tone="failing",
                    evidence=mission_evidence | {"incident_id": incident.get("incident_id")},
                    observed_at=str(incident.get("linked_at") or mission.get("updated_at") or ""),
                )
            for outcome in mission.get("outcomes") or []:
                outcome_id = str(outcome.get("outcome_id") or "")
                outcome_status = str(outcome.get("status") or "")
                outcome_tone = "failing" if outcome_status == "blocked" else "pending" if outcome_status in {"not_started", "in_progress", "review"} else "normal"
                outcome_evidence = mission_evidence | {
                    "table": "outcomes",
                    "outcome_id": outcome_id,
                    "outcome_status": outcome_status,
                    "confidence": outcome.get("confidence"),
                }
                add(
                    source_type="mission",
                    source_id=mission_id,
                    target_type="outcome",
                    target_id=outcome_id,
                    kind="has_outcome",
                    tone=outcome_tone,
                    evidence=outcome_evidence,
                    observed_at=str(outcome.get("updated_at") or mission.get("updated_at") or ""),
                )
                for worker in outcome.get("workers") or []:
                    add(
                        source_type="outcome",
                        source_id=outcome_id,
                        target_type="runtime",
                        target_id=str(worker.get("adapter_id") or ""),
                        kind="contributed_by",
                        tone=outcome_tone,
                        evidence=outcome_evidence | {"adapter_id": worker.get("adapter_id")},
                        observed_at=str(worker.get("linked_at") or outcome.get("updated_at") or ""),
                    )
                for proposal in outcome.get("proposals") or []:
                    add(
                        source_type="outcome",
                        source_id=outcome_id,
                        target_type="proposal-detail",
                        target_id=str(proposal.get("proposal_id") or ""),
                        kind="has_proposal",
                        tone=tone_for_status(str(proposal.get("status") or ""), str(proposal.get("risk_level") or "")),
                        evidence=outcome_evidence | {"proposal_id": proposal.get("proposal_id")},
                        observed_at=str(proposal.get("linked_at") or proposal.get("updated_at") or ""),
                    )
                for incident in outcome.get("incidents") or []:
                    add(
                        source_type="outcome",
                        source_id=outcome_id,
                        target_type="incident",
                        target_id="primary",
                        kind="impacted_by_incident",
                        tone="failing",
                        evidence=outcome_evidence | {"incident_id": incident.get("incident_id")},
                        observed_at=str(incident.get("linked_at") or outcome.get("updated_at") or ""),
                    )
                for trace in outcome.get("traces") or []:
                    add(
                        source_type="outcome",
                        source_id=outcome_id,
                        target_type="trace",
                        target_id=str(trace.get("trace_id") or ""),
                        kind="evidenced_by_trace",
                        tone=outcome_tone,
                        evidence=outcome_evidence | {"trace_id": trace.get("trace_id")},
                        observed_at=str(trace.get("linked_at") or outcome.get("updated_at") or ""),
                    )

        for assignment in self.list_assignments(limit=limit):
            assignment_id = str(assignment.get("assignment_id") or "")
            status = str(assignment.get("status") or "")
            tone = "failing" if status == "blocked" else "pending" if status in {"assigned", "in_progress", "waiting", "handoff", "review"} else "normal"
            evidence = {
                "table": "assignments",
                "assignment_id": assignment_id,
                "status": status,
                "owner_worker": assignment.get("owner_worker"),
            }
            mission_id = str(assignment.get("mission_id") or "")
            outcome_id = str(assignment.get("outcome_id") or "")
            owner = str(assignment.get("owner_worker") or "")
            if mission_id:
                add(
                    source_type="mission",
                    source_id=mission_id,
                    target_type="assignment",
                    target_id=assignment_id,
                    kind="has_assignment",
                    tone=tone,
                    evidence=evidence | {"mission_id": mission_id},
                    observed_at=str(assignment.get("updated_at") or ""),
                )
            if outcome_id:
                add(
                    source_type="outcome",
                    source_id=outcome_id,
                    target_type="assignment",
                    target_id=assignment_id,
                    kind="contributes_assignment",
                    tone=tone,
                    evidence=evidence | {"outcome_id": outcome_id},
                    observed_at=str(assignment.get("updated_at") or ""),
                )
            if owner:
                add(
                    source_type="assignment",
                    source_id=assignment_id,
                    target_type="runtime",
                    target_id=owner,
                    kind="owned_by",
                    tone=tone,
                    evidence=evidence | {"owner_worker": owner},
                    observed_at=str(assignment.get("updated_at") or ""),
                )
            for contributor in assignment.get("contributor_workers") or []:
                add(
                    source_type="assignment",
                    source_id=assignment_id,
                    target_type="runtime",
                    target_id=str(contributor),
                    kind="assisted_by",
                    tone=tone,
                    evidence=evidence | {"contributor_worker": contributor},
                    observed_at=str(assignment.get("updated_at") or ""),
                )

        relationships.sort(key=lambda item: (str(item.get("observed_at") or ""), str(item.get("id") or "")), reverse=True)
        return relationships[:limit]

    # ── missions ─────────────────────────────────────────────────────────

    def _mission_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        outcomes = self.list_mission_outcomes(data["mission_id"])
        data["workers"] = self.mission_workers(data["mission_id"])
        data["rooms"] = self._mission_rooms(data["mission_id"])
        data["traces"] = self._mission_traces(data["mission_id"])
        data["incidents"] = self.mission_incidents(data["mission_id"])
        data["proposals"] = self.mission_proposals(data["mission_id"])
        data["relationships"] = self._mission_relationships(data["mission_id"])
        data["activity"] = self.mission_activity(data["mission_id"], limit=8) or []
        data["outcomes"] = outcomes
        data["assignments"] = self.mission_assignments(data["mission_id"]) or []
        completed = sum(1 for outcome in outcomes if outcome.get("status") == "completed")
        total = len(outcomes)
        data["progress"] = {
            "completed": completed,
            "total": total,
            "percent": int((completed / total) * 100) if total else 0,
        }
        return data

    def create_mission(
        self,
        *,
        mission_id: str,
        title: str,
        description: str = "",
        status: str = "proposed",
        priority: str = "medium",
        created_at: str | None = None,
        updated_at: str | None = None,
        owner: str = "",
        goal: str = "",
        outcome: str = "",
        risk_level: str = "medium",
        workers: list[str] | None = None,
        rooms: list[str] | None = None,
        traces: list[str] | None = None,
        incidents: list[str] | None = None,
        proposals: list[str] | None = None,
    ) -> dict:
        if status not in MISSION_STATUSES:
            raise ValueError(f"invalid mission status: {status}")
        if priority not in MISSION_PRIORITIES:
            raise ValueError(f"invalid mission priority: {priority}")
        now = created_at or utc_now_iso()
        updated = updated_at or now
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO missions (
                    mission_id, title, description, status, priority,
                    created_at, updated_at, owner, goal, outcome, risk_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mission_id, title, description, status, priority, now, updated, owner, goal, outcome, risk_level),
            )
            for adapter_id in workers or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mission_workers (mission_id, adapter_id, role, linked_at) VALUES (?, ?, '', ?)",
                    (mission_id, adapter_id, updated),
                )
            for room_name in rooms or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mission_rooms (mission_id, room_name, linked_at) VALUES (?, ?, ?)",
                    (mission_id, room_name, updated),
                )
            for trace_id in traces or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mission_traces (mission_id, trace_id, linked_at) VALUES (?, ?, ?)",
                    (mission_id, trace_id, updated),
                )
            for incident_id in incidents or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mission_incidents (mission_id, incident_id, incident_type, linked_at) VALUES (?, ?, '', ?)",
                    (mission_id, incident_id, updated),
                )
            for proposal_id in proposals or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO mission_proposals (mission_id, proposal_id, linked_at) VALUES (?, ?, ?)",
                    (mission_id, proposal_id, updated),
                )
            self._conn.execute(
                """
                INSERT INTO mission_events (event_id, mission_id, event_type, actor, details, created_at)
                VALUES (?, ?, 'mission_recorded', 'system', ?, ?)
                """,
                (str(uuid.uuid4()), mission_id, title, now),
            )
        mission = self.get_mission(mission_id)
        assert mission is not None
        return mission

    def list_missions(self, status: str | None = None, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        sql = "SELECT * FROM missions"
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC, created_at DESC, mission_id ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._mission_from_row(row) for row in rows]

    def get_mission(self, mission_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
        return self._mission_from_row(row) if row else None

    def mission_summary(self) -> dict:
        missions = self.list_missions(limit=500)
        counts = {status: 0 for status in sorted(MISSION_STATUSES)}
        for mission in missions:
            status = str(mission.get("status") or "")
            counts[status] = counts.get(status, 0) + 1
        active = [mission for mission in missions if mission.get("status") == "active"]
        blocked = [mission for mission in missions if mission.get("status") == "blocked"]
        review = [mission for mission in missions if mission.get("status") == "review"]
        completed = [mission for mission in missions if mission.get("status") == "completed"]
        priority_source = blocked or review or active or missions[:1]
        return {
            "total": len(missions),
            "counts": counts,
            "active_missions": len(active),
            "blocked_missions": len(blocked),
            "review_missions": len(review),
            "completed_missions": len(completed),
            "highest_priority": priority_source[0]["title"] if priority_source else "No missions recorded.",
            "missions": missions[:12],
        }

    def _mission_rooms(self, mission_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT room_name, linked_at FROM mission_rooms WHERE mission_id = ? ORDER BY room_name ASC",
                (mission_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _mission_traces(self, mission_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT trace_id, linked_at FROM mission_traces WHERE mission_id = ? ORDER BY linked_at DESC, trace_id ASC",
                (mission_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mission_workers(self, mission_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT mw.adapter_id, mw.role, mw.linked_at, a.runtime_name, a.status, a.current_room
                FROM mission_workers mw
                LEFT JOIN agents a ON a.adapter_id = mw.adapter_id
                WHERE mw.mission_id = ?
                ORDER BY mw.adapter_id ASC
                """,
                (mission_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mission_proposals(self, mission_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT p.*, mp.linked_at
                FROM mission_proposals mp
                LEFT JOIN proposals p ON p.proposal_id = mp.proposal_id
                WHERE mp.mission_id = ?
                ORDER BY COALESCE(p.updated_at, mp.linked_at) DESC
                """,
                (mission_id,),
            ).fetchall()
        return [self._proposal_from_row(row) | {"linked_at": row["linked_at"]} for row in rows if row["proposal_id"]]

    def mission_incidents(self, mission_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT mission_id, incident_id, incident_type, linked_at
                FROM mission_incidents
                WHERE mission_id = ?
                ORDER BY linked_at DESC, incident_id ASC
                """,
                (mission_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _mission_relationships(self, mission_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT relationship_id, mission_id, target_type, target_id, kind, evidence_json, observed_at
                FROM mission_relationships
                WHERE mission_id = ?
                ORDER BY observed_at DESC, relationship_id ASC
                """,
                (mission_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
            except json.JSONDecodeError:
                item["evidence"] = {}
            result.append(item)
        return result

    def _mission_link_index(self) -> dict[str, dict[str, list[str]]]:
        index: dict[str, dict[str, list[str]]] = {"worker": {}, "room": {}, "trace": {}, "incident": {}, "proposal": {}}
        with self._lock:
            workers = self._conn.execute("SELECT mission_id, adapter_id FROM mission_workers").fetchall()
            rooms = self._conn.execute("SELECT mission_id, room_name FROM mission_rooms").fetchall()
            traces = self._conn.execute("SELECT mission_id, trace_id FROM mission_traces").fetchall()
            incidents = self._conn.execute("SELECT mission_id, incident_id FROM mission_incidents").fetchall()
            proposals = self._conn.execute("SELECT mission_id, proposal_id FROM mission_proposals").fetchall()
        for row in workers:
            index["worker"].setdefault(str(row["adapter_id"]), []).append(str(row["mission_id"]))
        for row in rooms:
            index["room"].setdefault(str(row["room_name"]), []).append(str(row["mission_id"]))
        for row in traces:
            index["trace"].setdefault(str(row["trace_id"]), []).append(str(row["mission_id"]))
        for row in incidents:
            index["incident"].setdefault(str(row["incident_id"]), []).append(str(row["mission_id"]))
        for row in proposals:
            index["proposal"].setdefault(str(row["proposal_id"]), []).append(str(row["mission_id"]))
        return index

    def _attach_missions_to_activity(self, records: list[dict]) -> list[dict]:
        index = self._mission_link_index()
        for record in records:
            mission_ids: list[str] = [str(record["mission_id"])] if record.get("mission_id") else []
            for key, value in (
                ("worker", record.get("runtime") or record.get("actor")),
                ("room", record.get("room") or record.get("room_id")),
                ("trace", record.get("trace_id")),
                ("incident", record.get("incident_id") or record.get("dead_letter_id")),
                ("proposal", record.get("proposal_id")),
            ):
                if value is not None:
                    mission_ids.extend(index[key].get(str(value), []))
            unique = sorted(dict.fromkeys(mission_ids))
            record["mission_ids"] = unique
            record["mission_id"] = unique[0] if unique else None
        return records

    def mission_activity(self, mission_id: str, limit: int = 50) -> list[dict] | None:
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
        if exists is None:
            return None
        return self.list_live_activity(limit=max(limit, 100), mission=mission_id)["activity"][:limit]

    def current_mission_for_worker(self, adapter_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT m.mission_id, m.title, m.status, m.priority, m.updated_at
                FROM mission_workers mw
                JOIN missions m ON m.mission_id = mw.mission_id
                WHERE mw.adapter_id = ?
                  AND m.status IN ('active', 'blocked', 'review')
                ORDER BY
                  CASE m.status WHEN 'blocked' THEN 0 WHEN 'active' THEN 1 WHEN 'review' THEN 2 ELSE 3 END,
                  m.updated_at DESC
                LIMIT 1
                """,
                (adapter_id,),
            ).fetchone()
        return dict(row) if row else None

    def current_mission_for_room(self, room_name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT m.mission_id, m.title, m.status, m.priority, m.updated_at
                FROM mission_rooms mr
                JOIN missions m ON m.mission_id = mr.mission_id
                WHERE mr.room_name = ?
                  AND m.status IN ('active', 'blocked', 'review')
                ORDER BY
                  CASE m.status WHEN 'blocked' THEN 0 WHEN 'active' THEN 1 WHEN 'review' THEN 2 ELSE 3 END,
                  m.updated_at DESC
                LIMIT 1
                """,
                (room_name,),
            ).fetchone()
        return dict(row) if row else None

    # ── outcomes ─────────────────────────────────────────────────────────

    def _outcome_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        outcome_id = str(data["outcome_id"])
        data["workers"] = self.outcome_workers(outcome_id)
        data["traces"] = self._outcome_traces(outcome_id)
        data["incidents"] = self.outcome_incidents(outcome_id)
        data["proposals"] = self.outcome_proposals(outcome_id)
        data["relationships"] = self._outcome_relationships(outcome_id)
        data["activity"] = self.outcome_activity(outcome_id, limit=8) or []
        data["assignments"] = self.outcome_assignments(outcome_id) or []
        data["evidence_count"] = len(data["traces"]) + len(data["relationships"])
        data["proposal_count"] = len(data["proposals"])
        data["incident_count"] = len(data["incidents"])
        return data

    def create_outcome(
        self,
        *,
        outcome_id: str,
        mission_id: str,
        title: str,
        description: str = "",
        status: str = "not_started",
        confidence: str = "medium",
        owner: str = "",
        created_at: str | None = None,
        updated_at: str | None = None,
        completed_at: str | None = None,
        workers: list[str] | None = None,
        traces: list[str] | None = None,
        incidents: list[str] | None = None,
        proposals: list[str] | None = None,
    ) -> dict:
        if status not in OUTCOME_STATUSES:
            raise ValueError(f"invalid outcome status: {status}")
        if confidence not in OUTCOME_CONFIDENCE:
            raise ValueError(f"invalid outcome confidence: {confidence}")
        now = created_at or utc_now_iso()
        updated = updated_at or now
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM missions WHERE mission_id = ?", (mission_id,)).fetchone() is None:
                raise ValueError(f"mission not found: {mission_id}")
            self._conn.execute(
                """
                INSERT OR REPLACE INTO outcomes (
                    outcome_id, mission_id, title, description, status,
                    confidence, owner, created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (outcome_id, mission_id, title, description, status, confidence, owner, now, updated, completed_at),
            )
            for adapter_id in workers or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO outcome_workers (outcome_id, adapter_id, role, linked_at) VALUES (?, ?, '', ?)",
                    (outcome_id, adapter_id, updated),
                )
            for trace_id in traces or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO outcome_traces (outcome_id, trace_id, linked_at) VALUES (?, ?, ?)",
                    (outcome_id, trace_id, updated),
                )
            for incident_id in incidents or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO outcome_incidents (outcome_id, incident_id, incident_type, linked_at) VALUES (?, ?, '', ?)",
                    (outcome_id, incident_id, updated),
                )
            for proposal_id in proposals or []:
                self._conn.execute(
                    "INSERT OR REPLACE INTO outcome_proposals (outcome_id, proposal_id, linked_at) VALUES (?, ?, ?)",
                    (outcome_id, proposal_id, updated),
                )
            self._conn.execute(
                """
                INSERT INTO outcome_events (event_id, outcome_id, event_type, actor, details, created_at)
                VALUES (?, ?, 'outcome_recorded', 'system', ?, ?)
                """,
                (str(uuid.uuid4()), outcome_id, title, now),
            )
        outcome = self.get_outcome(outcome_id)
        assert outcome is not None
        return outcome

    def list_outcomes(self, status: str | None = None, mission_id: str | None = None, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        clauses = []
        params: list[object] = []
        if status:
            clauses.append("o.status = ?")
            params.append(status)
        if mission_id:
            clauses.append("o.mission_id = ?")
            params.append(mission_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT o.*, m.title AS mission_title, m.status AS mission_status
                FROM outcomes o
                LEFT JOIN missions m ON m.mission_id = o.mission_id
                {where}
                ORDER BY o.updated_at DESC, o.created_at DESC, o.outcome_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._outcome_from_row(row) for row in rows]

    def get_outcome(self, outcome_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT o.*, m.title AS mission_title, m.status AS mission_status
                FROM outcomes o
                LEFT JOIN missions m ON m.mission_id = o.mission_id
                WHERE o.outcome_id = ?
                """,
                (outcome_id,),
            ).fetchone()
        return self._outcome_from_row(row) if row else None

    def list_mission_outcomes(self, mission_id: str, limit: int = 100) -> list[dict]:
        return self.list_outcomes(mission_id=mission_id, limit=limit)

    def outcome_summary(self) -> dict:
        outcomes = self.list_outcomes(limit=500)
        counts = {status: 0 for status in sorted(OUTCOME_STATUSES)}
        for outcome in outcomes:
            status = str(outcome.get("status") or "")
            counts[status] = counts.get(status, 0) + 1
        priority_source = [outcome for outcome in outcomes if outcome.get("status") in {"blocked", "review", "in_progress"}] or outcomes[:1]
        return {
            "total": len(outcomes),
            "counts": counts,
            "completed": counts.get("completed", 0),
            "in_progress": counts.get("in_progress", 0),
            "review": counts.get("review", 0),
            "blocked": counts.get("blocked", 0),
            "highest_priority": priority_source[0]["title"] if priority_source else "No outcomes recorded.",
            "outcomes": outcomes[:12],
        }

    def _outcome_traces(self, outcome_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT trace_id, linked_at FROM outcome_traces WHERE outcome_id = ? ORDER BY linked_at DESC, trace_id ASC",
                (outcome_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def outcome_workers(self, outcome_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ow.adapter_id, ow.role, ow.linked_at, a.runtime_name, a.status, a.current_room
                FROM outcome_workers ow
                LEFT JOIN agents a ON a.adapter_id = ow.adapter_id
                WHERE ow.outcome_id = ?
                ORDER BY ow.adapter_id ASC
                """,
                (outcome_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def outcome_proposals(self, outcome_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT p.*, op.linked_at
                FROM outcome_proposals op
                LEFT JOIN proposals p ON p.proposal_id = op.proposal_id
                WHERE op.outcome_id = ?
                ORDER BY COALESCE(p.updated_at, op.linked_at) DESC
                """,
                (outcome_id,),
            ).fetchall()
        return [self._proposal_from_row(row) | {"linked_at": row["linked_at"]} for row in rows if row["proposal_id"]]

    def outcome_incidents(self, outcome_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT outcome_id, incident_id, incident_type, linked_at
                FROM outcome_incidents
                WHERE outcome_id = ?
                ORDER BY linked_at DESC, incident_id ASC
                """,
                (outcome_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _outcome_relationships(self, outcome_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT relationship_id, outcome_id, target_type, target_id, kind, evidence_json, observed_at
                FROM outcome_relationships
                WHERE outcome_id = ?
                ORDER BY observed_at DESC, relationship_id ASC
                """,
                (outcome_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
            except json.JSONDecodeError:
                item["evidence"] = {}
            result.append(item)
        return result

    def _outcome_link_index(self) -> dict[str, dict[str, list[str]]]:
        index: dict[str, dict[str, list[str]]] = {"worker": {}, "trace": {}, "incident": {}, "proposal": {}, "mission": {}}
        with self._lock:
            workers = self._conn.execute("SELECT outcome_id, adapter_id FROM outcome_workers").fetchall()
            traces = self._conn.execute("SELECT outcome_id, trace_id FROM outcome_traces").fetchall()
            incidents = self._conn.execute("SELECT outcome_id, incident_id FROM outcome_incidents").fetchall()
            proposals = self._conn.execute("SELECT outcome_id, proposal_id FROM outcome_proposals").fetchall()
            outcomes = self._conn.execute("SELECT outcome_id, mission_id FROM outcomes").fetchall()
        for row in workers:
            index["worker"].setdefault(str(row["adapter_id"]), []).append(str(row["outcome_id"]))
        for row in traces:
            index["trace"].setdefault(str(row["trace_id"]), []).append(str(row["outcome_id"]))
        for row in incidents:
            index["incident"].setdefault(str(row["incident_id"]), []).append(str(row["outcome_id"]))
        for row in proposals:
            index["proposal"].setdefault(str(row["proposal_id"]), []).append(str(row["outcome_id"]))
        for row in outcomes:
            index["mission"].setdefault(str(row["mission_id"]), []).append(str(row["outcome_id"]))
        return index

    def _attach_outcomes_to_activity(self, records: list[dict]) -> list[dict]:
        index = self._outcome_link_index()
        for record in records:
            outcome_ids: list[str] = [str(record["outcome_id"])] if record.get("outcome_id") else []
            for key, value in (
                ("worker", record.get("runtime") or record.get("actor")),
                ("trace", record.get("trace_id")),
                ("incident", record.get("incident_id") or record.get("dead_letter_id")),
                ("proposal", record.get("proposal_id")),
                ("mission", record.get("mission_id")),
            ):
                if value is not None:
                    outcome_ids.extend(index[key].get(str(value), []))
            unique = sorted(dict.fromkeys(outcome_ids))
            record["outcome_ids"] = unique
            record["outcome_id"] = unique[0] if unique else None
        return records

    def outcome_activity(self, outcome_id: str, limit: int = 50) -> list[dict] | None:
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM outcomes WHERE outcome_id = ?", (outcome_id,)).fetchone()
        if exists is None:
            return None
        return self.list_live_activity(limit=max(limit, 100), outcome=outcome_id)["activity"][:limit]

    def current_outcome_for_worker(self, adapter_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT o.outcome_id, o.mission_id, o.title, o.status, o.confidence, o.updated_at,
                       m.title AS mission_title
                FROM outcome_workers ow
                JOIN outcomes o ON o.outcome_id = ow.outcome_id
                LEFT JOIN missions m ON m.mission_id = o.mission_id
                WHERE ow.adapter_id = ?
                  AND o.status IN ('in_progress', 'blocked', 'review')
                ORDER BY
                  CASE o.status WHEN 'blocked' THEN 0 WHEN 'review' THEN 1 WHEN 'in_progress' THEN 2 ELSE 3 END,
                  o.updated_at DESC
                LIMIT 1
                """,
                (adapter_id,),
            ).fetchone()
        return dict(row) if row else None

    def current_outcome_for_room(self, room_name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT o.outcome_id, o.mission_id, o.title, o.status, o.confidence, o.updated_at,
                       m.title AS mission_title
                FROM mission_rooms mr
                JOIN outcomes o ON o.mission_id = mr.mission_id
                LEFT JOIN missions m ON m.mission_id = o.mission_id
                WHERE mr.room_name = ?
                  AND o.status IN ('in_progress', 'blocked', 'review')
                ORDER BY
                  CASE o.status WHEN 'blocked' THEN 0 WHEN 'review' THEN 1 WHEN 'in_progress' THEN 2 ELSE 3 END,
                  o.updated_at DESC
                LIMIT 1
                """,
                (room_name,),
            ).fetchone()
        return dict(row) if row else None

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
        data = dict(row)
        if data.get("status") == "peer_approved":
            data["status"] = "approved"
        if not data.get("body"):
            data["body"] = data.get("content") or ""
        if not data.get("title"):
            data["title"] = str(data.get("body") or data.get("content") or "")[:80]
        if not data.get("scope_type"):
            data["scope_type"] = "room" if data.get("room_name") else "global"
        if not data.get("scope_id") and data.get("room_name"):
            data["scope_id"] = data.get("room_name")
        if not data.get("source_type"):
            data["source_type"] = "operator"
        if not data.get("importance"):
            data["importance"] = "medium"
        return data

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
        title: str | None = None,
        body: str | None = None,
        scope_type: str = "global",
        scope_id: str | None = None,
        source_type: str = "operator",
        source_id: str | None = None,
        importance: str = "medium",
        expires_at: str | None = None,
        source_team_run_id: str | None = None,
        source_task_id: str | None = None,
        source_message_id: str | None = None,
    ) -> dict:
        if memory_type not in SHARED_MEMORY_TYPES:
            raise ValueError(f"invalid memory_type: {memory_type}")
        if status not in SHARED_MEMORY_STATUSES:
            raise ValueError(f"invalid memory status: {status}")
        if importance not in SHARED_MEMORY_IMPORTANCE:
            raise ValueError(f"invalid memory importance: {importance}")
        if scope_type not in SHARED_MEMORY_SCOPES:
            raise ValueError(f"invalid memory scope_type: {scope_type}")
        if status == "peer_approved":
            status = "approved"
        body = body if body is not None else content
        title = title or str(body or content)[:80]
        token_cost = max(1, len(content) // 4) if content else 0
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO shared_memory (
                    memory_id, room_name, workspace, memory_type, title, content,
                    body, scope_type, scope_id, source_type, source_id, status,
                    importance, confidence, created_by, created_at, updated_at,
                    expires_at, source_team_run_id,
                    source_task_id, source_message_id, token_cost_estimate,
                    use_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    memory_id,
                    room_name,
                    workspace,
                    memory_type,
                    title,
                    content,
                    body,
                    scope_type,
                    scope_id,
                    source_type,
                    source_id,
                    status,
                    importance,
                    int(confidence),
                    created_by,
                    created_at,
                    created_at,
                    expires_at,
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
                {"memory_type": memory_type, "status": status, "importance": importance, "scope_type": scope_type, "scope_id": scope_id},
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
        memory_type: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        importance: str | None = None,
        room_name: str | None = None,
        workspace: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = []
        params: list[object] = []
        if status:
            if status == "peer_approved":
                status = "approved"
            clauses.append("status = ?")
            params.append(status)
        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if scope_type:
            clauses.append("scope_type = ?")
            params.append(scope_type)
        if scope_id is not None:
            clauses.append("scope_id = ?")
            params.append(scope_id)
        if importance:
            clauses.append("importance = ?")
            params.append(importance)
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
                  CASE status WHEN 'approved' THEN 0 WHEN 'peer_approved' THEN 0 WHEN 'proposed' THEN 1 ELSE 2 END,
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
            "room_name", "workspace", "memory_type", "title", "content", "body",
            "scope_type", "scope_id", "source_type", "source_id", "status",
            "importance", "confidence", "updated_at", "expires_at",
            "reviewed_by", "review_result", "review_reason", "reviewed_at",
            "approved_by", "approved_at", "source_team_run_id", "source_task_id",
            "source_message_id", "token_cost_estimate", "use_count", "last_used_at",
        }
        clean = {key: value for key, value in fields.items() if key in allowed}
        if "memory_type" in clean and clean["memory_type"] not in SHARED_MEMORY_TYPES:
            raise ValueError(f"invalid memory_type: {clean['memory_type']}")
        if "status" in clean and clean["status"] not in SHARED_MEMORY_STATUSES:
            raise ValueError(f"invalid memory status: {clean['status']}")
        if clean.get("status") == "peer_approved":
            clean["status"] = "approved"
        if "importance" in clean and clean["importance"] not in SHARED_MEMORY_IMPORTANCE:
            raise ValueError(f"invalid memory importance: {clean['importance']}")
        if "scope_type" in clean and clean["scope_type"] not in SHARED_MEMORY_SCOPES:
            raise ValueError(f"invalid memory scope_type: {clean['scope_type']}")
        clean.setdefault("updated_at", utc_now_iso())
        if "content" in clean:
            clean["token_cost_estimate"] = max(1, len(str(clean["content"])) // 4) if clean["content"] else 0
            clean.setdefault("body", clean["content"])
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
        return self.select_workforce_memory_context(
            scopes=[("room", room_name)] if room_name else [],
            workspace=workspace,
            max_items=max_items,
            max_chars=max_chars,
            min_confidence=min_confidence,
        )

    def select_workforce_memory_context(
        self,
        *,
        scopes: list[tuple[str, str | None]],
        workspace: str | None,
        max_items: int,
        max_chars: int,
        min_confidence: int = 0,
    ) -> list[dict]:
        active_scopes = [(scope_type, scope_id) for scope_type, scope_id in scopes if scope_type and scope_id]
        clauses = ["status = 'approved'", "confidence >= ?"]
        params: list[object] = [int(min_confidence)]
        scope_clauses = ["scope_type = 'global'"]
        for scope_type, scope_id in active_scopes:
            scope_clauses.append("(scope_type = ? AND scope_id = ?)")
            params.extend([scope_type, scope_id])
        clauses.append(f"({' OR '.join(scope_clauses)})")
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
                  CASE
                    WHEN scope_type = 'assignment' THEN 0
                    WHEN scope_type = 'outcome' THEN 1
                    WHEN scope_type = 'mission' THEN 2
                    WHEN scope_type = 'room' THEN 3
                    WHEN scope_type = 'runtime' THEN 4
                    WHEN scope_type = 'global' THEN 5
                    ELSE 6
                  END AS scope_rank,
                  CASE importance WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END AS importance_rank
                FROM shared_memory
                WHERE {' AND '.join(clauses)}
                ORDER BY scope_rank ASC, importance_rank ASC, COALESCE(approved_at, updated_at, created_at) DESC, created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        selected: list[dict] = []
        used_chars = 0
        for row in rows:
            memory = self._memory_from_row(row)
            line_len = len(f"- {memory.get('memory_id')} {memory.get('title')}: {memory.get('body') or memory.get('content')}")
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
        now = datetime.now(timezone.utc)
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
            room_names = [str(row["name"]) for row in rows]
            live_rows: dict[str, list[sqlite3.Row]] = {}
            for name in room_names:
                live_rows[name] = self._conn.execute(
                    """
                    SELECT source, timestamp, body
                    FROM messages
                    WHERE target = ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                    """,
                    (f"room:{name}",),
                ).fetchall()
        result = []
        for row in rows:
            room = dict(row)
            events = live_rows.get(str(row["name"]), [])
            room["current_mission"] = self.current_mission_for_room(str(row["name"]))
            room["current_outcome"] = self.current_outcome_for_room(str(row["name"]))
            workers: dict[str, int] = {}
            for event in events:
                source = str(event["source"] or "")
                if source and source != "operator" and not source.startswith("synkraken-"):
                    workers[source] = workers.get(source, 0) + 1
            recent_count = 0
            for event in events:
                seconds = self._presence_seconds_since(now, event["timestamp"])
                if seconds is not None and seconds <= 3600:
                    recent_count += 1
            latest = events[0] if events else None
            room["most_active_workers"] = [
                {"runtime": worker, "events": count}
                for worker, count in sorted(workers.items(), key=lambda item: (-item[1], item[0]))[:3]
            ]
            room["last_room_event"] = self._activity_summary_subject(latest["body"], "No room events recorded.") if latest else ""
            room["activity_rate"] = round(recent_count / 60, 2)
            room["activity_rate_label"] = f"{recent_count} events/hour"
            result.append(room)
        return result

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

    def search_room_messages(self, name: str, query: str, limit: int = 50) -> list[dict]:
        target = f"room:{name}"
        needle = f"%{query.strip()}%"
        if not query.strip():
            return self.get_room_messages(name, limit=limit)
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT message_id, conversation_id, source, target, timestamp,
                       message_type, subject, priority, reply_to, hop_count, body, metadata_json
                FROM messages
                WHERE target = ? AND body LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (target, needle, limit),
            ).fetchall()
        return [self._message_from_row(row) for row in reversed(rows)]

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

    # ── proposals ────────────────────────────────────────────────────────

    def _proposal_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        for key in ("linked_decision_ids", "linked_handoff_ids", "linked_message_ids"):
            raw = data.pop(f"{key}_json", "[]") or "[]"
            try:
                data[key] = json.loads(raw)
            except json.JSONDecodeError:
                data[key] = []
        raw_payload = data.pop("execution_payload_json", "{}") or "{}"
        try:
            data["execution_payload"] = json.loads(raw_payload)
        except json.JSONDecodeError:
            data["execution_payload"] = {}
        data["requires_approval"] = bool(data.get("requires_approval"))
        return data

    def create_proposal(
        self,
        *,
        proposal_id: str,
        created_at: str,
        proposal_type: str,
        title: str,
        summary: str,
        details: str,
        proposed_by: str,
        room_id: str | None,
        task_id: str | None,
        goal_id: str | None,
        linked_decision_ids: list[str],
        linked_handoff_ids: list[str],
        linked_message_ids: list[str],
        execution_payload: dict,
        risk_level: str,
        requires_approval: bool,
        approval_reason: str,
    ) -> dict:
        if proposal_type not in PROPOSAL_TYPES:
            raise ValueError(f"invalid proposal_type: {proposal_type}")
        if risk_level not in USAGE_RISKS:
            raise ValueError(f"invalid risk_level: {risk_level}")
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO proposals (
                    proposal_id, created_at, updated_at, status, proposal_type,
                    title, summary, details, proposed_by, room_id, task_id,
                    goal_id, linked_decision_ids_json, linked_handoff_ids_json,
                    linked_message_ids_json, execution_payload_json,
                    risk_level, requires_approval, approval_reason
                ) VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id, created_at, created_at, proposal_type, title,
                    summary, details, proposed_by, room_id, task_id, goal_id,
                    json.dumps(linked_decision_ids, ensure_ascii=False),
                    json.dumps(linked_handoff_ids, ensure_ascii=False),
                    json.dumps(linked_message_ids, ensure_ascii=False),
                    json.dumps(execution_payload, ensure_ascii=False),
                    risk_level, 1 if requires_approval else 0, approval_reason,
                ),
            )
            self._append_proposal_event_locked(
                proposal_id,
                "proposed",
                proposed_by,
                {
                    "proposal_type": proposal_type,
                    "risk_level": risk_level,
                    "requires_approval": requires_approval,
                    "approval_reason": approval_reason,
                },
                created_at,
            )
        self.recompute_runtime_health(proposed_by)
        proposal = self.get_proposal(proposal_id)
        assert proposal is not None
        return proposal

    def get_proposal(self, proposal_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        return self._proposal_from_row(row) if row else None

    def list_proposals(
        self,
        *,
        status: str | None = None,
        room_id: str | None = None,
        task_id: str | None = None,
        goal_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if room_id is not None:
            clauses.append("room_id = ?")
            params.append(room_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if goal_id is not None:
            clauses.append("goal_id = ?")
            params.append(goal_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT *
                FROM proposals
                {where}
                ORDER BY created_at DESC, proposal_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._proposal_from_row(row) for row in rows]

    def update_proposal(self, proposal_id: str, fields: dict, *, actor: str, event_type: str, details: dict | str | None = None) -> dict | None:
        allowed = {
            "status", "updated_at", "approved_by", "rejected_by", "executed_by",
            "executed_at", "rejected_at",
        }
        clean = {key: value for key, value in fields.items() if key in allowed}
        if "status" in clean and clean["status"] not in PROPOSAL_STATUSES:
            raise ValueError(f"invalid proposal status: {clean['status']}")
        if "updated_at" not in clean:
            clean["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            cur = self._conn.execute(
                f"UPDATE proposals SET {assignments} WHERE proposal_id = ?",
                [*clean.values(), proposal_id],
            )
            if cur.rowcount == 0:
                return None
            self._append_proposal_event_locked(
                proposal_id,
                event_type,
                actor,
                details if details is not None else clean,
                str(clean["updated_at"]),
            )
        proposal = self.get_proposal(proposal_id)
        if proposal:
            for actor_id in {
                proposal.get("proposed_by"),
                proposal.get("approved_by"),
                proposal.get("rejected_by"),
                proposal.get("executed_by"),
            }:
                if actor_id:
                    self.recompute_runtime_health(str(actor_id))
        return proposal

    def _append_proposal_event_locked(
        self,
        proposal_id: str,
        event_type: str,
        actor: str,
        details: dict | str | None,
        created_at: str,
    ) -> None:
        detail_text = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
        self._conn.execute(
            """
            INSERT INTO proposal_events (
                event_id, proposal_id, event_type, actor, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), proposal_id, event_type, actor or "system", detail_text, created_at),
        )

    def append_proposal_event(
        self,
        proposal_id: str,
        event_type: str,
        actor: str,
        details: dict | str | None,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone() is None:
                return
            self._append_proposal_event_locked(proposal_id, event_type, actor, details, created_at or utc_now_iso())

    def list_proposal_events(self, proposal_id: str | None = None, limit: int = 100) -> list[dict] | None:
        if proposal_id and self.get_proposal(proposal_id) is None:
            return None
        params: list[object] = []
        where = ""
        if proposal_id:
            where = "WHERE proposal_id = ?"
            params.append(proposal_id)
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT event_id, proposal_id, event_type, actor, details, created_at
                FROM proposal_events
                {where}
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

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

    # ── assignments ───────────────────────────────────────────────────────

    def _assignment_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        assignment_id = str(data["assignment_id"])
        data["id"] = assignment_id
        contributors = self.assignment_contributors(assignment_id)
        data["contributor_workers"] = [item["worker_id"] for item in contributors]
        data["contributors"] = contributors
        data["handoffs"] = self.assignment_handoffs(assignment_id)
        data["proposals"] = self.assignment_proposals(assignment_id)
        data["traces"] = self.assignment_traces(assignment_id)
        data["last_activity"] = self._assignment_last_activity(data)
        mission_id = data.get("mission_id")
        outcome_id = data.get("outcome_id")
        with self._lock:
            mission = self._conn.execute(
                "SELECT mission_id, title, status FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone() if mission_id else None
            outcome = self._conn.execute(
                "SELECT outcome_id, mission_id, title, status FROM outcomes WHERE outcome_id = ?",
                (outcome_id,),
            ).fetchone() if outcome_id else None
        if mission:
            data["mission"] = dict(mission)
        if outcome:
            data["outcome"] = dict(outcome)
        return data

    def _assignment_last_activity(self, assignment: dict) -> str:
        values = [str(assignment.get("updated_at") or assignment.get("created_at") or "")]
        assignment_id = str(assignment.get("assignment_id") or assignment.get("id") or "")
        with self._lock:
            event = self._conn.execute(
                "SELECT MAX(created_at) AS last_at FROM assignment_events WHERE assignment_id = ?",
                (assignment_id,),
            ).fetchone()
            handoff = self._conn.execute(
                "SELECT MAX(created_at) AS last_at FROM handoffs WHERE assignment_id = ?",
                (assignment_id,),
            ).fetchone()
        for row in (event, handoff):
            if row and row["last_at"]:
                values.append(str(row["last_at"]))
        return max(value for value in values if value)

    def _save_assignment_event(
        self,
        assignment_id: str,
        event_type: str,
        actor: str,
        old_value: object | None,
        new_value: object | None,
        details: dict | str | None,
        created_at: str,
    ) -> None:
        detail_text = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else details
        old_text = json.dumps(old_value, ensure_ascii=False) if isinstance(old_value, (dict, list)) else old_value
        new_text = json.dumps(new_value, ensure_ascii=False) if isinstance(new_value, (dict, list)) else new_value
        self._conn.execute(
            """
            INSERT INTO assignment_events (event_id, assignment_id, event_type, actor, old_value, new_value, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), assignment_id, event_type, actor or "operator", old_text, new_text, detail_text, created_at),
        )

    def create_assignment(
        self,
        *,
        assignment_id: str,
        title: str,
        description: str = "",
        status: str = "assigned",
        owner_worker: str,
        contributor_workers: list[str] | None = None,
        mission_id: str | None = None,
        outcome_id: str | None = None,
        room_id: str | None = None,
        actor: str = "operator",
        created_at: str | None = None,
    ) -> dict:
        if status not in ASSIGNMENT_STATUSES:
            raise ValueError(f"invalid assignment status: {status}")
        if not owner_worker:
            raise ValueError("owner_worker required")
        now = created_at or utc_now_iso()
        contributors = [worker for worker in dict.fromkeys(contributor_workers or []) if worker and worker != owner_worker]
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO assignments (
                    assignment_id, title, description, status, owner_worker,
                    mission_id, outcome_id, room_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (assignment_id, title, description or "", status, owner_worker, mission_id, outcome_id, room_id, now, now),
            )
            for worker in contributors:
                self._conn.execute(
                    "INSERT OR IGNORE INTO assignment_contributors (assignment_id, worker_id, linked_at) VALUES (?, ?, ?)",
                    (assignment_id, worker, now),
                )
            self._save_assignment_event(
                assignment_id,
                "created",
                actor,
                None,
                status,
                {"owner_worker": owner_worker, "contributor_workers": contributors},
                now,
            )
        assignment = self.get_assignment(assignment_id)
        assert assignment is not None
        return assignment

    def get_assignment(self, assignment_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM assignments WHERE assignment_id = ?",
                (assignment_id,),
            ).fetchone()
        return self._assignment_from_row(row) if row else None

    def list_assignments(
        self,
        *,
        status: str | None = None,
        owner_worker: str | None = None,
        contributor_worker: str | None = None,
        mission_id: str | None = None,
        outcome_id: str | None = None,
        room_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("a.status = ?")
            params.append(status)
        if owner_worker:
            clauses.append("a.owner_worker = ?")
            params.append(owner_worker)
        if contributor_worker:
            clauses.append("EXISTS (SELECT 1 FROM assignment_contributors ac WHERE ac.assignment_id = a.assignment_id AND ac.worker_id = ?)")
            params.append(contributor_worker)
        if mission_id:
            clauses.append("a.mission_id = ?")
            params.append(mission_id)
        if outcome_id:
            clauses.append("a.outcome_id = ?")
            params.append(outcome_id)
        if room_id:
            clauses.append("a.room_id = ?")
            params.append(room_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT a.* FROM assignments a {where} ORDER BY a.updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._assignment_from_row(row) for row in rows]

    def assignment_summary(self) -> dict:
        assignments = self.list_assignments(limit=1000)
        counts = {status: 0 for status in ASSIGNMENT_STATUSES}
        for assignment in assignments:
            status = str(assignment.get("status") or "")
            if status in counts:
                counts[status] += 1
        return {
            "total": len(assignments),
            "counts": counts,
            "assigned": counts["assigned"],
            "in_progress": counts["in_progress"],
            "waiting": counts["waiting"],
            "blocked": counts["blocked"],
            "review": counts["review"],
            "completed": counts["completed"],
            "assignments": assignments[:25],
        }

    def assignment_contributors(self, assignment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT worker_id, linked_at
                FROM assignment_contributors
                WHERE assignment_id = ?
                ORDER BY linked_at ASC, worker_id ASC
                """,
                (assignment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def assignment_events(self, assignment_id: str) -> list[dict] | None:
        if not self._assignment_exists(assignment_id):
            return None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT event_id, assignment_id, event_type, actor, old_value, new_value, details, created_at
                FROM assignment_events
                WHERE assignment_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (assignment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _assignment_exists(self, assignment_id: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM assignments WHERE assignment_id = ?", (assignment_id,)).fetchone()
        return row is not None

    def update_assignment(
        self,
        assignment_id: str,
        fields: dict,
        *,
        actor: str = "operator",
        updated_at: str | None = None,
    ) -> dict | None:
        before = self.get_assignment(assignment_id)
        if before is None:
            return None
        allowed = {"title", "description", "status", "owner_worker", "mission_id", "outcome_id", "room_id"}
        clean: dict[str, object | None] = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "status" and value not in ASSIGNMENT_STATUSES:
                raise ValueError(f"invalid assignment status: {value}")
            clean[key] = value
        if not clean:
            return before
        now = updated_at or utc_now_iso()
        clean["updated_at"] = now
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE assignments SET {assignments} WHERE assignment_id = ?",
                [*clean.values(), assignment_id],
            )
            if "owner_worker" in clean:
                self._conn.execute(
                    "DELETE FROM assignment_contributors WHERE assignment_id = ? AND worker_id = ?",
                    (assignment_id, clean["owner_worker"]),
                )
            self._save_assignment_event(assignment_id, "updated", actor, before, clean, clean, now)
        return self.get_assignment(assignment_id)

    def update_assignment_status(self, assignment_id: str, status: str, *, actor: str = "operator") -> dict | None:
        before = self.get_assignment(assignment_id)
        updated = self.update_assignment(assignment_id, {"status": status}, actor=actor)
        if updated and before:
            with self._lock, self._conn:
                self._save_assignment_event(assignment_id, f"marked_{status}", actor, before.get("status"), status, None, utc_now_iso())
        return updated

    def set_assignment_owner(self, assignment_id: str, owner_worker: str, *, actor: str = "operator") -> dict | None:
        return self.update_assignment(assignment_id, {"owner_worker": owner_worker}, actor=actor)

    def add_assignment_contributor(self, assignment_id: str, worker_id: str, *, actor: str = "operator") -> dict | None:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            return None
        if worker_id == assignment.get("owner_worker"):
            return assignment
        now = utc_now_iso()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO assignment_contributors (assignment_id, worker_id, linked_at) VALUES (?, ?, ?)",
                (assignment_id, worker_id, now),
            )
            self._conn.execute("UPDATE assignments SET updated_at = ? WHERE assignment_id = ?", (now, assignment_id))
            if cur.rowcount:
                self._save_assignment_event(assignment_id, "contributor_added", actor, None, worker_id, None, now)
        return self.get_assignment(assignment_id)

    def remove_assignment_contributor(self, assignment_id: str, worker_id: str, *, actor: str = "operator") -> dict | None:
        if not self._assignment_exists(assignment_id):
            return None
        now = utc_now_iso()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM assignment_contributors WHERE assignment_id = ? AND worker_id = ?",
                (assignment_id, worker_id),
            )
            self._conn.execute("UPDATE assignments SET updated_at = ? WHERE assignment_id = ?", (now, assignment_id))
            if cur.rowcount:
                self._save_assignment_event(assignment_id, "contributor_removed", actor, worker_id, None, None, now)
        return self.get_assignment(assignment_id)

    def assignment_handoffs(self, assignment_id: str) -> list[dict]:
        return self.list_handoffs(assignment_id=assignment_id, limit=100)

    def assignment_proposals(self, assignment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT p.*
                FROM proposals p
                JOIN assignment_proposals ap ON ap.proposal_id = p.proposal_id
                WHERE ap.assignment_id = ?
                ORDER BY p.created_at DESC
                """,
                (assignment_id,),
            ).fetchall()
        return [self._proposal_from_row(row) for row in rows]

    def assignment_traces(self, assignment_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT trace_id, linked_at
                FROM assignment_traces
                WHERE assignment_id = ?
                ORDER BY linked_at DESC
                """,
                (assignment_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def assignment_activity(self, assignment_id: str, limit: int = 50) -> list[dict] | None:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            return None
        workers = {assignment["owner_worker"], *assignment.get("contributor_workers", [])}
        room_id = assignment.get("room_id")
        activity: list[dict] = []
        for event in self.assignment_events(assignment_id) or []:
            activity.append({
                "activity_id": event["event_id"],
                "timestamp": event["created_at"],
                "event_type": event["event_type"],
                "activity_type": "assignment",
                "actor": event["actor"],
                "assignment_id": assignment_id,
                "summary": event.get("new_value") or event.get("details") or event["event_type"],
            })
        for handoff in self.assignment_handoffs(assignment_id):
            activity.append({
                "activity_id": handoff["handoff_id"],
                "timestamp": handoff["created_at"],
                "event_type": "handoff",
                "activity_type": "handoff",
                "actor": handoff.get("from_agent"),
                "assignment_id": assignment_id,
                "summary": f"{handoff.get('from_agent')} -> {handoff.get('to_agent')}: {handoff.get('summary')}",
            })
        if room_id and workers:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT message_id, timestamp, source, body
                    FROM messages
                    WHERE target = ? AND source IN ({})
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """.format(",".join("?" for _ in workers)),
                    [f"room:{room_id}", *sorted(workers), limit],
                ).fetchall()
            for row in rows:
                activity.append({
                    "activity_id": row["message_id"],
                    "timestamp": row["timestamp"],
                    "event_type": "message",
                    "activity_type": "message",
                    "actor": row["source"],
                    "assignment_id": assignment_id,
                    "room_id": room_id,
                    "summary": self._activity_summary_subject(row["body"], "room activity"),
                })
        activity.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return activity[:limit]

    def worker_assignments(self, worker_id: str, limit: int = 100) -> dict:
        owned = self.list_assignments(owner_worker=worker_id, limit=limit)
        contributing = self.list_assignments(contributor_worker=worker_id, limit=limit)
        all_items = {item["assignment_id"]: item for item in [*owned, *contributing]}
        counts = {
            "owned": len(owned),
            "contributor": len(contributing),
            "waiting": len([item for item in all_items.values() if item.get("status") == "waiting"]),
            "blocked": len([item for item in all_items.values() if item.get("status") == "blocked"]),
            "review": len([item for item in all_items.values() if item.get("status") == "review"]),
        }
        return {"worker_id": worker_id, "counts": counts, "owned": owned, "contributing": contributing}

    def mission_assignments(self, mission_id: str, limit: int = 100) -> list[dict] | None:
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
        if exists is None:
            return None
        return self.list_assignments(mission_id=mission_id, limit=limit)

    def outcome_assignments(self, outcome_id: str, limit: int = 100) -> list[dict] | None:
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM outcomes WHERE outcome_id = ?", (outcome_id,)).fetchone()
        if exists is None:
            return None
        return self.list_assignments(outcome_id=outcome_id, limit=limit)

    def room_assignments(self, room_id: str, limit: int = 100) -> list[dict] | None:
        if not self.room_exists(room_id):
            return None
        member_ids = set(self.get_room_members(room_id))
        assignments = self.list_assignments(room_id=room_id, limit=limit)
        for assignment in self.list_assignments(limit=limit):
            if assignment["assignment_id"] in {item["assignment_id"] for item in assignments}:
                continue
            workers = {assignment.get("owner_worker"), *assignment.get("contributor_workers", [])}
            if member_ids.intersection(worker for worker in workers if worker):
                assignments.append(assignment)
        assignments.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return assignments[:limit]

    def recent_assignment_handoffs(self, limit: int = 50) -> list[dict]:
        return self.list_handoffs(limit=limit)

    def create_assignment_handoff(
        self,
        assignment_id: str,
        *,
        to_worker: str,
        reason: str,
        context_summary: str = "",
        actor: str = "operator",
        created_at: str | None = None,
    ) -> dict | None:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            return None
        now = created_at or utc_now_iso()
        from_worker = str(assignment.get("owner_worker") or "")
        handoff = self.create_handoff(
            handoff_id=str(uuid.uuid4()),
            from_agent=from_worker,
            to_agent=to_worker,
            assignment_id=assignment_id,
            room_id=assignment.get("room_id"),
            summary=reason,
            recommended_next_step=context_summary,
            created_at=now,
        )
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE assignments SET owner_worker = ?, status = 'handoff', updated_at = ? WHERE assignment_id = ?",
                (to_worker, now, assignment_id),
            )
            self._conn.execute(
                "DELETE FROM assignment_contributors WHERE assignment_id = ? AND worker_id = ?",
                (assignment_id, to_worker),
            )
            self._save_assignment_event(
                assignment_id,
                "handoff",
                actor,
                from_worker,
                to_worker,
                {"reason": reason, "context_summary": context_summary, "handoff_id": handoff["handoff_id"]},
                now,
            )
        self.append_handoff_event(
            handoff["handoff_id"],
            "assignment_handoff",
            actor,
            {"assignment_id": assignment_id, "from_worker": from_worker, "to_worker": to_worker, "reason": reason, "context_summary": context_summary},
            now,
        )
        updated = self.get_assignment(assignment_id)
        return {"handoff": self.get_handoff(handoff["handoff_id"]), "assignment": updated}

    # ── handoffs ──────────────────────────────────────────────────────────

    def _handoff_from_row(self, row: sqlite3.Row) -> dict:
        data = dict(row)
        handoff_id = data.get("id") or data.get("handoff_id")
        room_id = data.get("room_id") or data.get("room_name")
        data["id"] = handoff_id
        data["handoff_id"] = handoff_id
        data["room_id"] = room_id
        data["room_name"] = room_id
        data["assignment_id"] = data.get("assignment_id") or ""
        data["from_worker"] = data.get("from_worker") or data.get("from_agent") or ""
        data["to_worker"] = data.get("to_worker") or data.get("to_agent") or ""
        data["reason"] = data.get("reason") or data.get("summary") or ""
        data["context_summary"] = data.get("context_summary") or data.get("recommended_next_step") or ""
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
        assignment_id: str | None = None,
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
                    id, handoff_id, created_at, updated_at, room_id, room_name, task_id, assignment_id,
                    goal_id, from_agent, to_agent, status, summary, open_questions, risks,
                    recommended_next_step, confidence, linked_message_ids_json,
                    linked_decision_ids_json, accepted_at, rejected_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    record_id, record_id, now, now, room, room, task_id, assignment_id, goal_id,
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
        assignment_id: str | None = None,
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
        if assignment_id is not None:
            clauses.append("assignment_id = ?")
            params.append(assignment_id)
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
            "assignment_id",
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
