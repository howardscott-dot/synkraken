import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Agent,
  DAEMON_URL,
  HealthResponse,
  IncidentResponse,
  Proposal,
  ReplayResponse,
  Room,
  RoomMemory,
  RoomMessage,
  WorkforceHealthResponse,
  WorkforceResponse,
  api,
} from "./lib/api";
import { asRecord, duration, numberText, percent, prettyJson, shortDate, stringList, text } from "./lib/format";

type View = "workforce" | "rooms" | "flight" | "proposals" | "proposal-detail" | "incidents";
type SortKey = "health" | "trust" | "latency" | "incidents";
type ReplayFilter = "all" | "message" | "reply" | "handoff" | "proposal" | "approval" | "execution" | "incident" | "failure";

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
};

type RoomDetail = {
  room?: Room;
  messages: RoomMessage[];
  memory?: RoomMemory;
};

const initialData: AppData = {
  agents: [],
  proposals: [],
  pending: [],
  rooms: [],
  deadLetters: [],
};

const navItems: { id: View; label: string }[] = [
  { id: "workforce", label: "Workforce" },
  { id: "rooms", label: "Rooms" },
  { id: "flight", label: "Flight Recorder" },
  { id: "proposals", label: "Proposals" },
  { id: "incidents", label: "Incidents" },
];

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

export default function App() {
  const [view, setView] = useState<View>("workforce");
  const [data, setData] = useState<AppData>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  const daemonOnline = !error && Boolean(data.health);

  const workers = useMemo(() => {
    const workforceWorkers = (data.workforce?.workforce || data.workforce?.workers || data.workforce?.agents || []) as Agent[];
    return workforceWorkers.length ? workforceWorkers : data.agents;
  }, [data.agents, data.workforce]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [health, agents, workforce, workforceHealth, proposals, pending, rooms, incident, deadLetters] =
        await Promise.all([
          api.getHealth(),
          api.getAgents(),
          api.getWorkforce(),
          api.getWorkforceHealth(),
          api.getProposals(),
          api.getPendingProposals(),
          api.getRooms(),
          api.getLatestIncident(),
          api.getDeadLetters(100),
        ]);

      setData({
        health,
        agents: agents.agents || [],
        workforce,
        workforceHealth,
        proposals: proposals.proposals || [],
        pending: pending.proposals || [],
        rooms: rooms.rooms || [],
        incident,
        deadLetters: deadLetters.dead_letters || [],
      });
      setError(null);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Daemon unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRoom = useCallback(async (name: string) => {
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
      setError(null);
    } catch (roomError) {
      setRoomDetail({ messages: [] });
      setError(roomError instanceof Error ? roomError.message : "Room load failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    void loadRoom(selectedRoom);
  }, [loadRoom, selectedRoom]);

  useEffect(() => {
    const timer = window.setInterval(() => void loadRoom(selectedRoom), 5000);
    return () => window.clearInterval(timer);
  }, [loadRoom, selectedRoom]);

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
      setError(null);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "Proposal load failed");
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
        setError(null);
      } catch (actionError) {
        setError(actionError instanceof Error ? actionError.message : "Proposal action failed");
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
      setError(null);
    } catch (replayError) {
      setReplay(null);
      setError(replayError instanceof Error ? replayError.message : "Replay load failed");
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
      setError(sendError instanceof Error ? sendError.message : "Room broadcast failed");
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
      setError(memberError instanceof Error ? memberError.message : "Room membership update failed");
    }
  }, [loadRoom, refresh, selectedRoom]);

  const commands = useMemo(
    () => [
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
    [refresh],
  );

  return (
    <div className="min-h-screen bg-abyss text-slate-100">
      <aside className="fixed inset-y-0 left-0 w-60 border-r border-line bg-panel">
        <div className="border-b border-line px-5 py-4">
          <div className="text-xs uppercase tracking-[0.28em] text-cyanop">SynKraken</div>
          <div className="mt-1 font-mono text-lg">Console v0.2</div>
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
          loading={loading}
          error={error}
          workers={workers}
          onRefresh={() => void refresh()}
          onPalette={() => setPaletteOpen(true)}
        />
        {error && <OfflineState message={error} onRefresh={() => void refresh()} />}

        <section className="p-4">
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
            setSelectedRuntime(id);
            setView("workforce");
          }}
          onProposal={(id) => void openProposal(id)}
          onTrace={(id) => void loadReplay(id)}
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
  error,
  onRefresh,
  onPalette,
}: {
  data: AppData;
  workers: Agent[];
  online: boolean;
  loading: boolean;
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
          {loading && <span className="text-amberop">polling</span>}
          {error && <span className="text-danger">fault</span>}
          <button className="btn" onClick={onRefresh}>Refresh</button>
        </div>
      </div>
    </header>
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
