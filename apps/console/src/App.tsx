import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import {
  Agent,
  CanvasRelationship,
  DAEMON_URL,
  HealthResponse,
  IncidentResponse,
  Proposal,
  ReplayResponse,
  Room,
  RoomMemory,
  RoomMessage,
  TraceResponse,
  WorkforceHealthResponse,
  WorkforceResponse,
  api,
} from "./lib/api";
import { asRecord, duration, numberText, percent, prettyJson, shortDate, stringList, text } from "./lib/format";

type View = "canvas" | "workforce" | "rooms" | "flight" | "proposals" | "proposal-detail" | "incidents";
type SortKey = "health" | "trust" | "latency" | "incidents";
type ReplayFilter = "all" | "message" | "reply" | "handoff" | "proposal" | "approval" | "execution" | "incident" | "failure";
type WorkspacePreset = "Coding" | "Operations" | "Research" | "Incident Response";
type CanvasNodeType = "workforce-summary" | "runtime" | "room" | "proposal-queue" | "proposal-detail" | "incident" | "trace" | "dead-letter";

type CanvasNode = {
  id: string;
  type: CanvasNodeType;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  collapsed?: boolean;
  refId?: string;
};

type CanvasCommand =
  | { nonce: number; kind: "workspace"; workspace: WorkspacePreset }
  | { nonce: number; kind: "add"; nodeType: CanvasNodeType; refId?: string }
  | { nonce: number; kind: "fit" }
  | { nonce: number; kind: "reset" }
  | { nonce: number; kind: "clear-layout" }
  | { nonce: number; kind: "focus-runtime"; id?: string }
  | { nonce: number; kind: "focus-room"; id?: string }
  | { nonce: number; kind: "focus-proposal"; id?: string }
  | { nonce: number; kind: "focus-trace"; id?: string };

type CanvasCommandInput =
  | { kind: "workspace"; workspace: WorkspacePreset }
  | { kind: "add"; nodeType: CanvasNodeType; refId?: string }
  | { kind: "fit" }
  | { kind: "reset" }
  | { kind: "clear-layout" }
  | { kind: "focus-runtime"; id?: string }
  | { kind: "focus-room"; id?: string }
  | { kind: "focus-proposal"; id?: string }
  | { kind: "focus-trace"; id?: string };

type AppData = {
  health?: HealthResponse;
  agents: Agent[];
  workforce?: WorkforceResponse;
  workforceHealth?: WorkforceHealthResponse;
  proposals: Proposal[];
  pending: Proposal[];
  rooms: Room[];
  incident?: IncidentResponse;
  deadLetters: unknown[];
  canvasRelationships: CanvasRelationship[];
};

type RoomDetail = {
  room?: Room;
  messages: RoomMessage[];
  memory?: RoomMemory;
};

type DaemonStatus = "unknown" | "online" | "offline";

type NodeErrors = Record<string, string | undefined>;

const initialData: AppData = {
  agents: [],
  proposals: [],
  pending: [],
  rooms: [],
  deadLetters: [],
  canvasRelationships: [],
};

const navItems: { id: View; label: string }[] = [
  { id: "canvas", label: "Canvas" },
  { id: "workforce", label: "Workforce" },
  { id: "rooms", label: "Rooms" },
  { id: "flight", label: "Trace" },
  { id: "proposals", label: "Proposals" },
  { id: "incidents", label: "Incidents" },
];

const workspacePresets: WorkspacePreset[] = ["Coding", "Operations", "Research", "Incident Response"];
const canvasStorageKey = "synkraken.console.v03.operationsCanvasLayout";

const healthRank: Record<string, number> = {
  failing: 0,
  unstable: 1,
  degraded: 2,
  healthy: 3,
};

function proposalId(proposal: Proposal): string {
  return text(proposal.proposal_id || proposal.id, "");
}

function workerId(worker: Agent): string {
  return text(worker.adapter_id || worker.runtime_id || worker.id, "runtime");
}

function workerReputation(worker: Agent): Record<string, unknown> {
  return asRecord(worker.reputation || worker);
}

function workerHealth(worker: Agent): string {
  const reputation = workerReputation(worker);
  return text(reputation.health_status || worker.health_status || worker.status, "healthy").toLowerCase();
}

function workerTrust(worker: Agent): number {
  const reputation = workerReputation(worker);
  const value = reputation.trust_score ?? worker.trust_score ?? worker.trust;
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1 ? value / 100 : value;
  }
  return 0;
}

function workerLatency(worker: Agent): number {
  const reputation = workerReputation(worker);
  const value = reputation.avg_duration_ms ?? worker.avg_duration_ms;
  return typeof value === "number" && Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
}

function workerIncidentCount(worker: Agent): number {
  const reputation = workerReputation(worker);
  const failures = Number(reputation.recent_failures ?? reputation.failures ?? 0);
  const timeouts = Number(reputation.recent_timeouts ?? reputation.timeouts ?? 0);
  const empty = Number(reputation.recent_empty_replies ?? reputation.empty_replies ?? 0);
  const status = workerHealth(worker);
  return (Number.isFinite(failures) ? failures : 0) + (Number.isFinite(timeouts) ? timeouts : 0) + (Number.isFinite(empty) ? empty : 0) + (status === "failing" ? 10 : 0);
}

function statusClass(value: unknown): string {
  const normalized = text(value, "").toLowerCase();
  if (normalized.includes("fail") || normalized.includes("timeout") || normalized.includes("offline")) {
    return "status-danger";
  }
  if (normalized.includes("unstable") || normalized.includes("degrad") || normalized.includes("block")) {
    return "status-warn";
  }
  return "status-good";
}

function eventKind(event: Record<string, unknown>): ReplayFilter {
  const raw = text(event.event_type || event.type || event.kind || event.source, "").toLowerCase();
  const outcome = text(event.outcome || event.status, "").toLowerCase();
  if (raw.includes("dead") || raw.includes("incident") || raw.includes("letter")) return "incident";
  if (raw.includes("approval") || raw.includes("approved") || raw.includes("reject")) return "approval";
  if (raw.includes("execut")) return "execution";
  if (raw.includes("handoff")) return "handoff";
  if (raw.includes("proposal")) return "proposal";
  if (raw.includes("delivery") || raw.includes("reply")) return outcome.includes("fail") || outcome.includes("timeout") ? "failure" : "reply";
  if (outcome.includes("fail") || outcome.includes("timeout")) return "failure";
  return "message";
}

function containsFailure(event: Record<string, unknown>): boolean {
  const haystack = `${text(event.event_type, "")} ${text(event.type, "")} ${text(event.status, "")} ${text(event.outcome, "")}`.toLowerCase();
  return haystack.includes("fail") || haystack.includes("timeout") || haystack.includes("dead");
}

function proposalLinks(proposal: Proposal): string[] {
  return [
    ...stringList(proposal.linked_message_ids),
    ...stringList(proposal.linked_decision_ids),
    ...stringList(proposal.linked_handoff_ids),
    text(proposal.task_id, ""),
    text(proposal.goal_id || proposal.goal, ""),
    text(proposal.room_id || proposal.room, ""),
  ].filter(Boolean);
}

function sameCanvasRelationships(left: CanvasRelationship[], right: CanvasRelationship[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((item, index) => {
    const other = right[index];
    return Boolean(other)
      && item.id === other.id
      && item.source_type === other.source_type
      && item.source_id === other.source_id
      && item.target_type === other.target_type
      && item.target_id === other.target_id
      && item.kind === other.kind
      && item.tone === other.tone
      && item.status === other.status;
  });
}

function nodeTitle(type: CanvasNodeType, refId?: string): string {
  if (type === "workforce-summary") return "Workforce Summary";
  if (type === "runtime") return refId ? `Runtime · ${refId}` : "Runtime";
  if (type === "room") return refId ? `Room · #${refId}` : "Room";
  if (type === "proposal-queue") return "Proposal Queue";
  if (type === "proposal-detail") return refId ? `Proposal · ${refId}` : "Proposal Detail";
  if (type === "incident") return "Incident";
  if (type === "trace") return refId ? `Trace · ${refId}` : "Trace";
  return "Dead Letters";
}

function createNode(type: CanvasNodeType, x: number, y: number, refId?: string): CanvasNode {
  const compact = type === "runtime";
  const id = `${type}:${refId || "primary"}`;
  return {
    id,
    type,
    title: nodeTitle(type, refId),
    x,
    y,
    width: compact ? 300 : 360,
    height: type === "trace" ? 360 : 300,
    refId,
  };
}

function createPresetNodes(workspace: WorkspacePreset, workers: Agent[], rooms: Room[], proposals: Proposal[], deadLetters: unknown[]): CanvasNode[] {
  const primaryRoom = text(rooms[0]?.name, workspace === "Research" ? "research" : workspace === "Coding" ? "coding" : "ops");
  const failingWorkers = workers.filter((worker) => ["failing", "unstable", "degraded"].includes(workerHealth(worker)));
  const runtimeWorkers = workspace === "Incident Response" ? failingWorkers : workers;
  const selectedProposal = proposals.find((proposal) => text(proposal.status, "").toLowerCase() === "pending") || proposals[0];
  const traceId = text(selectedProposal ? proposalId(selectedProposal) : asRecord(deadLetters[0]).message_id || asRecord(deadLetters[0]).conversation_id, "");

  if (workspace === "Coding") {
    return [
      createNode("workforce-summary", 40, 40),
      createNode("room", 430, 40, primaryRoom),
      createNode("proposal-queue", 40, 380),
      createNode("trace", 430, 380, traceId || undefined),
    ];
  }
  if (workspace === "Research") {
    return [
      createNode("room", 40, 40, primaryRoom),
      createNode("trace", 430, 40, traceId || undefined),
      createNode("proposal-queue", 40, 400),
      createNode("workforce-summary", 430, 430),
    ];
  }
  if (workspace === "Incident Response") {
    return [
      createNode("incident", 40, 40),
      createNode("dead-letter", 430, 40),
      createNode("trace", 820, 40, traceId || undefined),
      ...runtimeWorkers.slice(0, 4).map((worker, index) => createNode("runtime", 40 + index * 320, 430, workerId(worker))),
      createNode("proposal-queue", 40, 760),
    ];
  }
  return [
    createNode("workforce-summary", 40, 40),
    ...runtimeWorkers.slice(0, 6).map((worker, index) => createNode("runtime", 430 + (index % 3) * 320, 40 + Math.floor(index / 3) * 330, workerId(worker))),
    createNode("incident", 40, 380),
    createNode("dead-letter", 430, 710),
  ];
}

function nodeTone(type: CanvasNodeType, node: CanvasNode, workers: Agent[], pending: Proposal[], deadLetters: unknown[]): "normal" | "selected" | "degraded" | "failing" | "pending" | "empty" | "loading" | "error" {
  if (type === "runtime") {
    const worker = workers.find((item) => workerId(item) === node.refId);
    if (!worker) return "empty";
    const health = workerHealth(worker);
    if (health === "failing" || health === "unstable") return "failing";
    if (health === "degraded") return "degraded";
  }
  if (type === "proposal-queue" || type === "proposal-detail") return pending.length ? "pending" : "empty";
  if (type === "dead-letter") return deadLetters.length ? "failing" : "empty";
  if (type === "incident") return deadLetters.length || workers.some((worker) => ["failing", "unstable"].includes(workerHealth(worker))) ? "failing" : "normal";
  return "normal";
}

function inferCanvasTarget(query: string, workers: Agent[], rooms: Room[], proposals: Proposal[], deadLetters: unknown[]): { type: CanvasNodeType; refId?: string } {
  const value = query.trim();
  const normalized = value.toLowerCase();
  if (!value) return { type: "workforce-summary" };
  const runtime = workers.find((worker) => workerId(worker).toLowerCase() === normalized);
  if (runtime) return { type: "runtime", refId: workerId(runtime) };
  const roomName = normalized.startsWith("#") ? normalized.slice(1) : normalized;
  const room = rooms.find((item) => text(item.name, "").toLowerCase() === roomName);
  if (room) return { type: "room", refId: text(room.name, roomName) };
  const proposal = proposals.find((item) => proposalId(item).toLowerCase() === normalized || text(item.title, "").toLowerCase().includes(normalized));
  if (proposal) return { type: "proposal-detail", refId: proposalId(proposal) };
  const deadLetter = deadLetters.find((item) => {
    const record = asRecord(item);
    return [record.dead_letter_id, record.delivery_id, record.message_id, record.conversation_id].some((candidate) => text(candidate, "").toLowerCase() === normalized);
  });
  if (deadLetter) return { type: "dead-letter" };
  if (normalized.includes("incident")) return { type: "incident" };
  if (normalized.includes("dead")) return { type: "dead-letter" };
  if (normalized.includes("proposal")) return { type: "proposal-queue" };
  return { type: "trace", refId: value };
}

export default function App() {
  const [view, setView] = useState<View>("canvas");
  const [data, setData] = useState<AppData>(initialData);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [daemonStatus, setDaemonStatus] = useState<DaemonStatus>("unknown");
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [nodeErrors, setNodeErrors] = useState<NodeErrors>({});
  const [selectedRuntime, setSelectedRuntime] = useState<string | null>(null);
  const [selectedRoom, setSelectedRoom] = useState("ops");
  const [roomDetail, setRoomDetail] = useState<RoomDetail>({ messages: [] });
  const [roomMessage, setRoomMessage] = useState("");
  const [roomMember, setRoomMember] = useState("");
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [selectedProposal, setSelectedProposal] = useState<Proposal | null>(null);
  const [replayId, setReplayId] = useState("");
  const [replay, setReplay] = useState<ReplayResponse | null>(null);
  const [replayFilter, setReplayFilter] = useState<ReplayFilter>("all");
  const [runtimeFilter, setRuntimeFilter] = useState("");
  const [failureOnly, setFailureOnly] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [canvasWorkspace, setCanvasWorkspace] = useState<WorkspacePreset>("Operations");
  const [canvasCommand, setCanvasCommand] = useState<CanvasCommand | null>(null);

  const daemonOnline = daemonStatus === "online";

  const workers = useMemo(() => {
    const workforceWorkers = (data.workforce?.workforce || data.workforce?.workers || data.workforce?.agents || []) as Agent[];
    return workforceWorkers.length ? workforceWorkers : data.agents;
  }, [data.agents, data.workforce]);

  const refresh = useCallback(async (background = false) => {
    if (background) {
      setRefreshing(true);
    } else {
      setInitialLoading(true);
    }
    const health = await api.getHealth().catch((healthError: unknown) => healthError) as HealthResponse | Error;
    if (health instanceof Error) {
      setDaemonStatus("offline");
      setGlobalError(health.message || "Daemon unavailable");
      if (!background) setInitialLoading(false);
      setRefreshing(false);
      return;
    }

    setDaemonStatus("online");
    setGlobalError(null);
    const [agents, workforce, workforceHealth, proposals, pending, rooms, incident, deadLetters, canvasRelationships] =
      await Promise.allSettled([
        api.getAgents(),
        api.getWorkforce(),
        api.getWorkforceHealth(),
        api.getProposals(),
        api.getPendingProposals(),
        api.getRooms(),
        api.getLatestIncident(),
        api.getDeadLetters(100),
        api.getCanvasRelationships(500),
      ]);

    const endpointErrors = [agents, workforce, workforceHealth, proposals, pending, rooms, incident, deadLetters, canvasRelationships]
      .filter((result): result is PromiseRejectedResult => result.status === "rejected")
      .map((result) => result.reason instanceof Error ? result.reason.message : "Endpoint refresh failed");

    setData((current) => {
      const nextRelationships = canvasRelationships.status === "fulfilled" ? canvasRelationships.value.relationships || [] : current.canvasRelationships;
      return {
        health,
        agents: agents.status === "fulfilled" ? agents.value.agents || [] : current.agents,
        workforce: workforce.status === "fulfilled" ? workforce.value : current.workforce,
        workforceHealth: workforceHealth.status === "fulfilled" ? workforceHealth.value : current.workforceHealth,
        proposals: proposals.status === "fulfilled" ? proposals.value.proposals || [] : current.proposals,
        pending: pending.status === "fulfilled" ? pending.value.proposals || [] : current.pending,
        rooms: rooms.status === "fulfilled" ? rooms.value.rooms || [] : current.rooms,
        incident: incident.status === "fulfilled" ? incident.value : current.incident,
        deadLetters: deadLetters.status === "fulfilled" ? deadLetters.value.dead_letters || [] : current.deadLetters,
        canvasRelationships: sameCanvasRelationships(current.canvasRelationships, nextRelationships) ? current.canvasRelationships : nextRelationships,
      };
    });
    setViewError(endpointErrors[0] || null);
    if (!background) setInitialLoading(false);
    setRefreshing(false);
  }, []);

  const loadRoom = useCallback(async (name: string, background = false) => {
    if (!name) return;
    try {
      const [room, messages, memory] = await Promise.all([
        api.getRoom(name),
        api.getRoomMessages(name, 100),
        api.getRoomMemory(name),
      ]);
      setRoomDetail({
        room,
        messages: messages.messages || [],
        memory: ("memory" in memory ? memory.memory : memory) as RoomMemory,
      });
      setViewError(null);
      setNodeErrors((current) => {
        const next = { ...current };
        delete next[`room:${name}`];
        return next;
      });
    } catch (roomError) {
      const message = roomError instanceof Error ? roomError.message : "Room load failed";
      if (!background) setViewError(message);
      setNodeErrors((current) => ({ ...current, [`room:${name}`]: message.toLowerCase().includes("not found") ? "Room not found" : message }));
    }
  }, []);

  useEffect(() => {
    void refresh(false);
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => void refresh(true), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    void loadRoom(selectedRoom);
  }, [loadRoom, selectedRoom]);

  useEffect(() => {
    const timer = window.setInterval(() => void loadRoom(selectedRoom, true), 5000);
    return () => window.clearInterval(timer);
  }, [loadRoom, selectedRoom]);

  useEffect(() => {
    if (selectedRoom === "ops" && data.rooms.length && !data.rooms.some((room) => room.name === selectedRoom)) {
      const firstRoom = text(data.rooms[0]?.name, "");
      if (firstRoom) setSelectedRoom(firstRoom);
    }
  }, [data.rooms, selectedRoom]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const openProposal = useCallback(async (id: string) => {
    setSelectedProposalId(id);
    setSelectedProposal(null);
    setView("proposal-detail");
    try {
      setSelectedProposal(await api.getProposal(id));
      setViewError(null);
      setNodeErrors((current) => {
        const next = { ...current };
        delete next[`proposal-detail:${id}`];
        return next;
      });
    } catch (detailError) {
      const message = detailError instanceof Error ? detailError.message : "Proposal load failed";
      setViewError(message);
      setNodeErrors((current) => ({ ...current, [`proposal-detail:${id}`]: message.toLowerCase().includes("not found") ? "Proposal not found" : message }));
    }
  }, []);

  const proposalAction = useCallback(
    async (id: string, action: "approve" | "reject" | "execute") => {
      try {
        if (action === "approve") await api.approveProposal(id);
        if (action === "reject") await api.rejectProposal(id);
        if (action === "execute") await api.executeProposal(id);
        await refresh();
        if (selectedProposalId === id) {
          setSelectedProposal(await api.getProposal(id));
        }
        setViewError(null);
      } catch (actionError) {
        setViewError(actionError instanceof Error ? actionError.message : "Proposal action failed");
      }
    },
    [refresh, selectedProposalId],
  );

  const loadReplay = useCallback(async (id = replayId) => {
    if (!id.trim()) return;
    try {
      const result = await api.getReplay(id.trim());
      setReplay(result);
      setReplayId(id.trim());
      setView("flight");
      setViewError(null);
    } catch (replayError) {
      setReplay(null);
      setViewError(replayError instanceof Error ? replayError.message : "Replay load failed");
    }
  }, [replayId]);

  const sendRoomMessage = useCallback(async () => {
    if (!roomMessage.trim() || !selectedRoom) return;
    try {
      await api.sendMessage(`room:${selectedRoom}`, roomMessage.trim(), selectedRoom);
      setRoomMessage("");
      await loadRoom(selectedRoom);
      await refresh();
    } catch (sendError) {
      setViewError(sendError instanceof Error ? sendError.message : "Room broadcast failed");
    }
  }, [loadRoom, refresh, roomMessage, selectedRoom]);

  const updateRoomMember = useCallback(async (action: "add" | "remove", adapterId: string) => {
    if (!selectedRoom || !adapterId.trim()) return;
    try {
      if (action === "add") {
        await api.addRoomMember(selectedRoom, adapterId.trim());
        setRoomMember("");
      } else {
        await api.removeRoomMember(selectedRoom, adapterId.trim());
      }
      await loadRoom(selectedRoom);
      await refresh();
    } catch (memberError) {
      setViewError(memberError instanceof Error ? memberError.message : "Room membership update failed");
    }
  }, [loadRoom, refresh, selectedRoom]);

  const dispatchCanvasCommand = useCallback((command: CanvasCommandInput) => {
    setView("canvas");
    setCanvasCommand({ ...command, nonce: Date.now() } as CanvasCommand);
    if (command.kind === "workspace") {
      setCanvasWorkspace(command.workspace);
    }
  }, []);

  const commands = useMemo(
    () => [
      { label: "Open Operations Canvas", run: () => setView("canvas") },
      { label: "Switch workspace: Coding", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Coding" }) },
      { label: "Switch workspace: Operations", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Operations" }) },
      { label: "Switch workspace: Research", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Research" }) },
      { label: "Switch workspace: Incident Response", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Incident Response" }) },
      { label: "Add Workforce Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "workforce-summary" }) },
      { label: "Add Runtime Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "runtime", refId: workers[0] ? workerId(workers[0]) : undefined }) },
      { label: "Add Room Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "room", refId: data.rooms[0]?.name }) },
      { label: "Add Proposal Queue Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "proposal-queue" }) },
      { label: "Add Proposal Detail Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "proposal-detail", refId: data.pending[0] ? proposalId(data.pending[0]) : undefined }) },
      { label: "Add Incident Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "incident" }) },
      { label: "Add Trace Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "trace" }) },
      { label: "Add Dead Letter Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "dead-letter" }) },
      { label: "Fit Canvas", run: () => dispatchCanvasCommand({ kind: "fit" }) },
      { label: "Reset Layout", run: () => dispatchCanvasCommand({ kind: "reset" }) },
      { label: "Clear Saved Layout", run: () => dispatchCanvasCommand({ kind: "clear-layout" }) },
      { label: "Focus Runtime", run: () => dispatchCanvasCommand({ kind: "focus-runtime" }) },
      { label: "Focus Room", run: () => dispatchCanvasCommand({ kind: "focus-room" }) },
      { label: "Focus Proposal", run: () => dispatchCanvasCommand({ kind: "focus-proposal" }) },
      { label: "Focus Trace", run: () => dispatchCanvasCommand({ kind: "focus-trace" }) },
      { label: "Go to Workforce", run: () => setView("workforce") },
      { label: "Go to Rooms", run: () => setView("rooms") },
      { label: "Go to Proposals", run: () => setView("proposals") },
      { label: "Go to Flight Recorder", run: () => setView("flight") },
      { label: "Go to Incidents", run: () => setView("incidents") },
      { label: "Search Runtime", run: () => setView("workforce") },
      { label: "Search Proposal", run: () => setView("proposals") },
      { label: "Search Trace", run: () => setView("flight") },
      { label: "Live Refresh", run: () => void refresh() },
    ],
    [data.pending, data.rooms, dispatchCanvasCommand, refresh, workers],
  );

  return (
    <div className="min-h-screen bg-abyss text-slate-100">
      <aside className="fixed inset-y-0 left-0 w-60 border-r border-line bg-panel">
        <div className="border-b border-line px-5 py-4">
          <div className="text-xs uppercase tracking-[0.28em] text-cyanop">SynKraken</div>
          <div className="mt-1 font-mono text-lg">Console v0.4</div>
        </div>
        <nav className="p-3">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? "nav-item-active" : ""}`}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="absolute bottom-0 left-0 right-0 border-t border-line p-4 font-mono text-[11px] text-muted">
          Agents propose.
          <br />
          Humans approve.
          <br />
          SynKraken records.
        </div>
      </aside>

      <main className="ml-60 min-h-screen pb-14">
        <TopBar
          data={data}
          online={daemonOnline}
          loading={initialLoading}
          refreshing={refreshing}
          error={globalError}
          workers={workers}
          onRefresh={() => void refresh(false)}
          onPalette={() => setPaletteOpen(true)}
        />
        {globalError && <OfflineState message={globalError} onRefresh={() => void refresh(false)} />}
        {!globalError && viewError && <InlineFault message={viewError} />}

        <section className="p-4">
          {view === "canvas" && (
            <OperationsCanvas
              data={data}
              workers={workers}
              selectedWorkspace={canvasWorkspace}
              selectedRoom={selectedRoom}
              selectedProposal={selectedProposal}
              command={canvasCommand}
              loading={initialLoading}
              refreshing={refreshing}
              daemonStatus={daemonStatus}
              globalError={globalError}
              nodeErrors={nodeErrors}
              onWorkspace={setCanvasWorkspace}
              onSelectRoom={setSelectedRoom}
              onOpenProposal={openProposal}
              onProposalAction={proposalAction}
              onReplay={(id) => void loadReplay(id)}
              onView={setView}
            />
          )}
          {view === "workforce" && (
            <WorkforceView
              workers={workers}
              proposals={data.proposals}
              selectedRuntime={selectedRuntime}
              onSelectRuntime={setSelectedRuntime}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "rooms" && (
            <RoomsView
              rooms={data.rooms}
              workers={workers}
              proposals={data.proposals}
              selectedRoom={selectedRoom}
              roomDetail={roomDetail}
              message={roomMessage}
              member={roomMember}
              onSelectRoom={setSelectedRoom}
              onMessage={setRoomMessage}
              onMember={setRoomMember}
              onSend={() => void sendRoomMessage()}
              onMemberAction={(action, adapterId) => void updateRoomMember(action, adapterId)}
            />
          )}
          {view === "flight" && (
            <FlightRecorderView
              replayId={replayId}
              replay={replay}
              filter={replayFilter}
              runtimeFilter={runtimeFilter}
              failureOnly={failureOnly}
              workers={workers}
              onReplayId={setReplayId}
              onLoad={() => void loadReplay()}
              onFilter={setReplayFilter}
              onRuntimeFilter={setRuntimeFilter}
              onFailureOnly={setFailureOnly}
            />
          )}
          {view === "proposals" && (
            <ProposalsView
              proposals={data.proposals}
              pending={data.pending}
              onOpen={openProposal}
              onAction={proposalAction}
            />
          )}
          {view === "proposal-detail" && (
            <ProposalDetail
              proposal={selectedProposal}
              proposalId={selectedProposalId}
              onAction={proposalAction}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "incidents" && (
            <IncidentsView
              workers={workers}
              workforceHealth={data.workforceHealth}
              incident={data.incident}
              deadLetters={data.deadLetters}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
        </section>
      </main>

      <CommandBar onPalette={() => setPaletteOpen(true)} />
      {paletteOpen && (
        <CommandPalette
          query={paletteQuery}
          commands={commands}
          workers={workers}
          proposals={data.proposals}
          onQuery={setPaletteQuery}
          onClose={() => setPaletteOpen(false)}
          onRuntime={(id) => {
            dispatchCanvasCommand({ kind: "focus-runtime", id });
          }}
          onProposal={(id) => void openProposal(id)}
          onTrace={(id) => dispatchCanvasCommand({ kind: "focus-trace", id })}
        />
      )}
    </div>
  );
}

function TopBar({
  data,
  workers,
  online,
  loading,
  refreshing,
  error,
  onRefresh,
  onPalette,
}: {
  data: AppData;
  workers: Agent[];
  online: boolean;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  onRefresh: () => void;
  onPalette: () => void;
}) {
  const counts = asRecord(data.workforceHealth?.summary || data.workforceHealth?.counts || data.workforce?.summary);
  const healthy = counts.healthy ?? workers.filter((worker) => workerHealth(worker) === "healthy").length;
  const degraded = counts.degraded ?? workers.filter((worker) => workerHealth(worker) === "degraded").length;
  const failing = counts.failing ?? workers.filter((worker) => workerHealth(worker) === "failing").length;
  const incidentCount = Array.isArray(data.workforceHealth?.recent_incidents)
    ? data.workforceHealth?.recent_incidents.length
    : workers.filter((worker) => text(workerReputation(worker).incident_summary, "").length > 0).length;

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-abyss/95 px-4 py-2 backdrop-blur">
      <div className="grid grid-cols-[1.4fr_2fr_auto] items-center gap-4">
        <button className="flex min-w-0 items-center gap-3 text-left font-mono text-xs" onClick={onPalette}>
          <span className={`status-dot ${online ? "bg-cyanop" : "bg-danger"}`} />
          <span className={online ? "text-cyanop" : "text-danger"}>
            daemon {online ? text(data.health?.status, "online") : "offline"}
          </span>
          <span className="truncate text-muted">{DAEMON_URL}</span>
        </button>
        <div className="status-strip">
          <StatusMetric label="agents" value={workers.length} />
          <StatusMetric label="healthy" value={healthy} tone="good" />
          <StatusMetric label="degraded" value={degraded} tone="warn" />
          <StatusMetric label="failing" value={failing} tone="danger" />
          <StatusMetric label="pending proposals" value={data.pending.length} tone="warn" />
          <StatusMetric label="incidents" value={incidentCount} tone={incidentCount ? "danger" : "good"} />
          <StatusMetric label="dead letters" value={data.deadLetters.length} tone={data.deadLetters.length ? "danger" : "good"} />
        </div>
        <div className="flex items-center justify-end gap-3 font-mono text-xs">
          {loading && <span className="text-amberop">loading</span>}
          {!loading && refreshing && <span className="text-amberop">polling</span>}
          {error && <span className="text-danger">fault</span>}
          <button className="btn" onClick={onRefresh}>Refresh</button>
        </div>
      </div>
    </header>
  );
}

function OperationsCanvas({
  data,
  workers,
  selectedWorkspace,
  selectedRoom,
  selectedProposal,
  command,
  loading,
  refreshing,
  daemonStatus,
  globalError,
  nodeErrors,
  onWorkspace,
  onSelectRoom,
  onOpenProposal,
  onProposalAction,
  onReplay,
  onView,
}: {
  data: AppData;
  workers: Agent[];
  selectedWorkspace: WorkspacePreset;
  selectedRoom: string;
  selectedProposal: Proposal | null;
  command: CanvasCommand | null;
  loading: boolean;
  refreshing: boolean;
  daemonStatus: DaemonStatus;
  globalError: string | null;
  nodeErrors: NodeErrors;
  onWorkspace: (workspace: WorkspacePreset) => void;
  onSelectRoom: (room: string) => void;
  onOpenProposal: (id: string) => void;
  onProposalAction: (id: string, action: "approve" | "reject" | "execute") => void;
  onReplay: (id: string) => void;
  onView: (view: View) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ mode: "pan" | "node"; id?: string; startX: number; startY: number; baseX: number; baseY: number } | null>(null);
  const layoutDirtyRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const [nodes, setNodes] = useState<CanvasNode[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [transform, setTransform] = useState({ x: 40, y: 40, scale: 1 });
  const [traceId, setTraceId] = useState("");
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [layoutRestored, setLayoutRestored] = useState(false);
  const [layoutInitialized, setLayoutInitialized] = useState(false);
  const [focusQuery, setFocusQuery] = useState("");

  const markLayoutDirty = useCallback(() => {
    layoutDirtyRef.current = true;
  }, []);

  const resetLayout = useCallback((workspace = selectedWorkspace) => {
    setNodes(createPresetNodes(workspace, workers, data.rooms, data.pending.length ? data.pending : data.proposals, data.deadLetters));
    setSelectedNode(null);
    setTransform({ x: 40, y: 40, scale: 1 });
  }, [data.deadLetters, data.pending, data.proposals, data.rooms, selectedWorkspace, workers]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(canvasStorageKey);
      if (raw) {
        const saved = JSON.parse(raw) as { selectedWorkspace?: WorkspacePreset; nodes?: CanvasNode[]; transform?: { x: number; y: number; scale: number } };
        if (saved.selectedWorkspace && workspacePresets.includes(saved.selectedWorkspace)) onWorkspace(saved.selectedWorkspace);
        if (Array.isArray(saved.nodes) && saved.nodes.length) {
          setNodes(saved.nodes);
          setLayoutRestored(true);
          setLayoutInitialized(true);
        }
        if (saved.transform && Number.isFinite(saved.transform.scale)) setTransform(saved.transform);
        return;
      }
    } catch {
      window.localStorage.removeItem(canvasStorageKey);
    }
    if (workers.length || data.rooms.length || data.proposals.length || data.deadLetters.length) {
      resetLayout(selectedWorkspace);
      setLayoutInitialized(true);
    }
  }, []);

  useEffect(() => {
    if (!layoutRestored && !layoutInitialized && (workers.length || data.rooms.length || data.proposals.length || data.deadLetters.length)) {
      resetLayout(selectedWorkspace);
      setLayoutInitialized(true);
    }
  }, [data.deadLetters.length, data.proposals.length, data.rooms.length, layoutInitialized, layoutRestored, resetLayout, selectedWorkspace, workers.length]);

  useEffect(() => {
    if (!layoutDirtyRef.current) return;
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      window.localStorage.setItem(canvasStorageKey, JSON.stringify({ selectedWorkspace, nodes, transform }));
      layoutDirtyRef.current = false;
      saveTimerRef.current = null;
    }, 350);
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    };
  }, [nodes, selectedWorkspace, transform]);

  const saveLayoutNow = useCallback(() => {
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    window.localStorage.setItem(canvasStorageKey, JSON.stringify({ selectedWorkspace, nodes, transform }));
    layoutDirtyRef.current = false;
    saveTimerRef.current = null;
  }, [nodes, selectedWorkspace, transform]);

  const addNode = useCallback((nodeType: CanvasNodeType, refId?: string) => {
    const nodeId = `${nodeType}:${refId || "primary"}`;
    setNodes((current) => {
      if (current.some((node) => node.id === nodeId)) return current;
      markLayoutDirty();
      return [...current, createNode(nodeType, 160 + current.length * 28, 140 + current.length * 28, refId)];
    });
    setSelectedNode(nodeId);
    return nodeId;
  }, []);

  const focusNode = useCallback((id: string) => {
    const node = nodes.find((item) => item.id === id);
    if (!node) return;
    const bounds = viewportRef.current?.getBoundingClientRect();
    setSelectedNode(id);
    if (bounds) {
      setTransform((current) => ({
        ...current,
        x: bounds.width / 2 - (node.x + node.width / 2) * current.scale,
        y: bounds.height / 2 - (node.y + node.height / 2) * current.scale,
      }));
    }
  }, [nodes]);

  const focusOrCreateNode = useCallback((nodeType: CanvasNodeType, refId?: string) => {
    const id = `${nodeType}:${refId || "primary"}`;
    const existing = nodes.find((node) => node.id === id);
    const nextNode = existing || createNode(nodeType, 160 + nodes.length * 28, 140 + nodes.length * 28, refId);
    if (!existing) {
      markLayoutDirty();
      setNodes((current) => current.some((node) => node.id === id) ? current : [...current, nextNode]);
    }
    setSelectedNode(id);
    const bounds = viewportRef.current?.getBoundingClientRect();
    if (bounds) {
      setTransform((current) => ({
        ...current,
        x: bounds.width / 2 - (nextNode.x + nextNode.width / 2) * current.scale,
        y: bounds.height / 2 - (nextNode.y + nextNode.height / 2) * current.scale,
      }));
    }
    if (nodeType === "trace" && refId) setTraceId(refId);
    return id;
  }, [markLayoutDirty, nodes]);

  const fitCanvas = useCallback(() => {
    if (!nodes.length) return;
    const bounds = viewportRef.current?.getBoundingClientRect();
    if (!bounds) return;
    const minX = Math.min(...nodes.map((node) => node.x));
    const minY = Math.min(...nodes.map((node) => node.y));
    const maxX = Math.max(...nodes.map((node) => node.x + node.width));
    const maxY = Math.max(...nodes.map((node) => node.y + node.height));
    const scale = Math.min(1.1, Math.max(0.35, Math.min((bounds.width - 96) / (maxX - minX), (bounds.height - 96) / (maxY - minY))));
    markLayoutDirty();
    setTransform({
      scale,
      x: bounds.width / 2 - ((minX + maxX) / 2) * scale,
      y: bounds.height / 2 - ((minY + maxY) / 2) * scale,
    });
  }, [markLayoutDirty, nodes]);

  useEffect(() => {
    if (!command) return;
    if (command.kind === "workspace") {
      onWorkspace(command.workspace);
      markLayoutDirty();
      resetLayout(command.workspace);
    }
    if (command.kind === "add") focusOrCreateNode(command.nodeType, command.refId);
    if (command.kind === "fit") fitCanvas();
    if (command.kind === "reset") {
      markLayoutDirty();
      resetLayout(selectedWorkspace);
    }
    if (command.kind === "clear-layout") {
      window.localStorage.removeItem(canvasStorageKey);
      setLayoutRestored(false);
      markLayoutDirty();
      resetLayout(selectedWorkspace);
    }
    if (command.kind === "focus-runtime") {
      const id = command.id || (workers[0] ? workerId(workers[0]) : "");
      if (id) {
        focusOrCreateNode("runtime", id);
      }
    }
    if (command.kind === "focus-room") focusOrCreateNode("room", command.id || text(data.rooms[0]?.name, "ops"));
    if (command.kind === "focus-proposal") {
      const id = command.id || proposalId(data.pending[0] || data.proposals[0] || {});
      focusOrCreateNode("proposal-detail", id || undefined);
    }
    if (command.kind === "focus-trace") {
      const id = command.id || traceId || proposalId(data.pending[0] || data.proposals[0] || {});
      focusOrCreateNode("trace", id || undefined);
    }
  }, [command, data.pending, data.proposals, data.rooms, fitCanvas, focusOrCreateNode, markLayoutDirty, onWorkspace, resetLayout, selectedWorkspace, traceId, workers]);

  const loadTrace = useCallback(async (id = traceId) => {
    if (!id.trim()) return;
    try {
      const result = await api.getTrace(id.trim());
      setTrace(result);
      setTraceId(id.trim());
      setTraceError(null);
    } catch (loadError) {
      setTrace(null);
      setTraceError(loadError instanceof Error ? loadError.message : "Trace load failed");
    }
  }, [traceId]);

  const onMouseMove = useCallback((event: MouseEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (drag.mode === "pan") {
      markLayoutDirty();
      setTransform((current) => ({ ...current, x: drag.baseX + dx, y: drag.baseY + dy }));
      return;
    }
    if (drag.id) {
      markLayoutDirty();
      setNodes((current) => current.map((node) => node.id === drag.id
        ? { ...node, x: drag.baseX + dx / transform.scale, y: drag.baseY + dy / transform.scale }
        : node));
    }
  }, [markLayoutDirty, transform.scale]);

  const relationships = useMemo(() => buildRelationships(nodes, data.canvasRelationships), [data.canvasRelationships, nodes]);
  const selectedCanvasNode = nodes.find((node) => node.id === selectedNode) || null;
  const focusCanvasQuery = useCallback(() => {
    const target = inferCanvasTarget(focusQuery, workers, data.rooms, data.proposals, data.deadLetters);
    focusOrCreateNode(target.type, target.refId);
    if (target.type === "room" && target.refId) onSelectRoom(target.refId);
    if (target.type === "proposal-detail" && target.refId) onOpenProposal(target.refId);
  }, [data.deadLetters, data.proposals, data.rooms, focusOrCreateNode, focusQuery, onOpenProposal, onSelectRoom, workers]);

  return (
    <div className="operations-shell">
      <div className="canvas-toolbar">
        <div>
          <h1 className="font-mono text-xl text-slate-50">Operations Canvas</h1>
          <p className="text-xs text-muted">Spatial AI workforce control plane · saved locally</p>
        </div>
        <div className="toolbar">
          {workspacePresets.map((workspace) => (
            <button
              key={workspace}
              className={`seg ${selectedWorkspace === workspace ? "seg-active" : ""}`}
              onClick={() => {
                onWorkspace(workspace);
                markLayoutDirty();
                resetLayout(workspace);
              }}
            >
              {workspace}
            </button>
          ))}
          <input
            className="input canvas-focus-input"
            value={focusQuery}
            onChange={(event) => setFocusQuery(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") focusCanvasQuery(); }}
            placeholder="focus runtime, #room, proposal, trace"
          />
          <button className="btn-cyan" onClick={focusCanvasQuery}>Focus</button>
          <select
            className="input canvas-add-select"
            value=""
            onChange={(event) => {
              const nodeType = event.target.value as CanvasNodeType;
              if (nodeType) focusOrCreateNode(nodeType);
            }}
          >
            <option value="">add node</option>
            <option value="workforce-summary">Workforce</option>
            <option value="runtime">Runtime</option>
            <option value="room">Room</option>
            <option value="proposal-queue">Proposal Queue</option>
            <option value="proposal-detail">Proposal Detail</option>
            <option value="incident">Incident</option>
            <option value="trace">Trace</option>
            <option value="dead-letter">Dead Letter</option>
          </select>
          <button className="btn" onClick={fitCanvas}>Fit</button>
          <button className="btn" onClick={() => { markLayoutDirty(); resetLayout(selectedWorkspace); }}>Reset Layout</button>
          <button className="btn" onClick={() => { window.localStorage.removeItem(canvasStorageKey); setLayoutRestored(false); markLayoutDirty(); resetLayout(selectedWorkspace); }}>Clear Saved</button>
          <button className="btn-cyan" onClick={saveLayoutNow}>Save Layout</button>
        </div>
      </div>
      <div className="canvas-main">
        <div
          className="canvas-viewport"
          ref={viewportRef}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              dragRef.current = { mode: "pan", startX: event.clientX, startY: event.clientY, baseX: transform.x, baseY: transform.y };
            }
          }}
          onMouseMove={onMouseMove}
          onMouseUp={() => { dragRef.current = null; }}
          onMouseLeave={() => { dragRef.current = null; }}
          onWheel={(event) => {
            event.preventDefault();
            const next = Math.max(0.45, Math.min(1.6, transform.scale - event.deltaY * 0.001));
            markLayoutDirty();
            setTransform((current) => ({ ...current, scale: next }));
          }}
        >
          <div className="canvas-world" style={{ transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})` }}>
            <svg className="relationship-layer" width="2400" height="1600" viewBox="0 0 2400 1600">
              {relationships.map((line) => (
                <line
                  key={line.id}
                  x1={line.x1}
                  y1={line.y1}
                  x2={line.x2}
                  y2={line.y2}
                  className={`relationship-line relationship-${line.tone}`}
                />
              ))}
            </svg>
            {nodes.map((node) => {
              const tone = nodeTone(node.type, node, workers, data.pending, data.deadLetters);
              const nodeError = nodeErrors[node.id] || (node.type === "room" && node.refId && !data.rooms.some((room) => room.name === node.refId) ? "Room not found" : undefined);
              return (
                <CanvasNodePanel
                  key={node.id}
                  node={node}
                  selected={selectedNode === node.id}
                  tone={tone}
                  data={data}
                  workers={workers}
                  selectedRoom={selectedRoom}
                  selectedProposal={selectedProposal}
                  traceId={traceId}
                  trace={trace}
                  traceError={traceError}
                  loading={loading}
                  refreshing={refreshing}
                  daemonStatus={daemonStatus}
                  error={nodeError || globalError}
                  onSelect={() => setSelectedNode(node.id)}
                  onDragStart={(event) => {
                    event.stopPropagation();
                    setSelectedNode(node.id);
                    dragRef.current = { mode: "node", id: node.id, startX: event.clientX, startY: event.clientY, baseX: node.x, baseY: node.y };
                  }}
                  onSelectRoom={onSelectRoom}
                  onOpenProposal={onOpenProposal}
                  onProposalAction={onProposalAction}
                  onTraceId={setTraceId}
                  onLoadTrace={() => void loadTrace()}
                  onReplay={onReplay}
                  onView={onView}
                />
              );
            })}
          </div>
        </div>
        <CanvasInspector
          node={selectedCanvasNode}
          data={data}
          workers={workers}
          trace={trace}
          relationships={data.canvasRelationships.filter((relationship) => {
            if (!selectedCanvasNode) return false;
            const nodeType = selectedCanvasNode.type;
            const nodeId = selectedCanvasNode.refId || "primary";
            return (
              (relationship.source_type === nodeType && relationship.source_id === nodeId)
              || (relationship.target_type === nodeType && relationship.target_id === nodeId)
            );
          })}
          onFocus={focusOrCreateNode}
          onSelectRoom={onSelectRoom}
          onOpenProposal={onOpenProposal}
          onProposalAction={onProposalAction}
          onReplay={onReplay}
          onView={onView}
        />
      </div>
    </div>
  );
}

function buildRelationships(nodes: CanvasNode[], canvasRelationships: CanvasRelationship[]) {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const center = (node: CanvasNode) => ({ x: node.x + node.width / 2, y: node.y + node.height / 2 });
  const lines: { id: string; x1: number; y1: number; x2: number; y2: number; tone: "normal" | "pending" | "failing"; relationship: CanvasRelationship }[] = [];
  const add = (from?: CanvasNode, to?: CanvasNode, relationship?: CanvasRelationship) => {
    if (!relationship) return;
    if (!from || !to) return;
    const a = center(from);
    const b = center(to);
    const rawTone = text(relationship.tone || relationship.status, "normal");
    const tone = rawTone === "failing" || rawTone === "pending" ? rawTone : "normal";
    lines.push({ id: relationship.id, x1: a.x, y1: a.y, x2: b.x, y2: b.y, tone, relationship });
  };

  canvasRelationships.forEach((relationship) => {
    const source = nodeMap.get(`${relationship.source_type}:${relationship.source_id || "primary"}`);
    const target = nodeMap.get(`${relationship.target_type}:${relationship.target_id || "primary"}`);
    add(source, target, relationship);
  });

  return lines;
}

function CanvasNodePanel({
  node,
  selected,
  tone,
  data,
  workers,
  selectedRoom,
  selectedProposal,
  traceId,
  trace,
  traceError,
  loading,
  refreshing,
  daemonStatus,
  error,
  onSelect,
  onDragStart,
  onSelectRoom,
  onOpenProposal,
  onProposalAction,
  onTraceId,
  onLoadTrace,
  onReplay,
  onView,
}: {
  node: CanvasNode;
  selected: boolean;
  tone: string;
  data: AppData;
  workers: Agent[];
  selectedRoom: string;
  selectedProposal: Proposal | null;
  traceId: string;
  trace: TraceResponse | null;
  traceError: string | null;
  loading: boolean;
  refreshing: boolean;
  daemonStatus: DaemonStatus;
  error: string | null;
  onSelect: () => void;
  onDragStart: (event: MouseEvent<HTMLElement>) => void;
  onSelectRoom: (room: string) => void;
  onOpenProposal: (id: string) => void;
  onProposalAction: (id: string, action: "approve" | "reject" | "execute") => void;
  onTraceId: (id: string) => void;
  onLoadTrace: () => void;
  onReplay: (id: string) => void;
  onView: (view: View) => void;
}) {
  return (
    <article
      className={`canvas-node canvas-node-${tone} ${selected ? "canvas-node-selected" : ""}`}
      style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
      onMouseDown={onSelect}
    >
      <header className="canvas-node-header" onMouseDown={onDragStart}>
        <span>{node.type.replace("-", " ")}</span>
        <strong>{node.title}</strong>
        <em>{loading ? "loading" : error ? "warning" : refreshing ? "polling" : tone}</em>
      </header>
      <div className="canvas-node-meta">
        <span>{node.refId || "daemon"}</span>
        <span>{shortDate(new Date().toISOString())}</span>
      </div>
      <div className="canvas-node-body">
        {error && <div className="text-xs text-danger">{error}</div>}
        {node.type === "workforce-summary" && <WorkforceSummaryNode data={data} workers={workers} daemonStatus={daemonStatus} />}
        {node.type === "runtime" && <RuntimeNode node={node} workers={workers} onView={onView} />}
        {node.type === "room" && <RoomNode node={node} data={data} selectedRoom={selectedRoom} onSelectRoom={onSelectRoom} onView={onView} />}
        {node.type === "proposal-queue" && <ProposalQueueNode proposals={data.pending} onOpen={onOpenProposal} onAction={onProposalAction} onView={onView} />}
        {node.type === "proposal-detail" && <ProposalDetailNode node={node} proposal={selectedProposal || data.proposals.find((proposal) => proposalId(proposal) === node.refId) || null} onAction={onProposalAction} onReplay={onReplay} />}
        {node.type === "incident" && <IncidentNode data={data} workers={workers} onView={onView} onReplay={onReplay} />}
        {node.type === "trace" && <TraceNode traceId={traceId || node.refId || ""} trace={trace} traceError={traceError} onTraceId={onTraceId} onLoadTrace={onLoadTrace} onReplay={onReplay} />}
        {node.type === "dead-letter" && <DeadLetterNode data={data} onReplay={onReplay} />}
      </div>
    </article>
  );
}

function CanvasInspector({
  node,
  data,
  workers,
  trace,
  relationships,
  onFocus,
  onSelectRoom,
  onOpenProposal,
  onProposalAction,
  onReplay,
  onView,
}: {
  node: CanvasNode | null;
  data: AppData;
  workers: Agent[];
  trace: TraceResponse | null;
  relationships: CanvasRelationship[];
  onFocus: (nodeType: CanvasNodeType, refId?: string) => string;
  onSelectRoom: (room: string) => void;
  onOpenProposal: (id: string) => void;
  onProposalAction: (id: string, action: "approve" | "reject" | "execute") => void;
  onReplay: (id: string) => void;
  onView: (view: View) => void;
}) {
  if (!node) {
    return (
      <aside className="canvas-inspector">
        <div className="canvas-inspector-title">Canvas Inspector</div>
        <EmptyPanel label="Select a node to inspect daemon object detail." />
      </aside>
    );
  }
  const tone = nodeTone(node.type, node, workers, data.pending, data.deadLetters);
  const runtime = node.type === "runtime" ? workers.find((worker) => workerId(worker) === node.refId) : null;
  const room = node.type === "room" ? data.rooms.find((item) => item.name === node.refId) : null;
  const proposal = node.type === "proposal-detail" ? data.proposals.find((item) => proposalId(item) === node.refId) : null;
  const latestDeadLetter = asRecord(data.deadLetters[0]);

  return (
    <aside className="canvas-inspector">
      <div className="canvas-inspector-title">Canvas Inspector</div>
      <div className="canvas-inspector-section">
        <Field label="node type" value={node.type} />
        <Field label="status" value={tone} />
        <Field label="object id" value={node.refId || "primary"} />
        <Field label="position" value={`${Math.round(node.x)}, ${Math.round(node.y)}`} />
      </div>

      {node.type === "workforce-summary" && (
        <div className="canvas-inspector-section">
          <Field label="workers" value={workers.length} />
          <Field label="pending proposals" value={data.pending.length} />
          <Field label="dead letters" value={data.deadLetters.length} />
          <button className="btn-cyan" onClick={() => onView("workforce")}>Open Workforce</button>
        </div>
      )}

      {node.type === "runtime" && runtime && (
        <div className="canvas-inspector-section">
          <Field label="health" value={workerHealth(runtime)} />
          <Field label="trust" value={percent(workerReputation(runtime).trust_score ?? runtime.trust_score ?? runtime.trust)} />
          <Field label="cost tier" value={text(runtime.cost_tier || workerReputation(runtime).cost_tier, "medium")} />
          <Field label="incident" value={text(workerReputation(runtime).incident_summary || runtime.incident_summary, "none")} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} />
          <button className="btn-cyan" onClick={() => onView("workforce")}>Open Runtime Detail</button>
        </div>
      )}

      {node.type === "room" && (
        <div className="canvas-inspector-section">
          <Field label="room" value={`#${node.refId || "ops"}`} />
          <Field label="members" value={room?.member_count ?? 0} />
          <Field label="last activity" value={shortDate(room?.last_activity)} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} />
          <button className="btn-cyan" onClick={() => { onSelectRoom(node.refId || "ops"); onView("rooms"); }}>Open Room</button>
        </div>
      )}

      {node.type === "proposal-queue" && (
        <div className="canvas-inspector-section">
          <Field label="pending" value={data.pending.length} />
          <Field label="highest visible risk" value={text(data.pending[0]?.risk || data.pending[0]?.risk_level, "none")} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} />
          <button className="btn-cyan" onClick={() => onView("proposals")}>Open Governance</button>
        </div>
      )}

      {node.type === "proposal-detail" && proposal && (
        <div className="canvas-inspector-section">
          <Field label="status" value={proposal.status} />
          <Field label="risk" value={proposal.risk || proposal.risk_level} />
          <Field label="proposer" value={proposal.proposed_by || proposal.proposer} />
          <Field label="room" value={proposal.room_id || proposal.room || "-"} />
          <ProposalActions id={proposalId(proposal)} onAction={onProposalAction} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} onReplay={onReplay} />
        </div>
      )}

      {node.type === "incident" && (
        <div className="canvas-inspector-section">
          <Field label="failing runtimes" value={workers.filter((worker) => ["failing", "unstable"].includes(workerHealth(worker))).map(workerId).join(", ") || "none"} />
          <Field label="dead letters" value={data.deadLetters.length} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onReplay={onReplay} />
          <button className="btn-cyan" onClick={() => onView("incidents")}>Open Incident View</button>
        </div>
      )}

      {node.type === "trace" && (
        <div className="canvas-inspector-section">
          <Field label="trace id" value={node.refId || "manual"} />
          <Field label="timeline events" value={Array.isArray(trace?.timeline) ? trace.timeline.length : 0} />
          <Field label="dead letters" value={Array.isArray(trace?.dead_letters) ? trace.dead_letters.length : 0} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} onReplay={onReplay} />
          {node.refId && <button className="btn-cyan" onClick={() => onReplay(node.refId || "")}>Open Replay</button>}
        </div>
      )}

      {node.type === "dead-letter" && (
        <div className="canvas-inspector-section">
          <Field label="count" value={data.deadLetters.length} />
          <Field label="latest runtime" value={text(latestDeadLetter.adapter_id || latestDeadLetter.target || latestDeadLetter.source, "none")} />
          <Field label="latest reason" value={text(latestDeadLetter.reason || latestDeadLetter.error || latestDeadLetter.status, "none")} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onReplay={onReplay} />
        </div>
      )}

      <div className="canvas-inspector-section">
        <Field label="relationships" value={relationships.length} />
        <div className="mini-list">
          {relationships.slice(0, 4).map((line) => (
            <div className="canvas-mini-row" key={line.id}>
              <span>{line.id}</span>
              <span>{line.tone}</span>
            </div>
          ))}
          {!relationships.length && <span className="text-xs text-muted">No daemon relationship records touch this node.</span>}
        </div>
      </div>
    </aside>
  );
}

function RelationshipJumpRow({
  relationships,
  onFocus,
  onOpenProposal,
  onReplay,
}: {
  relationships: CanvasRelationship[];
  onFocus: (nodeType: CanvasNodeType, refId?: string) => string;
  onOpenProposal?: (id: string) => void;
  onReplay?: (id: string) => void;
}) {
  if (!relationships.length) {
    return <span className="text-xs text-muted">No daemon relationship jumps returned.</span>;
  }
  return (
    <div className="chip-row">
      {relationships.slice(0, 8).map((relationship) => {
        const targetType = relationship.target_type as CanvasNodeType;
        const targetId = text(relationship.target_id, "primary");
        return (
          <button
            className="chip"
            key={relationship.id}
            onClick={() => {
              onFocus(targetType, targetId === "primary" ? undefined : targetId);
              if (targetType === "proposal-detail" && onOpenProposal && targetId !== "primary") onOpenProposal(targetId);
              if (targetType === "trace" && onReplay && targetId !== "primary") onReplay(targetId);
            }}
            title={text(asRecord(relationship.evidence).table || asRecord(relationship.evidence).source || relationship.kind, relationship.kind)}
          >
            {relationship.kind} · {targetType}:{targetId}
          </button>
        );
      })}
    </div>
  );
}

function WorkforceSummaryNode({ data, workers, daemonStatus }: { data: AppData; workers: Agent[]; daemonStatus: DaemonStatus }) {
  const failing = workers.filter((worker) => ["failing", "unstable"].includes(workerHealth(worker))).length;
  const degraded = workers.filter((worker) => workerHealth(worker) === "degraded").length;
  const healthy = workers.filter((worker) => workerHealth(worker) === "healthy").length;
  return (
    <div className="node-grid">
      <Field label="daemon" value={daemonStatus === "offline" ? "offline" : text(data.health?.status, daemonStatus)} />
      <Field label="active agents" value={workers.length} />
      <Field label="healthy" value={healthy} />
      <Field label="degraded" value={degraded} />
      <Field label="failing" value={failing} />
      <Field label="pending proposals" value={data.pending.length} />
      <Field label="incidents" value={failing + (data.deadLetters.length ? 1 : 0)} />
      <Field label="dead letters" value={data.deadLetters.length} />
    </div>
  );
}

function RuntimeNode({ node, workers, onView }: { node: CanvasNode; workers: Agent[]; onView: (view: View) => void }) {
  const worker = workers.find((item) => workerId(item) === node.refId);
  if (!worker) return <EmptyPanel label="Runtime not returned by daemon." />;
  const reputation = workerReputation(worker);
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="health" value={workerHealth(worker)} />
        <Field label="trust" value={percent(reputation.trust_score ?? worker.trust_score ?? worker.trust)} />
        <Field label="cost tier" value={text(worker.cost_tier || reputation.cost_tier, "medium")} />
        <Field label="usage risk" value={text(worker.usage_risk || reputation.usage_risk, "unknown")} />
        <Field label="latest delivery" value={text(reputation.latest_delivery_status || worker.latest_delivery_status, "none")} />
        <Field label="incident" value={text(reputation.incident_summary || worker.incident_summary, "none")} />
      </div>
      <button className="btn-cyan" onClick={() => onView("workforce")}>Focus Runtime Detail</button>
    </div>
  );
}

function RoomNode({ node, data, selectedRoom, onSelectRoom, onView }: { node: CanvasNode; data: AppData; selectedRoom: string; onSelectRoom: (room: string) => void; onView: (view: View) => void }) {
  const roomName = node.refId || selectedRoom;
  const room = data.rooms.find((item) => item.name === roomName);
  const roomProposals = data.proposals.filter((proposal) => text(proposal.room_id || proposal.room, "") === roomName);
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="room" value={`#${roomName}`} />
        <Field label="members" value={room?.member_count ?? 0} />
        <Field label="recent messages" value="open Rooms view" />
        <Field label="last activity" value={shortDate(room?.last_activity)} />
      </div>
      <textarea className="textarea canvas-textarea" placeholder="@everyone or @runtime message via Rooms view" readOnly />
      <div className="flex gap-2">
        <button className="btn-cyan" onClick={() => { onSelectRoom(roomName); onView("rooms"); }}>Open Room</button>
        <span className="pill status-warn">{roomProposals.length} proposals</span>
      </div>
    </div>
  );
}

function ProposalQueueNode({ proposals, onOpen, onAction, onView }: { proposals: Proposal[]; onOpen: (id: string) => void; onAction: (id: string, action: "approve" | "reject" | "execute") => void; onView: (view: View) => void }) {
  return (
    <div className="mini-list">
      {proposals.slice(0, 6).map((proposal) => {
        const id = proposalId(proposal);
        return (
          <div className="canvas-mini-row" key={id}>
            <button className="link-button" onClick={() => onOpen(id)}>{text(proposal.title || proposal.summary, id)}</button>
            <span className={`pill ${statusClass(proposal.risk || proposal.risk_level)}`}>{text(proposal.risk || proposal.risk_level, "risk")}</span>
            <span>{text(proposal.proposed_by || proposal.proposer, "unknown")}</span>
            <div className="flex gap-1">
              <button className="micro-btn" onClick={() => onAction(id, "approve")}>approve</button>
              <button className="micro-btn" onClick={() => onAction(id, "reject")}>reject</button>
              <button className="micro-btn" onClick={() => onAction(id, "execute")}>execute</button>
            </div>
          </div>
        );
      })}
      {!proposals.length && <EmptyPanel label="No pending proposals." />}
      <button className="btn mt-2" onClick={() => onView("proposals")}>Open Proposal Governance</button>
    </div>
  );
}

function ProposalDetailNode({ node, proposal, onAction, onReplay }: { node: CanvasNode; proposal: Proposal | null; onAction: (id: string, action: "approve" | "reject" | "execute") => void; onReplay: (id: string) => void }) {
  if (!proposal) return <EmptyPanel label="No selected proposal detail." />;
  const id = proposalId(proposal) || node.refId || "";
  return (
    <div className="space-y-3">
      <Field label="status" value={proposal.status} />
      <Field label="risk" value={proposal.risk || proposal.risk_level} />
      <Field label="approval reason" value={proposal.approval_reason || proposal.governance_reason} />
      <p className="line-clamp-node text-sm text-slate-200">{text(proposal.summary || proposal.details, "No proposal summary returned.")}</p>
      <div className="chip-row">
        {proposalLinks(proposal).slice(0, 5).map((link) => <button className="chip" key={link} onClick={() => onReplay(link)}>{link}</button>)}
      </div>
      <ProposalActions id={id} onAction={onAction} />
    </div>
  );
}

function IncidentNode({ data, workers, onView, onReplay }: { data: AppData; workers: Agent[]; onView: (view: View) => void; onReplay: (id: string) => void }) {
  const failing = workers.filter((worker) => ["failing", "unstable"].includes(workerHealth(worker)));
  const latest = asRecord(data.deadLetters[0]);
  const traceId = text(latest.message_id || latest.conversation_id || latest.dead_letter_id, "");
  return (
    <div className="space-y-3">
      <Field label="latest incident" value={traceId || text(asRecord(data.incident?.incident).summary, "No incident returned.")} />
      <Field label="failing runtimes" value={failing.map(workerId).join(", ") || "none"} />
      <Field label="recommended action" value={failing.length ? "Inspect runtime and trace before retry." : "Monitor workforce health."} />
      <div className="flex gap-2">
        {traceId && <button className="btn" onClick={() => onReplay(traceId)}>Focus Trace</button>}
        <button className="btn-cyan" onClick={() => onView("incidents")}>Open Incidents</button>
      </div>
    </div>
  );
}

function TraceNode({ traceId, trace, traceError, onTraceId, onLoadTrace, onReplay }: { traceId: string; trace: TraceResponse | null; traceError: string | null; onTraceId: (id: string) => void; onLoadTrace: () => void; onReplay: (id: string) => void }) {
  const events = ((trace?.timeline || trace?.messages || []) as unknown[]).map(asRecord).slice(0, 10);
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input className="input" value={traceId} onChange={(event) => onTraceId(event.target.value)} placeholder="trace id" />
        <button className="btn-cyan" onClick={onLoadTrace}>Load</button>
      </div>
      {traceError && <div className="text-xs text-danger">{traceError}</div>}
      <div className="mini-list">
        {events.map((event, index) => (
          <div className="canvas-mini-row" key={index}>
            <span className="text-cyanop">{text(event.event_type || event.type || event.kind, "event")}</span>
            <span>{shortDate(event.timestamp || event.created_at)}</span>
            <span>{text(event.source || event.actor || event.status, "recorded")}</span>
          </div>
        ))}
        {!events.length && <EmptyPanel label="Load a trace to inspect summarized events." />}
      </div>
      {traceId && <button className="btn" onClick={() => onReplay(traceId)}>Open Replay</button>}
    </div>
  );
}

function DeadLetterNode({ data, onReplay }: { data: AppData; onReplay: (id: string) => void }) {
  return (
    <div className="mini-list">
      <Field label="dead letters" value={data.deadLetters.length} />
      {data.deadLetters.slice(0, 6).map((item, index) => {
        const record = asRecord(item);
        const id = text(record.message_id || record.conversation_id || record.dead_letter_id || record.delivery_id, "");
        return (
          <div className="canvas-mini-row" key={`${id}-${index}`}>
            <span>{text(record.adapter_id || record.target || record.source, "runtime")}</span>
            <span className="text-danger">{text(record.reason || record.error || record.status, "failed")}</span>
            {id && <button className="micro-btn" onClick={() => onReplay(id)}>replay</button>}
          </div>
        );
      })}
      {!data.deadLetters.length && <EmptyPanel label="No dead letters returned." />}
    </div>
  );
}

function WorkforceView({
  workers,
  proposals,
  selectedRuntime,
  onSelectRuntime,
  onReplay,
}: {
  workers: Agent[];
  proposals: Proposal[];
  selectedRuntime: string | null;
  onSelectRuntime: (runtime: string | null) => void;
  onReplay: (id: string) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("health");
  const selected = workers.find((worker) => workerId(worker) === selectedRuntime) || null;
  const sorted = [...workers].sort((left, right) => {
    if (sortKey === "health") return (healthRank[workerHealth(left)] ?? 2) - (healthRank[workerHealth(right)] ?? 2);
    if (sortKey === "trust") return workerTrust(right) - workerTrust(left);
    if (sortKey === "latency") return workerLatency(left) - workerLatency(right);
    return workerIncidentCount(right) - workerIncidentCount(left);
  });

  return (
    <div className="space-y-4">
      <SectionHeader title="Workforce Command Centre" subtitle="Runtime health, trust, latency, weak replies, and incidents." />
      <div className="toolbar">
        {(["health", "trust", "latency", "incidents"] as SortKey[]).map((key) => (
          <button key={key} className={`seg ${sortKey === key ? "seg-active" : ""}`} onClick={() => setSortKey(key)}>
            sort {key}
          </button>
        ))}
      </div>
      <Panel title="Runtime Operations Table" flush>
        <div className="ops-table ops-table-workforce">
          <div className="ops-head">
            <span>Runtime</span><span>Health</span><span>Trust</span><span>Status</span><span>Last Seen</span><span>Cost Tier</span><span>Average Latency</span><span>Recent Failures</span><span>Recent Empty Replies</span>
          </div>
          {sorted.map((worker) => {
            const reputation = workerReputation(worker);
            const id = workerId(worker);
            return (
              <button key={id} className={`ops-row ${selectedRuntime === id ? "ops-row-active" : ""}`} onClick={() => onSelectRuntime(id)}>
                <span className="runtime-cell">{id}</span>
                <span className={`pill ${statusClass(workerHealth(worker))}`}>{workerHealth(worker)}</span>
                <span>{percent(reputation.trust_score ?? worker.trust_score ?? worker.trust)}</span>
                <span>{text(worker.status || reputation.latest_delivery_status, "unknown")}</span>
                <span>{shortDate(reputation.last_seen || reputation.last_success || reputation.last_failure || worker.last_seen)}</span>
                <span>{text(worker.cost_tier || reputation.cost_tier, "medium")}</span>
                <span>{duration(reputation.avg_duration_ms ?? worker.avg_duration_ms)}</span>
                <span>{numberText(reputation.recent_failures ?? reputation.failures)}</span>
                <span>{numberText(reputation.recent_empty_replies ?? reputation.empty_replies)}</span>
              </button>
            );
          })}
          {!sorted.length && <EmptyPanel label="No enabled adapter workers returned." />}
        </div>
      </Panel>
      {selected && (
        <RuntimeDrawer runtime={selected} proposals={proposals} onClose={() => onSelectRuntime(null)} onReplay={onReplay} />
      )}
    </div>
  );
}

function RuntimeDrawer({
  runtime,
  proposals,
  onClose,
  onReplay,
}: {
  runtime: Agent;
  proposals: Proposal[];
  onClose: () => void;
  onReplay: (id: string) => void;
}) {
  const id = workerId(runtime);
  const reputation = workerReputation(runtime);
  const linked = proposals.filter((proposal) => text(proposal.proposed_by || proposal.proposer, "") === id);
  const traceIds = [
    text(reputation.latest_message_id, ""),
    text(reputation.latest_conversation_id, ""),
    ...linked.flatMap(proposalLinks),
  ].filter(Boolean);

  return (
    <aside className="drawer">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-mono text-xl text-slate-50">{id}</h2>
          <p className="text-sm text-muted">{text(runtime.type || runtime.runtime_type, "adapter worker")}</p>
        </div>
        <button className="btn" onClick={onClose}>Close</button>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-4">
        <Field label="health" value={workerHealth(runtime)} />
        <Field label="trust" value={percent(reputation.trust_score ?? runtime.trust_score ?? runtime.trust)} />
        <Field label="avg latency" value={duration(reputation.avg_duration_ms ?? runtime.avg_duration_ms)} />
        <Field label="cost tier" value={text(runtime.cost_tier || reputation.cost_tier, "medium")} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel title="Reputation Summary">
          <div className="compact-grid">
            <Field label="deliveries" value={numberText(reputation.total_deliveries)} />
            <Field label="success" value={numberText(reputation.successful_replies)} />
            <Field label="timeouts" value={numberText(reputation.timeouts)} />
            <Field label="empty replies" value={numberText(reputation.empty_replies)} />
            <Field label="wrong identity" value={numberText(reputation.wrong_identity)} />
            <Field label="suspicious" value={numberText(reputation.suspicious_output)} />
          </div>
        </Panel>
        <Panel title="Incident Summary">
          <p className="text-sm text-slate-200">{text(reputation.incident_summary || runtime.incident_summary, "No current incident summary.")}</p>
          <p className="mt-3 text-xs text-muted">Recommended action: {workerHealth(runtime) === "failing" ? "Disable adapter until repaired." : "Monitor delivery quality and latency."}</p>
        </Panel>
        <Panel title="Proposal History">
          <div className="compact-grid">
            <Field label="created" value={numberText(reputation.proposals_created)} />
            <Field label="rejected" value={numberText(reputation.proposals_rejected)} />
            <Field label="cancelled" value={numberText(reputation.proposals_cancelled)} />
            <Field label="executed" value={numberText(reputation.proposals_executed)} />
          </div>
        </Panel>
      </div>
      <Panel title="Linked Traces">
        <div className="chip-row">
          {traceIds.slice(0, 12).map((traceId) => (
            <button className="chip" key={traceId} onClick={() => onReplay(traceId)}>{traceId}</button>
          ))}
          {!traceIds.length && <span className="text-sm text-muted">No linked trace ids surfaced by daemon records.</span>}
        </div>
      </Panel>
      <details className="raw-details">
        <summary>Raw runtime data</summary>
        <pre className="json-block mt-2">{prettyJson(runtime)}</pre>
      </details>
    </aside>
  );
}

function RoomsView({
  rooms,
  workers,
  proposals,
  selectedRoom,
  roomDetail,
  message,
  member,
  onSelectRoom,
  onMessage,
  onMember,
  onSend,
  onMemberAction,
}: {
  rooms: Room[];
  workers: Agent[];
  proposals: Proposal[];
  selectedRoom: string;
  roomDetail: RoomDetail;
  message: string;
  member: string;
  onSelectRoom: (room: string) => void;
  onMessage: (value: string) => void;
  onMember: (value: string) => void;
  onSend: () => void;
  onMemberAction: (action: "add" | "remove", adapterId: string) => void;
}) {
  const knownRooms = ["ops", "coding", "research", "security"];
  const allRooms = [
    ...knownRooms.map((name) => rooms.find((room) => room.name === name) || { name, member_count: 0 }),
    ...rooms.filter((room) => !knownRooms.includes(text(room.name, ""))),
  ];
  const members = (roomDetail.room?.members || []) as Record<string, unknown>[];
  const roomProposals = proposals.filter((proposal) => text(proposal.room_id || proposal.room, "") === selectedRoom);

  return (
    <div className="grid gap-4 xl:grid-cols-[280px_1fr_360px]">
      <section className="space-y-3">
        <SectionHeader title="Rooms" subtitle="Persistent operator spaces and room-scoped broadcasts." />
        {allRooms.map((room) => {
          const name = text(room.name, "room");
          return (
            <button key={name} className={`room-tab ${selectedRoom === name ? "room-tab-active" : ""}`} onClick={() => onSelectRoom(name)}>
              <span>#{name}</span>
              <span>{numberText(room.member_count)} members</span>
            </button>
          );
        })}
      </section>
      <section className="space-y-4">
        <Panel title={`#${selectedRoom} Room View`}>
          <div className="grid gap-4 lg:grid-cols-3">
            <Field label="members" value={members.length || roomDetail.room?.member_count || 0} />
            <Field label="recent activity" value={shortDate(roomDetail.room?.last_activity)} />
            <Field label="proposal activity" value={roomProposals.length} />
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <TokenText value={text(roomDetail.memory?.notes || roomDetail.memory?.current_focus || roomDetail.memory?.objective, "No room notes returned.")} />
          </div>
        </Panel>
        <Panel title="Recent Activity">
          <div className="message-list">
            {roomDetail.messages.map((item) => (
              <article className="message-row" key={item.message_id || `${item.source}-${item.timestamp}`}>
                <div className="message-meta">
                  <span>{text(item.source, "unknown")}</span>
                  <span>{shortDate(item.timestamp)}</span>
                </div>
                <TokenText value={text(item.body, "[empty reply]")} />
              </article>
            ))}
            {!roomDetail.messages.length && <EmptyPanel label="No room history returned." />}
          </div>
        </Panel>
      </section>
      <section className="space-y-4">
        <Panel title="Members">
          <div className="chip-row">
            {members.map((memberRecord) => {
              const adapterId = text(memberRecord.adapter_id || memberRecord.id, "");
              return (
                <button className="chip" key={adapterId} onClick={() => onMemberAction("remove", adapterId)}>
                  @{adapterId} remove
                </button>
              );
            })}
            {!members.length && <span className="text-sm text-muted">No members returned for this room.</span>}
          </div>
          <div className="mt-4 flex gap-2">
            <input className="input" value={member} onChange={(event) => onMember(event.target.value)} placeholder="runtime id" list="runtime-list" />
            <button className="btn-cyan" onClick={() => onMemberAction("add", member)}>Add</button>
            <datalist id="runtime-list">
              {workers.map((worker) => <option value={workerId(worker)} key={workerId(worker)} />)}
            </datalist>
          </div>
        </Panel>
        <Panel title="Broadcast To Room">
          <textarea className="textarea" value={message} onChange={(event) => onMessage(event.target.value)} placeholder={`#${selectedRoom} @everyone status check`} />
          <button className="btn-cyan mt-3 w-full" onClick={onSend}>Broadcast</button>
        </Panel>
        <Panel title="Latest Deliveries / Proposals">
          <div className="mini-list">
            {roomProposals.slice(0, 8).map((proposal) => (
              <div className="mini-row" key={proposalId(proposal)}>
                <span>{text(proposal.title, "proposal")}</span>
                <span className={statusClass(proposal.status)}>{text(proposal.status)}</span>
              </div>
            ))}
            {!roomProposals.length && <span className="text-sm text-muted">No room-linked proposals returned.</span>}
          </div>
        </Panel>
      </section>
    </div>
  );
}

function FlightRecorderView({
  replayId,
  replay,
  filter,
  runtimeFilter,
  failureOnly,
  workers,
  onReplayId,
  onLoad,
  onFilter,
  onRuntimeFilter,
  onFailureOnly,
}: {
  replayId: string;
  replay: ReplayResponse | null;
  filter: ReplayFilter;
  runtimeFilter: string;
  failureOnly: boolean;
  workers: Agent[];
  onReplayId: (value: string) => void;
  onLoad: () => void;
  onFilter: (filter: ReplayFilter) => void;
  onRuntimeFilter: (value: string) => void;
  onFailureOnly: (value: boolean) => void;
}) {
  const events = ((replay?.timeline || []) as unknown[]).map(asRecord);
  const filtered = events.filter((event) => {
    const kind = eventKind(event);
    if (filter !== "all" && kind !== filter) return false;
    if (failureOnly && !containsFailure(event)) return false;
    if (runtimeFilter && !`${text(event.actor || event.source, "")} ${text(event.target, "")}`.toLowerCase().includes(runtimeFilter.toLowerCase())) return false;
    return true;
  });
  const summary = replaySummary(events);

  return (
    <div className="space-y-4">
      <SectionHeader title="Flight Recorder" subtitle="Timeline replay for conversations, tasks, goals, decisions, handoffs, proposals, incidents, and failures." />
      <div className="toolbar">
        <input className="input" value={replayId} onChange={(event) => onReplayId(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") onLoad(); }} placeholder="replay id, trace id, proposal id, task id, goal id, decision id, or handoff id" />
        <button className="btn-cyan" onClick={onLoad}>Replay</button>
      </div>
      <Panel title="Replay Summary">
        <div className="grid gap-3 md:grid-cols-5">
          <Metric label="messages" value={summary.messages} />
          <Metric label="proposals" value={summary.proposals} />
          <Metric label="handoffs" value={summary.handoffs} />
          <Metric label="failures" value={summary.failures} />
          <Metric label="outcome" value={text(asRecord(replay?.summary).outcome || replay?.kind, "unknown")} />
        </div>
      </Panel>
      <div className="toolbar">
        {(["all", "message", "reply", "handoff", "proposal", "approval", "execution", "incident", "failure"] as ReplayFilter[]).map((item) => (
          <button className={`seg ${filter === item ? "seg-active" : ""}`} key={item} onClick={() => onFilter(item)}>{item}</button>
        ))}
        <select className="input max-w-xs" value={runtimeFilter} onChange={(event) => onRuntimeFilter(event.target.value)}>
          <option value="">all runtimes</option>
          {workers.map((worker) => <option value={workerId(worker)} key={workerId(worker)}>{workerId(worker)}</option>)}
        </select>
        <label className="check-label"><input type="checkbox" checked={failureOnly} onChange={(event) => onFailureOnly(event.target.checked)} /> failures only</label>
      </div>
      <Panel title="Visual Timeline">
        <Timeline items={filtered} />
      </Panel>
      {replay && (
        <details className="raw-details">
          <summary>Raw replay data</summary>
          <pre className="json-block mt-2">{prettyJson(replay)}</pre>
        </details>
      )}
    </div>
  );
}

function ProposalsView({
  proposals,
  pending,
  onOpen,
  onAction,
}: {
  proposals: Proposal[];
  pending: Proposal[];
  onOpen: (id: string) => void;
  onAction: (id: string, action: "approve" | "reject" | "execute") => void;
}) {
  return (
    <div className="space-y-4">
      <SectionHeader title="Proposal Governance" subtitle="Execution authority queue with risk, approval requirement, room, goal, and trace links." />
      <Panel title={`Pending Queue (${pending.length})`} flush>
        <ProposalRows proposals={pending} onOpen={onOpen} onAction={onAction} queue />
      </Panel>
      <Panel title={`All Proposals (${proposals.length})`} flush>
        <ProposalRows proposals={proposals} onOpen={onOpen} onAction={onAction} />
      </Panel>
    </div>
  );
}

function ProposalRows({
  proposals,
  onOpen,
  onAction,
  queue = false,
}: {
  proposals: Proposal[];
  onOpen: (id: string) => void;
  onAction: (id: string, action: "approve" | "reject" | "execute") => void;
  queue?: boolean;
}) {
  if (!proposals.length) return <EmptyPanel label="No proposals returned." />;
  return (
    <div className="ops-table ops-table-proposals">
      <div className="ops-head">
        <span>Risk</span><span>Approval</span><span>Proposer</span><span>Room</span><span>Goal</span><span>Timestamp</span><span>Proposal</span><span>Actions</span>
      </div>
      {proposals.map((proposal) => {
        const id = proposalId(proposal);
        return (
          <div className={`ops-row ${queue ? "queue-row" : ""}`} key={id}>
            <span className={`pill ${statusClass(proposal.risk || proposal.risk_level)}`}>{text(proposal.risk || proposal.risk_level, "risk")}</span>
            <span>{text(proposal.requires_approval ?? proposal.approval_required, "unknown")}</span>
            <span>{text(proposal.proposed_by || proposal.proposer, "unknown")}</span>
            <span>{text(proposal.room_id || proposal.room, "-")}</span>
            <span>{text(proposal.goal_id || proposal.goal, "-")}</span>
            <span>{shortDate(proposal.created_at)}</span>
            <button className="link-button" onClick={() => onOpen(id)}>{text(proposal.title || proposal.summary, "Untitled proposal")}</button>
            <ProposalActions id={id} onAction={onAction} />
          </div>
        );
      })}
    </div>
  );
}

function ProposalActions({
  id,
  onAction,
}: {
  id: string;
  onAction: (id: string, action: "approve" | "reject" | "execute") => void;
}) {
  return (
    <div className="flex shrink-0 gap-2">
      <button className="btn-cyan" onClick={() => onAction(id, "approve")}>Approve</button>
      <button className="btn" onClick={() => onAction(id, "reject")}>Reject</button>
      <button className="btn-amber" onClick={() => onAction(id, "execute")}>Execute</button>
    </div>
  );
}

function ProposalDetail({
  proposal,
  proposalId,
  onAction,
  onReplay,
}: {
  proposal: Proposal | null;
  proposalId: string | null;
  onAction: (id: string, action: "approve" | "reject" | "execute") => void;
  onReplay: (id: string) => void;
}) {
  if (!proposalId) return <EmptyPanel label="Select a proposal." />;
  if (!proposal) return <EmptyPanel label="Loading proposal detail." />;
  const links = proposalLinks(proposal);
  return (
    <div className="space-y-4">
      <SectionHeader title="Proposal Detail" subtitle={proposalId} />
      <ProposalActions id={proposalId} onAction={onAction} />
      <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <Panel title="Full Proposal">
          <h2 className="font-mono text-xl text-slate-50">{text(proposal.title, "Untitled proposal")}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-200">{text(proposal.summary || proposal.details, "No proposal summary returned.")}</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Field label="type" value={text(proposal.proposal_type || proposal.type)} />
            <Field label="room" value={text(proposal.room_id || proposal.room, "-")} />
            <Field label="goal" value={text(proposal.goal_id || proposal.goal, "-")} />
          </div>
        </Panel>
        <Panel title="Governance Evaluation">
          <div className="compact-grid">
            <Field label="status" value={text(proposal.status)} />
            <Field label="risk" value={text(proposal.risk || proposal.risk_level)} />
            <Field label="approval required" value={text(proposal.requires_approval ?? proposal.approval_required)} />
            <Field label="proposer" value={text(proposal.proposed_by || proposal.proposer)} />
          </div>
          <p className="mt-4 border-t border-line pt-4 text-sm text-slate-200">{text(proposal.governance_reason || proposal.approval_reason, "No governance reason returned.")}</p>
        </Panel>
      </div>
      <Panel title="Linked Traces / Decisions / Handoffs">
        <div className="chip-row">
          {[proposalId, ...links].filter(Boolean).map((link) => (
            <button className="chip" key={link} onClick={() => onReplay(link)}>{link}</button>
          ))}
        </div>
      </Panel>
      <Panel title="Proposal Events">
        <Timeline items={(proposal.events || []).map(asRecord)} />
      </Panel>
      <details className="raw-details">
        <summary>Raw proposal data</summary>
        <pre className="json-block mt-2">{prettyJson(proposal)}</pre>
      </details>
    </div>
  );
}

function IncidentsView({
  workers,
  workforceHealth,
  incident,
  deadLetters,
  onReplay,
}: {
  workers: Agent[];
  workforceHealth?: WorkforceHealthResponse;
  incident?: IncidentResponse;
  deadLetters: unknown[];
  onReplay: (id: string) => void;
}) {
  const failing = workers.filter((worker) => ["failing", "unstable"].includes(workerHealth(worker)));
  const activeIncidents = [
    ...failing.map((worker) => ({ type: "runtime", runtime: workerId(worker), summary: text(workerReputation(worker).incident_summary || worker.incident_summary, "Runtime is degraded."), raw: worker })),
    ...deadLetters.slice(0, 8).map((item) => ({ type: "dead_letter", runtime: text(asRecord(item).adapter_id, "unknown"), summary: text(asRecord(item).reason, "Dead letter recorded."), raw: item })),
  ];
  const recentIncidents = (workforceHealth?.recent_incidents || []) as unknown[];

  return (
    <div className="space-y-4">
      <SectionHeader title="Incident Centre" subtitle="Active incidents, failing runtimes, dead letters, and operator recovery actions." />
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="active incidents" value={activeIncidents.length} />
        <Metric label="failing runtimes" value={failing.length} />
        <Metric label="dead letters" value={deadLetters.length} />
        <Metric label="recent incident notes" value={recentIncidents.length} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {activeIncidents.map((item, index) => {
          const raw = asRecord(item.raw);
          const replayId = text(raw.message_id || raw.conversation_id || raw.delivery_id || raw.dead_letter_id, "");
          return (
            <article className="incident-card" key={`${item.type}-${item.runtime}-${index}`}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-mono text-lg text-slate-50">{item.runtime}</h2>
                  <div className="mt-1 text-sm text-danger">Status: {item.type === "runtime" ? text(workerHealth(item.raw as Agent), "Failing") : "Dead letter"}</div>
                </div>
                {replayId && <button className="btn" onClick={() => onReplay(replayId)}>Trace</button>}
              </div>
              <p className="mt-4 text-sm text-slate-200">{item.summary}</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <Field label="first seen" value={shortDate(raw.created_at || raw.last_failure)} />
                <Field label="last seen" value={shortDate(raw.updated_at || raw.created_at || raw.last_seen)} />
                <Field label="empty replies" value={numberText(raw.empty_replies || raw.recent_empty_replies)} />
                <Field label="timeouts" value={numberText(raw.timeouts || raw.recent_timeouts)} />
              </div>
              <div className="mt-4 border-t border-line pt-3 text-sm">
                <span className="text-muted">Recommended action: </span>
                <span className="text-amberop">{item.type === "runtime" ? "Disable adapter until repaired." : "Inspect replay before retrying."}</span>
              </div>
              <details className="raw-details mt-3">
                <summary>Raw incident data</summary>
                <pre className="json-block mt-2">{prettyJson(item.raw)}</pre>
              </details>
            </article>
          );
        })}
        {!activeIncidents.length && <EmptyPanel label="No active incidents or dead letters returned." />}
      </div>
      <details className="raw-details">
        <summary>Latest incident raw context</summary>
        <pre className="json-block mt-2">{prettyJson(incident || {})}</pre>
      </details>
    </div>
  );
}

function CommandPalette({
  query,
  commands,
  workers,
  proposals,
  onQuery,
  onClose,
  onRuntime,
  onProposal,
  onTrace,
}: {
  query: string;
  commands: { label: string; run: () => void }[];
  workers: Agent[];
  proposals: Proposal[];
  onQuery: (value: string) => void;
  onClose: () => void;
  onRuntime: (id: string) => void;
  onProposal: (id: string) => void;
  onTrace: (id: string) => void;
}) {
  const normalized = query.toLowerCase();
  const runtimeMatches = workers.filter((worker) => workerId(worker).toLowerCase().includes(normalized)).slice(0, 6);
  const proposalMatches = proposals.filter((proposal) => `${proposalId(proposal)} ${text(proposal.title, "")}`.toLowerCase().includes(normalized)).slice(0, 6);
  const commandMatches = commands.filter((command) => command.label.toLowerCase().includes(normalized));

  return (
    <div className="fixed inset-0 z-50 bg-black/70 p-10" onClick={onClose}>
      <div className="mx-auto max-w-2xl border border-line bg-panel shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <div className="border-b border-line px-4 py-3 font-mono text-sm text-cyanop">Command Palette</div>
        <div className="border-b border-line p-3">
          <input className="input w-full" autoFocus value={query} onChange={(event) => onQuery(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && query.trim()) {
              onTrace(query.trim());
              onClose();
            }
          }} placeholder="go to, runtime id, proposal id, trace id" />
        </div>
        <div className="max-h-[60vh] overflow-auto p-2">
          {commandMatches.map((command) => (
            <button key={command.label} className="command-row" onClick={() => { command.run(); onClose(); }}>{command.label}</button>
          ))}
          {runtimeMatches.map((worker) => (
            <button key={workerId(worker)} className="command-row" onClick={() => { onRuntime(workerId(worker)); onClose(); }}>Search Runtime · {workerId(worker)}</button>
          ))}
          {proposalMatches.map((proposal) => (
            <button key={proposalId(proposal)} className="command-row" onClick={() => { onProposal(proposalId(proposal)); onClose(); }}>Search Proposal · {proposalId(proposal)} · {text(proposal.title, "untitled")}</button>
          ))}
          {query.trim() && (
            <button className="command-row" onClick={() => { onTrace(query.trim()); onClose(); }}>Search Trace · {query.trim()}</button>
          )}
        </div>
      </div>
    </div>
  );
}

function replaySummary(events: Record<string, unknown>[]): {
  messages: number;
  proposals: number;
  handoffs: number;
  failures: number;
} {
  return events.reduce<{
    messages: number;
    proposals: number;
    handoffs: number;
    failures: number;
  }>(
    (summary, event) => {
      const kind = eventKind(event);
      if (kind === "message") summary.messages += 1;
      if (kind === "proposal" || kind === "approval" || kind === "execution") summary.proposals += 1;
      if (kind === "handoff") summary.handoffs += 1;
      if (kind === "failure" || kind === "incident") summary.failures += 1;
      return summary;
    },
    { messages: 0, proposals: 0, handoffs: 0, failures: 0 },
  );
}

function TokenText({ value }: { value: string }) {
  const parts = value.split(/(@everyone|@[a-zA-Z0-9_.-]+|#[a-zA-Z0-9_-]+)/g);
  return (
    <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-200">
      {parts.map((part, index) => part.startsWith("@") || part.startsWith("#")
        ? <span className="mention" key={`${part}-${index}`}>{part}</span>
        : <span key={`${part}-${index}`}>{part}</span>)}
    </p>
  );
}

function Timeline({ items }: { items: Record<string, unknown>[] }) {
  if (!items.length) return <div className="text-sm text-muted">No timeline events returned.</div>;
  return (
    <div className="timeline">
      {items.map((item, index) => {
        const kind = eventKind(item);
        return (
          <article className={`timeline-item timeline-${kind}`} key={index}>
            <div className="timeline-pin" />
            <div className="grid gap-3 md:grid-cols-[160px_1fr_180px_160px]">
              <div>
                <div className="font-mono text-xs uppercase text-cyanop">{kind}</div>
                <div className="mt-1 text-xs text-muted">{shortDate(item.timestamp || item.created_at)}</div>
              </div>
              <div>
                <div className="font-mono text-sm text-slate-100">{text(item.event_type || item.type || item.kind, "event")}</div>
                <p className="mt-1 text-sm text-slate-300">{text(item.summary || item.action || item.details || item.body || item.reason, "No event summary returned.")}</p>
              </div>
              <Field label="actor" value={text(item.actor || item.source, "unknown")} />
              <Field label="outcome" value={text(item.outcome || item.status, "recorded")} />
            </div>
            <details className="raw-details mt-3">
              <summary>Raw event</summary>
              <pre className="json-block mt-2">{prettyJson(item)}</pre>
            </details>
          </article>
        );
      })}
    </div>
  );
}

function OfflineState({ message, onRefresh }: { message: string; onRefresh: () => void }) {
  return (
    <div className="border-b border-danger/60 bg-danger/10 px-5 py-3 font-mono text-sm text-danger">
      Daemon unavailable at {DAEMON_URL}: {message}
      <button className="btn ml-4" onClick={onRefresh}>Retry</button>
    </div>
  );
}

function InlineFault({ message }: { message: string }) {
  return (
    <div className="border-b border-amberop/50 bg-amberop/10 px-5 py-2 font-mono text-xs text-amberop">
      Endpoint warning: {message}
    </div>
  );
}

function CommandBar({ onPalette }: { onPalette: () => void }) {
  return (
    <div className="fixed bottom-0 left-60 right-0 z-20 flex h-12 items-center gap-3 border-t border-line bg-panel px-4 font-mono text-xs">
      <button className="command-trigger flex-1 text-left" onClick={onPalette}>
        Ctrl+K · Workforce · Rooms · Proposals · Flight Recorder · Incidents · Search Runtime · Search Proposal · Search Trace
      </button>
      <span className="text-muted">live polling 4s</span>
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h1 className="font-mono text-2xl text-slate-50">{title}</h1>
      <p className="mt-1 text-sm text-muted">{subtitle}</p>
    </div>
  );
}

function Panel({ title, children, flush = false }: { title: string; children: ReactNode; flush?: boolean }) {
  return (
    <section className={`border border-line bg-panel ${flush ? "" : "p-4"}`}>
      <h2 className={`font-mono text-sm uppercase tracking-[0.18em] text-cyanop ${flush ? "border-b border-line px-4 py-3" : "mb-3"}`}>{title}</h2>
      <div className={flush ? "" : undefined}>{children}</div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="border border-line bg-panel2 p-3">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">{label}</div>
      <div className="mt-2 font-mono text-xl text-slate-100">{text(value, "0")}</div>
    </div>
  );
}

function StatusMetric({ label, value, tone = "neutral" }: { label: string; value: unknown; tone?: "neutral" | "good" | "warn" | "danger" }) {
  return (
    <div className={`status-metric status-${tone}`}>
      <span>{label}</span>
      <strong>{text(value, "0")}</strong>
    </div>
  );
}

function Field({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">{label}</div>
      <div className="mt-1 break-words text-sm text-slate-200">{text(value)}</div>
    </div>
  );
}

function EmptyPanel({ label }: { label: string }) {
  return <div className="border border-dashed border-line bg-panel/60 p-6 font-mono text-sm text-muted">{label}</div>;
}
