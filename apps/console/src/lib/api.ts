import { fetch as tauriFetch } from "@tauri-apps/plugin-http";
import { invoke } from "@tauri-apps/api/core";

const DEFAULT_DAEMON_URL = "http://127.0.0.1:9460";

export const DAEMON_URL =
  (window as any).__SYNKRAKEN_DAEMON_URL?.replace(/\/$/, "") || DEFAULT_DAEMON_URL;

type JsonObject = Record<string, unknown>;

export type RuntimeRecovery = { ok: boolean; message: string };

export type HealthResponse = {
  ok?: boolean;
  status?: string;
  started_at?: string;
  uptime_seconds?: number;
  adapters?: JsonObject[];
  [key: string]: unknown;
};

export type Agent = {
  id?: string;
  adapter_id?: string;
  runtime_id?: string;
  type?: string;
  enabled?: boolean;
  status?: string;
  cost_tier?: string;
  usage_risk?: string;
  trust?: number;
  trust_score?: number;
  capabilities?: string[];
  latest_delivery_status?: string;
  latest_quality?: string;
  avg_duration_ms?: number;
  incident_summary?: string;
  reputation?: JsonObject;
  [key: string]: unknown;
};

export type RuntimeRecord = {
  runtime_id?: string;
  adapter_id?: string;
  id?: string;
  status?: string;
  enabled?: boolean;
  registry_only?: boolean;
  cost_tier?: string;
  supported_modes?: string[];
  capabilities?: string[];
  [key: string]: unknown;
};

export type WorkforceResponse = {
  workers?: Agent[];
  agents?: Agent[];
  workforce?: Agent[];
  runtimes?: RuntimeRecord[];
  registry?: RuntimeRecord[];
  reputation?: JsonObject[];
  summary?: JsonObject;
  recent_incidents?: unknown[];
  [key: string]: unknown;
};

export type WorkforceHealthResponse = {
  status?: string;
  summary?: string;
  counts?: JsonObject;
  incidents?: unknown[];
  [key: string]: unknown;
};

export type PresenceState =
  | "active"
  | "idle"
  | "watching"
  | "needs_attention"
  | "unavailable"
  | "unknown";

export type ActivityRecord = {
  activity_id?: string;
  timestamp?: string;
  runtime?: string | null;
  room?: string | null;
  event_type?: string;
  actor?: string;
  actor_type?: string;
  activity_type?: string;
  summary?: string;
  room_id?: string | null;
  task_id?: string | null;
  goal_id?: string | null;
  proposal_id?: string | null;
  trace_id?: string | null;
  mission_id?: string | null;
  mission_ids?: string[];
  outcome_id?: string | null;
  outcome_ids?: string[];
  assignment_id?: string | null;
  assignment_ids?: string[];
  severity?: string;
  [key: string]: unknown;
};

export type LiveActivitySummary = {
  active_workers?: number;
  active_worker_ids?: string[];
  recent_events?: number;
  last_activity_at?: string | null;
  last_activity_seconds_ago?: number | null;
  [key: string]: unknown;
};

export type WorkforcePresenceWorker = {
  runtime_id: string;
  display_name?: string;
  runtime_type?: string;
  status?: string;
  health_status?: string;
  trust_score?: number;
  presence_state?: PresenceState;
  current_room?: string | null;
  current_mission?: MissionRef | null;
  current_outcome?: OutcomeRef | null;
  current_assignment_count?: number;
  assignment_counts?: JsonObject;
  owned_assignments?: Assignment[];
  contributor_assignments?: Assignment[];
  assignments_waiting?: Assignment[];
  assignments_blocked?: Assignment[];
  assignments_in_review?: Assignment[];
  current_task_id?: string | null;
  current_goal_id?: string | null;
  latest_activity_type?: string;
  latest_activity_summary?: string;
  latest_activity_at?: string | null;
  current_activity?: string;
  last_meaningful_action?: string;
  seconds_since_activity?: number | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  idle_for_seconds?: number | null;
  needs_attention?: boolean;
  attention_reason?: string;
  suggested_action?: string;
  [key: string]: unknown;
};

export type MissionRef = {
  mission_id?: string;
  title?: string;
  status?: string;
  priority?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type Mission = MissionRef & {
  description?: string;
  created_at?: string;
  owner?: string;
  goal?: string;
  outcome?: string;
  risk_level?: string;
  progress?: {
    completed?: number;
    total?: number;
    percent?: number;
    [key: string]: unknown;
  };
  outcomes?: Outcome[];
  assignments?: Assignment[];
  workers?: JsonObject[];
  rooms?: JsonObject[];
  traces?: JsonObject[];
  incidents?: JsonObject[];
  proposals?: Proposal[];
  relationships?: JsonObject[];
  activity?: ActivityRecord[];
};

export type OutcomeRef = {
  outcome_id?: string;
  mission_id?: string;
  mission_title?: string;
  title?: string;
  status?: string;
  confidence?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type Outcome = OutcomeRef & {
  description?: string;
  owner?: string;
  created_at?: string;
  completed_at?: string | null;
  evidence_count?: number;
  proposal_count?: number;
  incident_count?: number;
  workers?: JsonObject[];
  traces?: JsonObject[];
  incidents?: JsonObject[];
  proposals?: Proposal[];
  relationships?: JsonObject[];
  activity?: ActivityRecord[];
  assignments?: Assignment[];
};

export type Assignment = {
  assignment_id?: string;
  id?: string;
  title?: string;
  description?: string;
  status?: string;
  owner_worker?: string;
  contributor_workers?: string[];
  mission_id?: string | null;
  outcome_id?: string | null;
  room_id?: string | null;
  mission?: MissionRef | null;
  outcome?: OutcomeRef | null;
  created_at?: string;
  updated_at?: string;
  last_activity?: string | null;
  handoffs?: HandoffRecord[];
  proposals?: Proposal[];
  traces?: JsonObject[];
  activity?: ActivityRecord[];
  events?: JsonObject[];
  [key: string]: unknown;
};

export type AssignmentSummary = {
  total?: number;
  assigned?: number;
  in_progress?: number;
  waiting?: number;
  blocked?: number;
  handoff?: number;
  review?: number;
  completed?: number;
  cancelled?: number;
  counts?: JsonObject;
  assignments?: Assignment[];
  [key: string]: unknown;
};

export type HandoffRecord = {
  handoff_id?: string;
  id?: string;
  assignment_id?: string | null;
  from_worker?: string;
  to_worker?: string;
  reason?: string;
  context_summary?: string;
  summary?: string;
  timestamp?: string;
  created_at?: string;
  [key: string]: unknown;
};

export type OutcomeSummary = {
  total?: number;
  counts?: JsonObject;
  completed?: number;
  in_progress?: number;
  review?: number;
  blocked?: number;
  highest_priority?: string;
  outcomes?: Outcome[];
  [key: string]: unknown;
};

export type MissionSummary = {
  total?: number;
  counts?: JsonObject;
  active_missions?: number;
  blocked_missions?: number;
  review_missions?: number;
  completed_missions?: number;
  highest_priority?: string;
  missions?: Mission[];
  [key: string]: unknown;
};

export type WorkforcePresenceResponse = {
  summary?: {
    total?: number;
    active?: number;
    idle?: number;
    watching?: number;
    needs_attention?: number;
    unavailable?: number;
    unknown?: number;
    highest_priority?: string;
    suggested_next_action?: string;
    [key: string]: unknown;
  };
  workers?: WorkforcePresenceWorker[];
  recent_activity?: ActivityRecord[];
  [key: string]: unknown;
};

export type ActivityRecentResponse = {
  activity?: ActivityRecord[];
  [key: string]: unknown;
};

export type ActivityLiveResponse = ActivityRecentResponse & {
  summary?: LiveActivitySummary;
  filters?: JsonObject;
};

export type Proposal = {
  id?: string;
  proposal_id?: string;
  status?: string;
  risk?: string;
  risk_level?: string;
  requires_approval?: boolean;
  approval_required?: boolean;
  approval_reason?: string;
  governance_reason?: string;
  proposed_by?: string;
  proposer?: string;
  title?: string;
  summary?: string;
  details?: string;
  room_id?: string;
  room?: string;
  goal_id?: string;
  goal?: string;
  linked_decision_ids?: unknown;
  linked_handoff_ids?: unknown;
  linked_message_ids?: unknown;
  type?: string;
  proposal_type?: string;
  created_at?: string;
  execution_payload?: unknown;
  events?: ProposalEvent[];
  [key: string]: unknown;
};

export type ProposalEvent = {
  event_type?: string;
  type?: string;
  actor?: string;
  created_at?: string;
  timestamp?: string;
  details?: unknown;
  [key: string]: unknown;
};

export type TraceResponse = {
  id?: string;
  trace_id?: string;
  replay?: unknown;
  summary?: unknown;
  timeline?: unknown[];
  messages?: unknown[];
  deliveries?: unknown[];
  dead_letters?: unknown[];
  decisions?: unknown[];
  handoffs?: unknown[];
  proposals?: unknown[];
  memory_markers?: unknown[];
  [key: string]: unknown;
};

export type ReplayResponse = TraceResponse & {
  kind?: string;
};

export type IncidentResponse = {
  incident?: unknown;
  latest_incident?: unknown;
  replay?: unknown;
  trace?: unknown;
  [key: string]: unknown;
};

export type DeadLettersResponse = {
  dead_letters?: unknown[];
  [key: string]: unknown;
};

export type CanvasRelationship = {
  id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  kind: string;
  tone?: string;
  status?: string;
  evidence?: JsonObject;
  observed_at?: string;
  [key: string]: unknown;
};

export type CanvasRelationshipsResponse = {
  relationships?: CanvasRelationship[];
  [key: string]: unknown;
};

export type Room = {
  name?: string;
  description?: string;
  created_at?: string;
  member_count?: number;
  last_activity?: string;
  most_active_workers?: { runtime?: string; events?: number }[];
  last_room_event?: string;
  activity_rate?: number;
  activity_rate_label?: string;
  current_mission?: MissionRef | null;
  current_outcome?: OutcomeRef | null;
  assignments?: Assignment[];
  members?: unknown[];
  [key: string]: unknown;
};

export type RoomMessage = {
  message_id?: string;
  conversation_id?: string;
  source?: string;
  target?: string;
  timestamp?: string;
  body?: string;
  metadata?: JsonObject;
  [key: string]: unknown;
};

export type DeliveryRecord = {
  adapter_id?: string;
  delivery_target?: string;
  original_target?: string;
  status?: string;
  quality?: string;
  ok?: boolean;
  duration_ms?: number | null;
  attempts?: number;
  body?: string;
  body_preview?: string;
  error?: string;
  message_id?: string;
  reply_message_id?: string | null;
  persisted_transcript_target?: string | null;
  [key: string]: unknown;
};

export type DispatchResponse = {
  message?: RoomMessage | JsonObject;
  routing?: JsonObject;
  deliveries?: DeliveryRecord[];
  dead_letters?: JsonObject[];
  [key: string]: unknown;
};

export type RoomMemory = {
  purpose?: string;
  objective?: string;
  current_focus?: string;
  notes?: string;
  rules?: unknown;
  constraints?: unknown;
  [key: string]: unknown;
};

export type WorkforceMemory = {
  memory_id: string;
  memory_type: string;
  title?: string;
  body?: string;
  content?: string;
  scope_type?: string;
  scope_id?: string;
  source_type?: string;
  source_id?: string;
  created_by?: string;
  status?: string;
  importance?: string;
  created_at?: string;
  updated_at?: string;
  expires_at?: string;
  [key: string]: unknown;
};

export type WorkforceMemoryResponse = {
  memories?: WorkforceMemory[];
};

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function daemonFetch(url: string, init: RequestInit): Promise<Response> {
  if ("__TAURI_INTERNALS__" in window) {
    return tauriFetch(url, init);
  }
  return window.fetch(url, init);
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await daemonFetch(`${DAEMON_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });

    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};

    if (!response.ok) {
      const detail =
        typeof payload?.error === "string" ? payload.error : `HTTP ${response.status}`;
      throw new ApiError(detail, response.status);
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Request timed out after ${timeoutMs}ms`);
    }
    const message = error instanceof Error ? error.message : "Daemon request failed";
    if (message === "Failed to fetch") {
      throw new ApiError("Daemon offline or unreachable");
    }
    throw new ApiError(message);
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function ensureRuntime(): Promise<RuntimeRecovery> {
  if (!("__TAURI_INTERNALS__" in window)) {
    return { ok: false, message: "Start SynKraken with `synkraken install`, then retry." };
  }
  return invoke<RuntimeRecovery>("ensure_synkraken_runtime");
}

function post<T>(path: string, body: JsonObject): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function patch<T>(path: string, body: JsonObject): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export const api = {
  getHealth: () => request<HealthResponse>("/health", {}, 3500),
  getAgents: () => request<{ agents: Agent[] }>("/v1/agents"),
  getWorkforce: () => request<WorkforceResponse>("/v1/workforce"),
  getWorkforceHealth: () => request<WorkforceHealthResponse>("/v1/workforce/health"),
  getWorkforcePresence: () => request<WorkforcePresenceResponse>("/v1/workforce/presence"),
  getRecentActivity: (limit = 50) =>
    request<ActivityRecentResponse>(`/v1/activity/recent?limit=${limit}`),
  getLiveActivity: (limit = 50) =>
    request<ActivityLiveResponse>(`/v1/activity/live?limit=${limit}`),
  getLiveActivityForMission: (missionId: string, limit = 50) =>
    request<ActivityLiveResponse>(
      `/v1/activity/live?limit=${limit}&mission=${encodeURIComponent(missionId)}`,
    ),
  getLiveActivityForActiveMissions: (limit = 50) =>
    request<ActivityLiveResponse>(`/v1/activity/live?limit=${limit}&active_missions=true`),
  getLiveActivityForOutcome: (outcomeId: string, limit = 50) =>
    request<ActivityLiveResponse>(
      `/v1/activity/live?limit=${limit}&outcome=${encodeURIComponent(outcomeId)}`,
    ),
  getLiveActivityForAssignment: (assignmentId: string, limit = 50) =>
    request<ActivityLiveResponse>(
      `/v1/activity/live?limit=${limit}&assignment=${encodeURIComponent(assignmentId)}`,
    ),
  getCanvasRelationships: (limit = 500) =>
    request<CanvasRelationshipsResponse>(`/v1/canvas/relationships?limit=${limit}`),
  getAssignments: () => request<{ assignments: Assignment[] }>("/v1/assignments?limit=200"),
  getAssignment: (id: string) => request<Assignment>(`/v1/assignments/${encodeURIComponent(id)}`),
  getAssignmentSummary: () => request<AssignmentSummary>("/v1/assignments/summary"),
  getAssignmentActivity: (id: string, limit = 50) =>
    request<{ assignment_id: string; activity: ActivityRecord[] }>(
      `/v1/assignments/${encodeURIComponent(id)}/activity?limit=${limit}`,
    ),
  getAssignmentHandoffs: (id: string) =>
    request<{ assignment_id: string; handoffs: HandoffRecord[] }>(`/v1/assignments/${encodeURIComponent(id)}/handoffs`),
  getAssignmentProposals: (id: string) =>
    request<{ assignment_id: string; proposals: Proposal[] }>(`/v1/assignments/${encodeURIComponent(id)}/proposals`),
  getAssignmentTraces: (id: string) =>
    request<{ assignment_id: string; traces: JsonObject[] }>(`/v1/assignments/${encodeURIComponent(id)}/traces`),
  getWorkerAssignments: (id: string) =>
    request<{ worker_id: string; assignments: Assignment[]; owned: Assignment[]; contributor: Assignment[]; waiting: Assignment[]; blocked: Assignment[]; review: Assignment[]; counts: JsonObject }>(
      `/v1/workforce/${encodeURIComponent(id)}/assignments`,
    ),
  createAssignment: (body: JsonObject) => post<Assignment>("/v1/assignments", body),
  updateAssignment: (id: string, body: JsonObject) => patch<Assignment>(`/v1/assignments/${encodeURIComponent(id)}`, body),
  addAssignmentContributor: (id: string, workerId: string) =>
    post<Assignment>(`/v1/assignments/${encodeURIComponent(id)}/contributors`, { worker_id: workerId }),
  removeAssignmentContributor: (id: string, workerId: string) =>
    del<Assignment>(`/v1/assignments/${encodeURIComponent(id)}/contributors/${encodeURIComponent(workerId)}`),
  handoffAssignment: (id: string, toWorker: string, reason: string, contextSummary = "") =>
    post<{ assignment?: Assignment; handoff?: HandoffRecord }>(`/v1/assignments/${encodeURIComponent(id)}/handoff`, {
      to_worker: toWorker,
      reason,
      context_summary: contextSummary,
    }),
  getOutcomes: () => request<{ outcomes: Outcome[] }>("/v1/outcomes?limit=100"),
  getOutcome: (id: string) => request<Outcome>(`/v1/outcomes/${encodeURIComponent(id)}`),
  getOutcomeSummary: () => request<OutcomeSummary>("/v1/outcomes/summary"),
  getMissionOutcomes: (id: string) =>
    request<{ mission_id: string; outcomes: Outcome[] }>(`/v1/missions/${encodeURIComponent(id)}/outcomes`),
  getMissionAssignments: (id: string) =>
    request<{ mission_id: string; assignments: Assignment[] }>(`/v1/missions/${encodeURIComponent(id)}/assignments`),
  getOutcomeActivity: (id: string, limit = 50) =>
    request<{ outcome_id: string; activity: ActivityRecord[] }>(
      `/v1/outcomes/${encodeURIComponent(id)}/activity?limit=${limit}`,
    ),
  getOutcomeWorkers: (id: string) =>
    request<{ outcome_id: string; workers: JsonObject[] }>(`/v1/outcomes/${encodeURIComponent(id)}/workers`),
  getOutcomeIncidents: (id: string) =>
    request<{ outcome_id: string; incidents: JsonObject[] }>(`/v1/outcomes/${encodeURIComponent(id)}/incidents`),
  getOutcomeProposals: (id: string) =>
    request<{ outcome_id: string; proposals: Proposal[] }>(`/v1/outcomes/${encodeURIComponent(id)}/proposals`),
  getMissions: () => request<{ missions: Mission[] }>("/v1/missions?limit=100"),
  getMission: (id: string) => request<Mission>(`/v1/missions/${encodeURIComponent(id)}`),
  getMissionSummary: () => request<MissionSummary>("/v1/missions/summary"),
  getMissionActivity: (id: string, limit = 50) =>
    request<{ mission_id: string; activity: ActivityRecord[] }>(
      `/v1/missions/${encodeURIComponent(id)}/activity?limit=${limit}`,
    ),
  getMissionWorkers: (id: string) =>
    request<{ mission_id: string; workers: JsonObject[] }>(`/v1/missions/${encodeURIComponent(id)}/workers`),
  getMissionIncidents: (id: string) =>
    request<{ mission_id: string; incidents: JsonObject[] }>(`/v1/missions/${encodeURIComponent(id)}/incidents`),
  getMissionProposals: (id: string) =>
    request<{ mission_id: string; proposals: Proposal[] }>(`/v1/missions/${encodeURIComponent(id)}/proposals`),
  getOutcomeAssignments: (id: string) =>
    request<{ outcome_id: string; assignments: Assignment[] }>(`/v1/outcomes/${encodeURIComponent(id)}/assignments`),
  getRooms: () => request<{ rooms: Room[] }>("/v1/rooms"),
  getRoom: (name: string) => request<Room>(`/v1/rooms/${encodeURIComponent(name)}`),
  getRoomMessages: (name: string, limit = 80) =>
    request<{ messages: RoomMessage[] }>(
      `/v1/rooms/${encodeURIComponent(name)}/messages?limit=${limit}`,
    ),
  searchRoomMessages: (name: string, query: string, limit = 80) =>
    request<{ messages: RoomMessage[] }>(
      `/v1/rooms/${encodeURIComponent(name)}/messages?q=${encodeURIComponent(query)}&limit=${limit}`,
    ),
  getRoomMemory: (name: string) =>
    request<{ memory?: RoomMemory } | RoomMemory>(`/v1/rooms/${encodeURIComponent(name)}/memory`),
  getRoomAssignments: (name: string) =>
    request<{ room: string; assignments: Assignment[] }>(`/v1/rooms/${encodeURIComponent(name)}/assignments`),
  getMemory: (params = "") =>
    request<WorkforceMemoryResponse>(`/v1/memory${params ? `?${params}` : ""}`),
  getMemoryContext: (scopeType: string, scopeId?: string) =>
    request<WorkforceMemoryResponse>(
      `/v1/memory/context?scope_type=${encodeURIComponent(scopeType)}${scopeId ? `&scope_id=${encodeURIComponent(scopeId)}` : ""}`,
    ),
  createMemoryNote: (body: JsonObject) => post<{ memory?: WorkforceMemory }>("/v1/memory/operator-note", body),
  approveMemory: (memoryId: string) => post<{ memory?: WorkforceMemory }>("/v1/memory/approve", { memory_id: memoryId, actor: "operator" }),
  rejectMemory: (memoryId: string) => post<{ memory?: WorkforceMemory }>("/v1/memory/reject", { memory_id: memoryId, actor: "operator" }),
  archiveMemory: (memoryId: string) => post<{ memory?: WorkforceMemory }>("/v1/memory/archive", { memory_id: memoryId, actor: "operator" }),
  createRoom: (name: string, members: string[] = [], description = "") =>
    post<Room>("/v1/rooms", { name, description, members }),
  createRoomPreset: (preset: string, name: string) =>
    post<{ room?: Room; memory?: RoomMemory; preset?: string }>("/v1/rooms/preset", {
      preset,
      name,
      actor: "operator",
    }),
  deleteRoom: (name: string) => del<{ deleted?: string }>(`/v1/rooms/${encodeURIComponent(name)}`),
  addRoomMember: (name: string, adapterId: string) =>
    post<{ room?: Room }>(`/v1/rooms/${encodeURIComponent(name)}/members`, {
      adapter_id: adapterId,
    }),
  removeRoomMember: (name: string, adapterId: string) =>
    del<{ ok?: boolean }>(
      `/v1/rooms/${encodeURIComponent(name)}/members/${encodeURIComponent(adapterId)}`,
    ),
  recordRoomNote: (name: string, body: string) =>
    post<DispatchResponse>(`/v1/rooms/${encodeURIComponent(name)}/messages`, {
      source: "operator",
      body,
    }),
  summarizeRoom: (name: string, limit = 50) =>
    post<{ room?: string; summary?: string; memory?: RoomMemory }>(
      `/v1/rooms/${encodeURIComponent(name)}/summary`,
      { actor: "operator", limit },
    ),
  sendMessage: (target: string, body: string, room?: string) =>
    post<DispatchResponse>("/v1/messages", { target, body, source: "operator", room }),
  sendRoomScopedMessage: (room: string, target: string, body: string) =>
    post<DispatchResponse>("/v1/messages", {
      target,
      body,
      source: "operator",
      metadata: { room_context: `room:${room}` },
    }),
  getProposals: () => request<{ proposals: Proposal[] }>("/v1/proposals?limit=100"),
  getPendingProposals: () => request<{ proposals: Proposal[] }>("/v1/proposals/pending"),
  getProposal: (id: string) => request<Proposal>(`/v1/proposal/${encodeURIComponent(id)}`),
  approveProposal: (id: string) =>
    post<Proposal>("/v1/proposal/approve", { proposal_id: id, actor: "operator" }),
  rejectProposal: (id: string) =>
    post<Proposal>("/v1/proposal/reject", { proposal_id: id, actor: "operator" }),
  executeProposal: (id: string) =>
    post<Proposal>("/v1/proposal/execute", { proposal_id: id, actor: "operator" }),
  getReplay: (id: string) => request<ReplayResponse>(`/v1/replay/${encodeURIComponent(id)}`),
  getTrace: (id: string) => request<TraceResponse>(`/v1/trace/${encodeURIComponent(id)}`),
  getLatestIncident: () => request<IncidentResponse>("/v1/incident/latest"),
  getRecentHandoffs: (limit = 20) => request<{ handoffs: HandoffRecord[] }>(`/v1/handoffs/recent?limit=${limit}`),
  getDeadLetters: (limit = 100) => request<DeadLettersResponse>(`/v1/dead-letters?limit=${limit}`),
};
