import { fetch } from "@tauri-apps/plugin-http";

const DEFAULT_DAEMON_URL = "http://127.0.0.1:9460";

export const DAEMON_URL =
  import.meta.env.VITE_SYNKRAKEN_DAEMON_URL?.replace(/\/$/, "") || DEFAULT_DAEMON_URL;

type JsonObject = Record<string, unknown>;

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

export type Room = {
  name?: string;
  description?: string;
  created_at?: string;
  member_count?: number;
  last_activity?: string;
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

export type RoomMemory = {
  purpose?: string;
  objective?: string;
  current_focus?: string;
  notes?: string;
  rules?: unknown;
  constraints?: unknown;
  [key: string]: unknown;
};

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${DAEMON_URL}${path}`, {
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
    throw new ApiError(error instanceof Error ? error.message : "Daemon request failed");
  } finally {
    window.clearTimeout(timeout);
  }
}

function post<T>(path: string, body: JsonObject): Promise<T> {
  return request<T>(path, {
    method: "POST",
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
  getRooms: () => request<{ rooms: Room[] }>("/v1/rooms"),
  getRoom: (name: string) => request<Room>(`/v1/rooms/${encodeURIComponent(name)}`),
  getRoomMessages: (name: string, limit = 80) =>
    request<{ messages: RoomMessage[] }>(
      `/v1/rooms/${encodeURIComponent(name)}/messages?limit=${limit}`,
    ),
  getRoomMemory: (name: string) =>
    request<{ memory?: RoomMemory } | RoomMemory>(`/v1/rooms/${encodeURIComponent(name)}/memory`),
  addRoomMember: (name: string, adapterId: string) =>
    post<{ room?: Room }>(`/v1/rooms/${encodeURIComponent(name)}/members`, {
      adapter_id: adapterId,
    }),
  removeRoomMember: (name: string, adapterId: string) =>
    del<{ ok?: boolean }>(
      `/v1/rooms/${encodeURIComponent(name)}/members/${encodeURIComponent(adapterId)}`,
    ),
  sendMessage: (target: string, body: string, room?: string) =>
    post<JsonObject>("/v1/messages", { target, body, source: "operator", room }),
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
  getDeadLetters: (limit = 100) => request<DeadLettersResponse>(`/v1/dead-letters?limit=${limit}`),
};
