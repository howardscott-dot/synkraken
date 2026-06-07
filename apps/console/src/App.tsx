import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import {
  Agent,
  Assignment,
  AssignmentSummary,
  CanvasRelationship,
  DAEMON_URL,
  DeliveryRecord,
  DispatchResponse,
  HealthResponse,
  HandoffRecord,
  IncidentResponse,
  Mission,
  MissionSummary,
  Outcome,
  OutcomeSummary,
  Proposal,
  ReplayResponse,
  Room,
  RoomMemory,
  RoomMessage,
  TraceResponse,
  ActivityRecord,
  LiveActivitySummary,
  WorkforcePresenceResponse,
  WorkforcePresenceWorker,
  WorkforceHealthResponse,
  WorkforceMemory,
  WorkforceResponse,
  ApiError,
  api,
  ensureRuntime,
} from "./lib/api";
import { asRecord, duration, numberText, percent, prettyJson, shortDate, stringList, text } from "./lib/format";

type View = "home" | "projects" | "conversations" | "knowledge" | "workforce" | "advanced" | "work" | "governance" | "search" | "rooms" | "memory" | "activity" | "incidents" | "canvas" | "settings" | "briefing" | "missions" | "outcomes" | "assignments" | "flight" | "proposals" | "proposal-detail";
type SortKey = "health" | "trust" | "latency" | "incidents";
type ReplayFilter = "all" | "message" | "reply" | "handoff" | "proposal" | "approval" | "execution" | "incident" | "failure";
type WorkspacePreset = "Coding" | "Operations" | "Research" | "Incident Response";
type CanvasNodeType = "workforce-summary" | "briefing" | "runtime" | "room" | "mission" | "outcome" | "assignment" | "memory" | "proposal-queue" | "proposal-detail" | "incident" | "trace" | "dead-letter" | "activity-feed";

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
  workforcePresence?: WorkforcePresenceResponse;
  workforceHealth?: WorkforceHealthResponse;
  proposals: Proposal[];
  pending: Proposal[];
  missions: Mission[];
  missionSummary?: MissionSummary;
  outcomes: Outcome[];
  outcomeSummary?: OutcomeSummary;
  assignments: Assignment[];
  assignmentSummary?: AssignmentSummary;
  recentHandoffs: HandoffRecord[];
  rooms: Room[];
  incident?: IncidentResponse;
  deadLetters: unknown[];
  recentActivity: ActivityRecord[];
  liveActivitySummary?: LiveActivitySummary;
  canvasRelationships: CanvasRelationship[];
  memories: WorkforceMemory[];
};

type RoomDetail = {
  room?: Room;
  messages: RoomMessage[];
  memory?: RoomMemory;
};

type RoomOperationMode = "create" | "preset";

type DaemonStatus = "unknown" | "online" | "offline";
type DisplaySeverity = "Operational" | "Needs attention" | "Degraded" | "Blocked" | "Critical";
type OperatorWorkerStatus = "Available" | "Monitor" | "Avoid for now" | "Unavailable";
type OperatorPriority = "Needs action now" | "Watch list" | "Historical / low impact";
type MissionHealth = "Healthy" | "Watching" | "At Risk";
type OutcomeHealth = "On Track" | "Watching" | "Blocked";
type AssignmentHealth = "Assigned" | "In Progress" | "Waiting" | "Blocked";
type BriefingAction = { priority: number; label: string; detail: string; targetView: View; refId?: string };
type ProjectTab = "overview" | "conversations" | "knowledge" | "deliverables" | "team" | "decisions";
type ProjectRecord = {
  project_id: string;
  title: string;
  purpose: string;
  status: string;
  room_id?: string;
  mission_id?: string;
  outcome_ids: string[];
  assignment_ids: string[];
  knowledge_ids: string[];
  worker_ids: string[];
  created_at: string;
  updated_at: string;
  local?: boolean;
};
type ProjectTarget = { projectId?: string; tab?: ProjectTab; roomId?: string };
type ProjectKnowledgeDraft = { title: string; body: string; importance: string };
type ProjectHealth = "Healthy" | "Watching" | "Needs Review" | "Blocked" | "Quiet";
type ProjectRecommendation = {
  title: string;
  why: string;
  action: string;
  priority: number;
  tab: ProjectTab;
  proposalId?: string;
};
type ProjectInboxItem = {
  id: string;
  title: string;
  detail: string;
  timestamp?: string;
  tab: ProjectTab;
  proposalId?: string;
};
type DeliverableRecord = {
  deliverable_id: string;
  title: string;
  deliverable_type: string;
  status: string;
  owner?: string;
  updated_at?: string;
  source_type: string;
  source_id?: string;
};

type NodeErrors = Record<string, string | undefined>;

const initialData: AppData = {
  agents: [],
  proposals: [],
  pending: [],
  missions: [],
  outcomes: [],
  assignments: [],
  recentHandoffs: [],
  rooms: [],
  deadLetters: [],
  recentActivity: [],
  canvasRelationships: [],
  memories: [],
};

const navItems: { id: View; label: string }[] = [
  { id: "home", label: "Today" },
  { id: "projects", label: "Projects" },
  { id: "conversations", label: "Conversations" },
  { id: "knowledge", label: "Knowledge" },
  { id: "workforce", label: "Workers" },
  { id: "advanced", label: "More" },
];

const workspacePresets: WorkspacePreset[] = ["Coding", "Operations", "Research", "Incident Response"];
const canvasStorageKey = "synkraken.console.v03.operationsCanvasLayout";
const projectStorageKey = "synkraken.console.v20.projects";

const healthRank: Record<string, number> = {
  failing: 0,
  unstable: 1,
  degraded: 2,
  healthy: 3,
};

function proposalId(proposal: Proposal): string {
  return text(proposal.proposal_id || proposal.id, "");
}

function missionId(mission: Mission): string {
  return text(mission.mission_id, "");
}

function missionTitle(mission?: Mission | null): string {
  return text(mission?.title, mission?.mission_id || "Mission");
}

function outcomeId(outcome: Outcome): string {
  return text(outcome.outcome_id, "");
}

function outcomeTitle(outcome?: Outcome | null): string {
  return text(outcome?.title, outcome?.outcome_id || "Outcome");
}

function projectSlug(value: string): string {
  const slug = value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
  return slug || `project-${Date.now()}`;
}

function readStoredProjects(): ProjectRecord[] {
  try {
    return JSON.parse(localStorage.getItem(projectStorageKey) || "[]") as ProjectRecord[];
  } catch {
    return [];
  }
}

function writeStoredProjects(projects: ProjectRecord[]): void {
  localStorage.setItem(projectStorageKey, JSON.stringify(projects));
}

function projectId(project: ProjectRecord): string {
  return text(project.project_id, "");
}

function projectTitle(project?: ProjectRecord | null): string {
  return text(project?.title, project?.project_id || "Project");
}

function assignmentId(assignment: Assignment): string {
  return text(assignment.assignment_id || assignment.id, "");
}

function assignmentTitle(assignment?: Assignment | null): string {
  return text(assignment?.title, assignment?.assignment_id || assignment?.id || "Assignment");
}

function assignmentStatusLabel(status?: string): string {
  if (status === "in_progress") return "In Progress";
  return text(status, "assigned").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function assignmentHealth(assignment?: Assignment | null): AssignmentHealth {
  const status = text(assignment?.status, "assigned");
  if (status === "blocked") return "Blocked";
  if (status === "waiting" || status === "handoff") return "Waiting";
  if (status === "in_progress" || status === "review") return "In Progress";
  return "Assigned";
}

function assignmentAgeDays(assignment?: Assignment | null): number {
  const raw = text(assignment?.updated_at || assignment?.created_at, "");
  const timestamp = raw ? Date.parse(raw) : Number.NaN;
  if (!Number.isFinite(timestamp)) return 0;
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
}

function ageDaysFromTimestamp(value?: string | null): number {
  const raw = text(value, "");
  const timestamp = raw ? Date.parse(raw) : Number.NaN;
  if (!Number.isFinite(timestamp)) return Number.POSITIVE_INFINITY;
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
}

function assignmentMissionTitle(assignment: Assignment, missions: Mission[]): string {
  const mission = assignment.mission || missions.find((item) => missionId(item) === assignment.mission_id);
  return text(mission?.title || assignment.mission_id, "None");
}

function assignmentOutcomeTitle(assignment: Assignment, outcomes: Outcome[]): string {
  const outcome = assignment.outcome || outcomes.find((item) => outcomeId(item) === assignment.outcome_id);
  return text(outcome?.title || assignment.outcome_id, "None");
}

function deriveProjects(data: AppData, storedProjects: ProjectRecord[]): ProjectRecord[] {
  const storedIds = new Set(storedProjects.map(projectId));
  const missionProjects = data.missions
    .filter((mission) => !storedIds.has(`mission-${missionId(mission)}`))
    .map((mission) => {
      const missionAssignments = data.assignments.filter((assignment) => assignment.mission_id === missionId(mission));
      const missionOutcomes = data.outcomes.filter((outcome) => outcome.mission_id === missionId(mission));
      const roomId = text((mission.rooms || []).map(asRecord)[0]?.room_name || mission.room_id, "");
      return {
        project_id: `mission-${missionId(mission)}`,
        title: missionTitle(mission),
        purpose: text(mission.goal || mission.description || mission.outcome, "Coordinate related workforce activity."),
        status: text(mission.status, "active"),
        room_id: roomId || undefined,
        mission_id: missionId(mission),
        outcome_ids: missionOutcomes.map(outcomeId),
        assignment_ids: missionAssignments.map(assignmentId),
        knowledge_ids: data.memories.filter((memory) => text(memory.scope_type, "") === "mission" && text(memory.scope_id, "") === missionId(mission)).map(memoryId),
        worker_ids: Array.from(new Set([
          ...(mission.workers || []).map((worker) => text(asRecord(worker).adapter_id || asRecord(worker).runtime_id, "")),
          ...missionAssignments.flatMap((assignment) => [assignment.owner_worker || "", ...(assignment.contributor_workers || [])]),
        ].filter(Boolean))),
        created_at: text(mission.created_at || mission.updated_at, new Date().toISOString()),
        updated_at: text(mission.updated_at || mission.created_at, new Date().toISOString()),
      } satisfies ProjectRecord;
    });
  return [...storedProjects, ...missionProjects];
}

function projectAssignments(project: ProjectRecord, data: AppData): Assignment[] {
  return data.assignments.filter((assignment) =>
    project.assignment_ids.includes(assignmentId(assignment))
    || (!!project.mission_id && assignment.mission_id === project.mission_id)
    || (!!project.room_id && assignment.room_id === project.room_id),
  );
}

function projectOutcomes(project: ProjectRecord, data: AppData): Outcome[] {
  return data.outcomes.filter((outcome) =>
    project.outcome_ids.includes(outcomeId(outcome))
    || (!!project.mission_id && outcome.mission_id === project.mission_id),
  );
}

function projectKnowledge(project: ProjectRecord, data: AppData): WorkforceMemory[] {
  return data.memories.filter((memory) =>
    project.knowledge_ids.includes(memoryId(memory))
    || (!!project.mission_id && text(memory.scope_type, "") === "mission" && text(memory.scope_id, "") === project.mission_id)
    || (!!project.room_id && text(memory.scope_type, "") === "room" && text(memory.scope_id, "") === project.room_id),
  );
}

function projectWorkers(project: ProjectRecord, data: AppData, workers: Agent[]): string[] {
  const ids = new Set(project.worker_ids);
  projectAssignments(project, data).forEach((assignment) => {
    if (assignment.owner_worker) ids.add(assignment.owner_worker);
    (assignment.contributor_workers || []).forEach((workerIdValue) => ids.add(workerIdValue));
  });
  workers.forEach((worker) => {
    const id = workerId(worker);
    if (project.room_id && text(worker.current_room || worker.room_id, "") === project.room_id) ids.add(id);
  });
  return Array.from(ids).filter(Boolean);
}

function projectDeliverables(project: ProjectRecord, data: AppData): DeliverableRecord[] {
  const outcomes = projectOutcomes(project, data).map((outcome) => ({
    deliverable_id: `outcome-${outcomeId(outcome)}`,
    title: outcomeTitle(outcome),
    deliverable_type: "Deliverable",
    status: text(outcome.status, "open"),
    owner: text(outcome.owner, ""),
    updated_at: outcome.updated_at,
    source_type: "outcome",
    source_id: outcomeId(outcome),
  }));
  const assignments = projectAssignments(project, data)
    .filter((assignment) => ["review", "completed", "in_progress"].includes(text(assignment.status, "")))
    .map((assignment) => ({
      deliverable_id: `assignment-${assignmentId(assignment)}`,
      title: assignmentTitle(assignment),
      deliverable_type: text(assignment.deliverable_type || assignment.output_type, "Specification"),
      status: text(assignment.status, "open"),
      owner: assignment.owner_worker,
      updated_at: assignment.updated_at,
      source_type: "assignment",
      source_id: assignmentId(assignment),
    }));
  const proposals = data.proposals
    .filter((proposal) => (!!project.room_id && text(proposal.room_id || proposal.room, "") === project.room_id) || (!!project.mission_id && text(proposal.mission_id || proposal.goal_id, "") === project.mission_id))
    .map((proposal) => ({
      deliverable_id: `proposal-${proposalId(proposal)}`,
      title: text(proposal.title || proposal.summary, proposalId(proposal)),
      deliverable_type: "Proposal",
      status: text(proposal.status, "proposed"),
      owner: text(proposal.proposed_by || proposal.proposer, ""),
      updated_at: text(proposal.updated_at || proposal.created_at, ""),
      source_type: "proposal",
      source_id: proposalId(proposal),
    }));
  return [...outcomes, ...assignments, ...proposals];
}

function projectActivity(project: ProjectRecord, data: AppData): ActivityRecord[] {
  const assignments = new Set(projectAssignments(project, data).map(assignmentId));
  const outcomes = new Set(projectOutcomes(project, data).map(outcomeId));
  return meaningfulActivity(data).filter((item) =>
    (!!project.room_id && activityRoom(item) === project.room_id)
    || (!!project.mission_id && text(item.mission_id || item.goal_id, "") === project.mission_id)
    || (!!text(item.assignment_id, "") && assignments.has(text(item.assignment_id, "")))
    || (!!text(item.outcome_id, "") && outcomes.has(text(item.outcome_id, ""))),
  );
}

function projectHandoffs(project: ProjectRecord, data: AppData): HandoffRecord[] {
  const assignments = new Set(projectAssignments(project, data).map(assignmentId));
  return data.recentHandoffs.filter((handoff) =>
    project.assignment_ids.includes(text(handoff.assignment_id, ""))
    || assignments.has(text(handoff.assignment_id, "")),
  );
}

function projectLatestTimestamp(project: ProjectRecord, data: AppData): string {
  const candidates = [
    ...projectActivity(project, data).map((item) => text(item.timestamp, "")),
    ...projectDeliverables(project, data).map((item) => text(item.updated_at, "")),
    ...projectKnowledge(project, data).map((item) => text(item.updated_at || item.created_at, "")),
    ...projectHandoffs(project, data).map((item) => text(item.timestamp || item.created_at, "")),
    text(project.updated_at, ""),
  ].filter(Boolean);
  candidates.sort();
  return candidates[candidates.length - 1] || "";
}

function projectHealth(project: ProjectRecord, data: AppData): ProjectHealth {
  const decisions = projectDecisions(project, data);
  const hasCriticalDecision = decisions.pending.some((proposal) => ["critical", "high"].includes(text(proposal.risk || proposal.risk_level, "").toLowerCase()));
  const hasBlockedWork = projectAssignments(project, data).some((assignment) => assignmentHealth(assignment) === "Blocked")
    || projectOutcomes(project, data).some((outcome) => outcomeHealth(outcome, data.assignments) === "Blocked");
  if (hasCriticalDecision || hasBlockedWork) return "Blocked";
  if (decisions.pending.length || projectDeliverables(project, data).some((deliverable) => ["review", "proposed"].includes(text(deliverable.status, "")))) return "Needs Review";
  if (ageDaysFromTimestamp(projectLatestTimestamp(project, data)) >= 3) return "Watching";
  if (!projectActivity(project, data).length && !projectDeliverables(project, data).length) return "Quiet";
  return "Healthy";
}

function projectHealthDetail(project: ProjectRecord, data: AppData): string {
  const health = projectHealth(project, data);
  if (health === "Blocked") return "A blocker or high-risk decision needs operator attention.";
  if (health === "Needs Review") return "Produced work or a proposal is waiting for review.";
  if (health === "Watching") return "No meaningful activity has been recorded for several days.";
  if (health === "Quiet") return "The project has little activity recorded yet.";
  return "Recent activity is present and no project blockers are waiting.";
}

function projectRecommendations(project: ProjectRecord, data: AppData): ProjectRecommendation[] {
  const recommendations: ProjectRecommendation[] = [];
  const decisions = projectDecisions(project, data);
  const knowledge = projectKnowledge(project, data);
  const assignments = projectAssignments(project, data);
  const deliverables = projectDeliverables(project, data);
  const activeAssignments = assignments.filter((assignment) => ["assigned", "in_progress", "waiting", "review"].includes(text(assignment.status, "")));

  decisions.pending.slice(0, 3).forEach((proposal) => {
    recommendations.push({
      title: `${text(proposal.title || proposal.summary, proposalId(proposal))} Waiting`,
      why: `${text(proposal.proposed_by || proposal.proposer, "A worker")} submitted a proposal${proposal.created_at ? ` ${shortDate(proposal.created_at)}` : ""}.`,
      action: "Review proposal.",
      priority: ["critical", "high"].includes(text(proposal.risk || proposal.risk_level, "").toLowerCase()) ? 100 : 90,
      tab: "decisions",
      proposalId: proposalId(proposal),
    });
  });

  assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked").slice(0, 2).forEach((assignment) => {
    recommendations.push({
      title: `${assignmentTitle(assignment)} Blocked`,
      why: `${text(assignment.owner_worker, "No owner")} owns blocked project work.`,
      action: "Open deliverables.",
      priority: 85,
      tab: "deliverables",
    });
  });

  deliverables.filter((deliverable) => ["review", "proposed"].includes(text(deliverable.status, ""))).slice(0, 3).forEach((deliverable) => {
    recommendations.push({
      title: `${deliverable.title} Needs Review`,
      why: `${text(deliverable.owner, "The workforce")} produced a ${deliverable.deliverable_type.toLowerCase()}${deliverable.updated_at ? ` ${shortDate(deliverable.updated_at)}` : ""}.`,
      action: deliverable.source_type === "proposal" ? "Review decision." : "Review deliverable.",
      priority: 80,
      tab: deliverable.source_type === "proposal" ? "decisions" : "deliverables",
      proposalId: deliverable.source_type === "proposal" ? deliverable.source_id : undefined,
    });
  });

  projectHandoffs(project, data).filter((handoff) => !["accepted", "acknowledged", "completed"].includes(text(asRecord(handoff).status, "").toLowerCase())).slice(0, 2).forEach((handoff) => {
    recommendations.push({
      title: "Handoff Needs Acknowledgement",
      why: `${text(handoff.from_worker, "A worker")} handed work to ${text(handoff.to_worker, "another worker")}.`,
      action: "Review handoff.",
      priority: 70,
      tab: "decisions",
    });
  });

  projectOutcomes(project, data).filter((outcome) => !activeAssignments.some((assignment) => assignment.outcome_id === outcomeId(outcome))).slice(0, 2).forEach((outcome) => {
    recommendations.push({
      title: `${outcomeTitle(outcome)} Has No Active Assignment`,
      why: "An outcome is linked to this project, but no active assignment owns it.",
      action: "Start a project conversation.",
      priority: 60,
      tab: "conversations",
    });
  });

  if (!knowledge.length) {
    recommendations.push({
      title: "Capture Project Knowledge",
      why: "No project knowledge has been captured yet.",
      action: "Add knowledge.",
      priority: 50,
      tab: "knowledge",
    });
  }

  const latestAge = ageDaysFromTimestamp(projectLatestTimestamp(project, data));
  if (latestAge >= 3) {
    recommendations.push({
      title: "Project Has Been Quiet",
      why: `No meaningful project activity has been recorded for ${latestAge} days.`,
      action: "Continue conversation.",
      priority: 40,
      tab: "conversations",
    });
  }

  return recommendations
    .sort((left, right) => right.priority - left.priority || left.title.localeCompare(right.title))
    .filter((item, index, list) => list.findIndex((candidate) => candidate.title === item.title) === index)
    .slice(0, 5);
}

function projectInbox(project: ProjectRecord, data: AppData): ProjectInboxItem[] {
  const items: ProjectInboxItem[] = [];
  projectActivity(project, data).forEach((activity, index) => {
    items.push({
      id: text(activity.activity_id || `activity-${index}`, `activity-${index}`),
      title: projectActivitySentence(activity),
      detail: activityEventType(activity).replace(/_/g, " "),
      timestamp: activity.timestamp,
      tab: "conversations",
    });
  });
  projectDeliverables(project, data).forEach((deliverable) => {
    items.push({
      id: deliverable.deliverable_id,
      title: `${deliverable.title} ${["review", "proposed"].includes(text(deliverable.status, "")) ? "needs review" : "created"}`,
      detail: `${deliverable.deliverable_type} · ${deliverableStatusLabel(deliverable.status)}`,
      timestamp: deliverable.updated_at,
      tab: deliverable.source_type === "proposal" ? "decisions" : "deliverables",
      proposalId: deliverable.source_type === "proposal" ? deliverable.source_id : undefined,
    });
  });
  projectKnowledge(project, data).forEach((memory) => {
    items.push({
      id: memoryId(memory),
      title: `${text(memory.title, "Knowledge")} updated`,
      detail: "Project knowledge",
      timestamp: text(memory.updated_at || memory.created_at, ""),
      tab: "knowledge",
    });
  });
  projectHandoffs(project, data).forEach((handoff, index) => {
    items.push({
      id: text(handoff.handoff_id || handoff.assignment_id || `handoff-${index}`, `handoff-${index}`),
      title: `${text(handoff.from_worker, "Worker")} handed work to ${text(handoff.to_worker, "worker")}`,
      detail: text(handoff.reason || handoff.context_summary || handoff.summary, "Project handoff"),
      timestamp: text(handoff.timestamp || handoff.created_at, ""),
      tab: "decisions",
    });
  });
  return items.sort((left, right) => text(right.timestamp, "").localeCompare(text(left.timestamp, ""))).slice(0, 10);
}

function projectCurrentFocus(project: ProjectRecord, data: AppData): string {
  const review = projectAssignments(project, data).find((assignment) => text(assignment.status, "") === "review");
  if (review) return `${assignmentTitle(review)} review`;
  const active = projectAssignments(project, data).find((assignment) => ["in_progress", "assigned", "waiting"].includes(text(assignment.status, "")));
  if (active) return assignmentTitle(active);
  const deliverable = projectDeliverables(project, data).find((item) => ["review", "proposed", "open", "in_progress"].includes(text(item.status, "")));
  if (deliverable) return `${deliverable.title}`;
  return "Project conversation and next deliverable";
}

function projectLatestActivity(project: ProjectRecord, data: AppData): string {
  const activity = projectActivity(project, data)[0];
  if (activity) return projectActivitySentence(activity);
  const deliverable = projectDeliverables(project, data).sort((left, right) => text(right.updated_at, "").localeCompare(text(left.updated_at, "")))[0];
  if (deliverable) return `${text(deliverable.owner, "The workforce")} updated ${deliverable.title}${deliverable.updated_at ? ` ${shortDate(deliverable.updated_at)}` : ""}.`;
  return "No meaningful project activity has been recorded yet.";
}

function projectRecommendedAction(project: ProjectRecord, data: AppData): { label: string; detail: string; tab: ProjectTab; proposalId?: string } {
  const recommendation = projectRecommendations(project, data)[0];
  if (recommendation) return { label: recommendation.action, detail: recommendation.why, tab: recommendation.tab, proposalId: recommendation.proposalId };
  const decisions = projectDecisions(project, data);
  if (decisions.pending.length) {
    const proposal = decisions.pending[0];
    return {
      label: `Review ${decisionTitle(proposal)}`,
      detail: text(proposal.approval_reason || proposal.governance_reason || proposal.risk || proposal.risk_level, "A worker proposal is waiting for operator judgement."),
      tab: "decisions",
      proposalId: proposalId(proposal),
    };
  }
  const deliverable = projectDeliverables(project, data).find((item) => ["review", "completed", "proposed"].includes(text(item.status, "")));
  if (deliverable) return { label: `Open ${deliverable.title}`, detail: "A produced project output is ready to inspect.", tab: "deliverables" };
  if (project.room_id) return { label: "Continue project conversation", detail: "Ask for the next deliverable or give feedback without leaving this workspace.", tab: "conversations" };
  return { label: "Start conversation", detail: "Create or open a project room so the workforce has one place to work.", tab: "conversations" };
}

function projectActivitySentence(item: ActivityRecord): string {
  const actor = text(item.actor || item.runtime || item.source, "The workforce");
  const summary = text(item.summary, "");
  const type = activityEventType(item).toLowerCase();
  if (summary && !summary.includes("{")) return summary;
  if (type.includes("proposal") || text(item.proposal_id, "")) return `${actor} submitted a proposal`;
  if (type.includes("handoff")) return `${actor} created a handoff`;
  if (type.includes("approval") || type.includes("decision")) return `${actor} recorded a decision`;
  if (type.includes("message") || type.includes("reply")) return `${actor} replied in the project conversation`;
  if (type.includes("assignment")) return `${actor} updated project work`;
  if (type.includes("outcome")) return `${actor} updated a deliverable`;
  return `${actor} recorded project activity`;
}

function decisionTitle(proposal: Proposal): string {
  const title = text(proposal.title || proposal.summary, proposalId(proposal));
  const status = text(proposal.status, "proposed");
  if (status === "approved" || status === "executed") return `${title} approved`;
  if (status === "rejected") return `${title} rejected`;
  if (status === "cancelled") return `${title} cancelled`;
  return title;
}

function decisionActionLabel(proposal: Proposal): string {
  const status = text(proposal.status, "proposed");
  if (status === "approved" || status === "executed") return "Review decision";
  if (status === "rejected") return "Read rejection";
  return "Decide";
}

function deliverableStatusLabel(status?: string): string {
  const value = text(status, "open");
  if (value === "in_progress") return "In progress";
  if (value === "proposed") return "Ready for decision";
  if (value === "review") return "Ready for review";
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function deliverableActionLabel(deliverable: DeliverableRecord): string {
  const status = text(deliverable.status, "");
  if (["review", "proposed"].includes(status)) return "Review";
  if (["approved", "executed", "completed"].includes(status)) return "Open";
  return deliverable.source_type === "proposal" ? "Review decision" : "Open";
}

function workerRecommendedUse(workerIdValue: string, project: ProjectRecord, data: AppData): string {
  const focus = workerFocus(workerIdValue, project, data).toLowerCase();
  if (focus.includes("review")) return "Use for review and judgement";
  if (focus.includes("architecture")) return "Use for architecture critique";
  if (focus.includes("research")) return "Use for research synthesis";
  if (focus.includes("copy") || focus.includes("article")) return "Use for drafting and editing";
  return "Use for the next project conversation";
}

function projectWorkerLastActivity(workerIdValue: string, project: ProjectRecord, data: AppData): string {
  const activity = projectActivity(project, data).find((item) => activityRuntime(item) === workerIdValue || text(item.actor, "") === workerIdValue);
  if (activity?.timestamp) return shortDate(activity.timestamp);
  return "No recent project activity";
}

function missionForWorker(runtimeId: string, missions: Mission[]): Mission | undefined {
  return missions.find((mission) => (mission.workers || []).some((worker) => text(worker.adapter_id || worker.id, "") === runtimeId));
}

function missionForRoom(roomName: string, missions: Mission[]): Mission | undefined {
  return missions.find((mission) => (mission.rooms || []).some((room) => text(room.room_name || room.name, "") === roomName));
}

function affectedMissionForIncident(raw: Record<string, unknown>, missions: Mission[]): Mission | undefined {
  const incidentId = text(raw.dead_letter_id || raw.delivery_id || raw.incident_id || raw.message_id, "");
  return missions.find((mission) => (mission.incidents || []).some((incident) => text(incident.incident_id || incident.id, "") === incidentId));
}

function outcomeForWorker(runtimeId: string, outcomes: Outcome[]): Outcome | undefined {
  return outcomes.find((outcome) => (outcome.workers || []).some((worker) => text(worker.adapter_id || worker.id, "") === runtimeId));
}

function affectedOutcomeForIncident(raw: Record<string, unknown>, outcomes: Outcome[]): Outcome | undefined {
  const incidentId = text(raw.dead_letter_id || raw.delivery_id || raw.incident_id || raw.message_id, "");
  return outcomes.find((outcome) => (outcome.incidents || []).some((incident) => text(incident.incident_id || incident.id, "") === incidentId));
}

function missionAssignments(mission: Mission, assignments: Assignment[]): Assignment[] {
  const id = missionId(mission);
  return assignments.filter((assignment) => text(assignment.mission_id || assignment.mission?.mission_id, "") === id);
}

function outcomeAssignments(outcome: Outcome, assignments: Assignment[]): Assignment[] {
  const id = outcomeId(outcome);
  return assignments.filter((assignment) => text(assignment.outcome_id || assignment.outcome?.outcome_id, "") === id);
}

function missionHealth(mission: Mission, assignments: Assignment[], activity: ActivityRecord[] = []): MissionHealth {
  const status = text(mission.status, "");
  const linkedAssignments = missionAssignments(mission, assignments);
  const blockedAssignments = linkedAssignments.filter((assignment) => assignmentHealth(assignment) === "Blocked");
  const incidentCount = (mission.incidents || []).length;
  const inactiveDays = assignmentAgeDays({ updated_at: mission.updated_at, created_at: mission.created_at } as Assignment);
  const hasRecentActivity = activity.some((item) => text(item.mission_id || item.mission, "") === missionId(mission));
  if (status === "blocked" || blockedAssignments.length || incidentCount > 0 || inactiveDays >= 7) return "At Risk";
  if (status === "review" || linkedAssignments.some((assignment) => assignmentHealth(assignment) === "Waiting") || (!hasRecentActivity && inactiveDays >= 3)) return "Watching";
  return "Healthy";
}

function outcomeHealth(outcome: Outcome, assignments: Assignment[]): OutcomeHealth {
  const status = text(outcome.status, "");
  const linkedAssignments = outcomeAssignments(outcome, assignments);
  if (status === "blocked" || linkedAssignments.some((assignment) => assignmentHealth(assignment) === "Blocked") || (outcome.incidents || []).length) return "Blocked";
  if (status === "review" || status === "not_started" || text(outcome.confidence, "") === "low" || linkedAssignments.some((assignment) => assignmentHealth(assignment) === "Waiting")) return "Watching";
  return "On Track";
}

function meaningfulActivity(data: AppData): ActivityRecord[] {
  const priorityTerms = ["proposal", "approval", "blocked", "incident", "handoff", "outcome", "mission", "assignment", "failed", "timeout"];
  const activity = data.recentActivity.length ? data.recentActivity : data.workforcePresence?.recent_activity || [];
  return [...activity].sort((left, right) => {
    const leftText = `${activityEventType(left)} ${text(left.summary, "")}`.toLowerCase();
    const rightText = `${activityEventType(right)} ${text(right.summary, "")}`.toLowerCase();
    const leftRank = priorityTerms.some((term) => leftText.includes(term)) ? 1 : 0;
    const rightRank = priorityTerms.some((term) => rightText.includes(term)) ? 1 : 0;
    if (leftRank !== rightRank) return rightRank - leftRank;
    return text(right.timestamp, "").localeCompare(text(left.timestamp, ""));
  });
}

function recommendedNextActions(data: AppData, workers: Agent[]): BriefingAction[] {
  const actions: BriefingAction[] = [];
  const activeMissionIds = new Set(data.missions.filter((mission) => text(mission.status, "") === "active").map(missionId));
  const criticalWorkers = workers.filter((worker) => displaySeverityForRuntime(worker, { requiredForCurrentWorkflow: true }) === "Critical");

  data.pending.slice(0, 3).forEach((proposal) => {
    actions.push({
      priority: 10,
      label: `Review proposal ${text(proposal.title || proposal.summary, proposalId(proposal))}`,
      detail: text(proposal.approval_reason || proposal.governance_reason || proposal.risk || proposal.risk_level, "Approval is waiting for operator review."),
      targetView: "proposals",
      refId: proposalId(proposal),
    });
  });

  data.assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked").slice(0, 3).forEach((assignment) => {
    actions.push({
      priority: 9,
      label: `Unblock assignment ${assignmentTitle(assignment)}`,
      detail: `${assignment.owner_worker || "No owner"} owns blocked work${assignment.room_id ? ` in #${assignment.room_id}` : ""}.`,
      targetView: "assignments",
      refId: assignmentId(assignment),
    });
  });

  data.missions.filter((mission) => text(mission.status, "") === "active" && !text(mission.owner, "") && !missionAssignments(mission, data.assignments).some((assignment) => text(assignment.owner_worker, ""))).slice(0, 3).forEach((mission) => {
    actions.push({
      priority: 8,
      label: `Mission ${missionTitle(mission)} has no active owner`,
      detail: "Assign accountable ownership before adding more work.",
      targetView: "missions",
      refId: missionId(mission),
    });
  });

  data.assignments.filter((assignment) => assignmentHealth(assignment) === "Waiting" && assignmentAgeDays(assignment) >= 3).slice(0, 3).forEach((assignment) => {
    actions.push({
      priority: 7,
      label: `Assignment ${assignmentTitle(assignment)} has been waiting ${assignmentAgeDays(assignment)} days`,
      detail: "Review the wait reason or move ownership forward.",
      targetView: "assignments",
      refId: assignmentId(assignment),
    });
  });

  data.outcomes.filter((outcome) => outcomeHealth(outcome, data.assignments) === "Blocked").slice(0, 3).forEach((outcome) => {
    actions.push({
      priority: 6,
      label: `Outcome ${outcomeTitle(outcome)} remains blocked`,
      detail: text(outcome.description, "Inspect linked assignments, incidents, and proposals."),
      targetView: "outcomes",
      refId: outcomeId(outcome),
    });
  });

  data.missions.filter((mission) => missionHealth(mission, data.assignments, data.recentActivity) === "At Risk").slice(0, 3).forEach((mission) => {
    actions.push({
      priority: 5,
      label: `Mission ${missionTitle(mission)} is at risk`,
      detail: `${missionAssignments(mission, data.assignments).filter((assignment) => assignmentHealth(assignment) === "Blocked").length} blocked assignments · ${(mission.incidents || []).length} incidents.`,
      targetView: "missions",
      refId: missionId(mission),
    });
  });

  if (criticalWorkers.length) {
    actions.push({
      priority: 4,
      label: `Review critical runtime ${workerId(criticalWorkers[0])}`,
      detail: explainRuntimeIssue(criticalWorkers[0]),
      targetView: "workforce",
      refId: workerId(criticalWorkers[0]),
    });
  }

  data.deadLetters.slice(0, 1).forEach((item) => {
    const record = asRecord(item);
    actions.push({
      priority: activeMissionIds.size ? 4 : 2,
      label: `Inspect incident ${text(record.dead_letter_id || record.delivery_id || record.message_id, "latest")}`,
      detail: text(record.reason || record.error || record.status, "Dead letter requires trace review."),
      targetView: "incidents",
      refId: text(record.message_id || record.conversation_id || record.dead_letter_id, ""),
    });
  });

  return actions
    .sort((left, right) => right.priority - left.priority || left.label.localeCompare(right.label))
    .filter((action, index, list) => list.findIndex((item) => item.label === action.label) === index)
    .slice(0, 5);
}

function projectForAction(action: BriefingAction, projects: ProjectRecord[], data: AppData): ProjectTarget {
  if (!["proposals", "assignments", "missions", "outcomes", "work", "governance"].includes(action.targetView)) return {};
  const refId = text(action.refId, "");
  const project = projects.find((item) => {
    if (action.targetView === "proposals" || action.targetView === "governance") {
      const proposal = data.proposals.find((candidate) => proposalId(candidate) === refId);
      return Boolean(proposal)
        && ((item.room_id && text(proposal?.room_id || proposal?.room, "") === item.room_id)
          || (item.mission_id && text(proposal?.mission_id || proposal?.goal_id, "") === item.mission_id));
    }
    if (action.targetView === "assignments" || action.targetView === "work") {
      return item.assignment_ids.includes(refId) || projectAssignments(item, data).some((assignment) => assignmentId(assignment) === refId);
    }
    if (action.targetView === "outcomes") {
      return item.outcome_ids.includes(refId) || projectOutcomes(item, data).some((outcome) => outcomeId(outcome) === refId);
    }
    if (action.targetView === "missions") return item.mission_id === refId;
    return false;
  }) || projects.find((item) => text(item.status, "") === "active") || projects[0];
  const tab: ProjectTab = action.targetView === "proposals" || action.targetView === "governance"
    ? "decisions"
    : action.targetView === "outcomes" || action.targetView === "assignments" || action.targetView === "work"
      ? "deliverables"
      : "overview";
  return { projectId: project ? projectId(project) : undefined, tab, roomId: project?.room_id };
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

function presenceId(worker: WorkforcePresenceWorker): string {
  return text(worker.runtime_id, "runtime");
}

function presenceForWorker(worker: Agent, presence?: WorkforcePresenceResponse): WorkforcePresenceWorker | undefined {
  const id = workerId(worker);
  return (presence?.workers || []).find((item) => presenceId(item) === id);
}

function presenceForRuntime(runtimeId: string, presence?: WorkforcePresenceResponse): WorkforcePresenceWorker | undefined {
  return (presence?.workers || []).find((item) => presenceId(item) === runtimeId);
}

function presenceLabel(state?: string): string {
  if (state === "needs_attention") return "Needs attention";
  if (state === "active") return "Active";
  if (state === "idle") return "Idle";
  if (state === "watching") return "Watching";
  if (state === "unavailable") return "Unavailable";
  return "Unknown";
}

function presenceClass(state?: string): string {
  if (state === "active") return "presence-active";
  if (state === "idle") return "presence-idle";
  if (state === "watching") return "presence-watching";
  if (state === "needs_attention") return "presence-attention";
  if (state === "unavailable") return "presence-unavailable";
  return "presence-unknown";
}

function canvasPresenceIndicatorClass(state?: string): string {
  if (state === "active") return "canvas-live-active";
  if (state === "needs_attention") return "canvas-live-attention";
  if (state === "idle" || state === "watching") return "canvas-live-idle";
  return "canvas-live-unknown";
}

function activityEventType(item: ActivityRecord): string {
  return text(item.event_type || item.activity_type, "activity");
}

function activityRuntime(item: ActivityRecord): string {
  return text(item.runtime || item.actor, "");
}

function activityRoom(item: ActivityRecord): string {
  return text(item.room || item.room_id, "");
}

function secondsAgo(value?: number | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unknown";
  if (value < 60) return `${Math.floor(value)} seconds ago`;
  if (value < 3600) return `${Math.floor(value / 60)} minutes ago`;
  if (value < 86400) return `${Math.floor(value / 3600)} hours ago`;
  return `${Math.floor(value / 86400)} days ago`;
}

function formatIdle(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "Unknown";
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function currentActivityLabel(presence: WorkforcePresenceWorker): string {
  if (presence.current_activity) return presence.current_activity;
  if (presence.needs_attention) return "Needs attention";
  if (presence.presence_state === "active") {
    const type = text(presence.latest_activity_type, "");
    if (type.includes("proposal")) return "Reviewing proposal";
    if (type.includes("delivery") || type.includes("reply")) return "Reply generated";
    if (presence.current_room) return "Working in room";
    return "Active";
  }
  if (presence.presence_state === "watching") return "Watching room";
  if (presence.presence_state === "idle") return "Idle";
  if (presence.presence_state === "unavailable") return "Unavailable";
  return "Awaiting activity";
}

function lastMeaningfulAction(presence: WorkforcePresenceWorker): string {
  return text(presence.last_meaningful_action || presence.latest_activity_summary, "No recent activity recorded.");
}

function humanHealthFromPresence(worker?: WorkforcePresenceWorker, fallback?: Agent): DisplaySeverity {
  if (worker?.presence_state === "unavailable") return "Needs attention";
  const rawHealth = text(worker?.health_status || (fallback ? workerHealth(fallback) : ""), "healthy").toLowerCase();
  if (rawHealth === "healthy") return "Operational";
  if (rawHealth === "degraded" || rawHealth === "failing") return "Needs attention";
  if (rawHealth === "unstable") return "Degraded";
  return "Needs attention";
}

function operatorWorkerStatus(worker?: Agent, presence?: WorkforcePresenceWorker): OperatorWorkerStatus {
  if (presence?.presence_state === "unavailable") return "Unavailable";
  const rawHealth = text(presence?.health_status || (worker ? workerHealth(worker) : ""), "healthy").toLowerCase();
  const issueCount = worker ? workerIncidentCount(worker) : Number(presence?.needs_attention ? 1 : 0);
  const currentActivity = text(presence?.current_activity || presence?.latest_activity_summary, "").toLowerCase();
  if (rawHealth === "healthy" && !presence?.needs_attention && issueCount === 0) return "Available";
  if (rawHealth === "failing" || currentActivity.includes("empty reply") || issueCount >= 3) return "Avoid for now";
  if (rawHealth === "degraded" || rawHealth === "unstable" || presence?.needs_attention || issueCount > 0) return "Monitor";
  return "Available";
}

function operatorWorkerTone(status: OperatorWorkerStatus): "neutral" | "good" | "warn" | "danger" {
  if (status === "Available") return "good";
  if (status === "Unavailable") return "neutral";
  return "warn";
}

function operatorWorkerImpact(status: OperatorWorkerStatus, worker?: Agent, presence?: WorkforcePresenceWorker): string {
  if (status === "Available") return "Safe for normal work.";
  if (status === "Unavailable") return "Cannot be relied on until the runtime is available.";
  const issue = text(presence?.attention_reason, worker ? explainRuntimeIssue(worker) : "Reliability needs observation.");
  if (status === "Avoid for now") return issue.includes("Empty") ? "Not reliable for active work." : "May block or miss replies in active work.";
  return issue.includes("Timeout") || issue.includes("delivery") ? "May miss replies." : "Usable, but watch replies before relying on them.";
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
  if (normalized.includes("critical") || normalized.includes("blocked") || normalized.includes("offline")) {
    return "status-danger";
  }
  if (normalized.includes("fail") || normalized.includes("timeout") || normalized.includes("unstable") || normalized.includes("degrad") || normalized.includes("attention") || normalized.includes("watching") || normalized.includes("risk") || normalized.includes("waiting")) {
    return "status-warn";
  }
  return "status-good";
}

function roomTargetFromComposer(value: string, room: string): { target: string; body: string; mode: "note" | "room" | "worker" | "global" } {
  const body = value.trim();
  if (body.startsWith("@everyone --global ")) {
    return { target: "broadcast", body: body.slice("@everyone --global ".length).trim(), mode: "global" };
  }
  if (body === "@everyone") {
    return { target: `room:${room}`, body: "Who is available?", mode: "room" };
  }
  if (body.startsWith("@everyone ")) {
    return { target: `room:${room}`, body: body.slice("@everyone ".length).trim(), mode: "room" };
  }
  const workerMatch = body.match(/^@([a-zA-Z0-9_.-]+)\s+([\s\S]+)$/);
  if (workerMatch) {
    return { target: workerMatch[1], body: workerMatch[2].trim(), mode: "worker" };
  }
  return { target: `room:${room}`, body, mode: "note" };
}

function deliveryStatusLabel(delivery?: DeliveryRecord | null): string {
  const status = text(delivery?.status, "").toLowerCase();
  const quality = text(delivery?.quality, "").toLowerCase();
  if (quality === "suspicious_output" || quality === "wrong_identity" || quality === "unexpected_output") return "suspicious output";
  if (status === "empty_reply") return "empty reply";
  if (status === "timeout") return "timeout";
  if (status === "failed") return "failed";
  if (status === "blocked") return "blocked";
  if (delivery?.ok === false) return "failed";
  if (status === "replied" || delivery?.ok === true) return "replied";
  return status || "queued";
}

function deliveryStatusCopy(delivery?: DeliveryRecord | null): string {
  const label = deliveryStatusLabel(delivery);
  if (label === "empty reply") return "[empty reply] - worker responded without text.";
  if (label === "timeout") return "Timeout - worker did not complete before the runtime limit.";
  if (label === "failed") return "Failed - adapter or runtime could not complete the request.";
  if (label === "blocked") return "Blocked - delivery could not proceed.";
  if (label === "suspicious output") return "Suspicious output - inspect the reply before relying on it.";
  if (label === "replied") return "Replied.";
  return label;
}

function deliveryPreview(delivery?: DeliveryRecord | null): string {
  const preview = text(delivery?.body_preview || delivery?.body, "");
  if (preview.trim()) return preview;
  if (deliveryStatusLabel(delivery) === "empty reply") return "[empty reply] - worker responded without text.";
  return text(delivery?.error, "No reply preview returned.");
}

function deliveryTone(delivery?: DeliveryRecord | null): string {
  const label = deliveryStatusLabel(delivery);
  if (label === "replied") return "status-good";
  if (label === "empty reply" || label === "suspicious output") return "status-warn";
  return "status-danger";
}

function deliverySummary(deliveries: DeliveryRecord[] = []): string {
  if (!deliveries.length) return "No delivery rows. Room note recorded locally.";
  const counts = deliveries.reduce<Record<string, number>>((acc, delivery) => {
    const label = deliveryStatusLabel(delivery);
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
  const targets = deliveries.length;
  const replied = counts.replied || 0;
  const empty = counts["empty reply"] || 0;
  const failed = (counts.failed || 0) + (counts.timeout || 0) + (counts.blocked || 0);
  const extras = Object.entries(counts)
    .filter(([label]) => !["replied", "empty reply", "failed", "timeout", "blocked"].includes(label))
    .map(([label, count]) => `${count} ${label}`);
  return [`${targets} targets`, `${replied} replied`, `${empty} empty reply`, `${failed} failed`, ...extras].join(" · ");
}

function displaySeverityForRuntime(worker: Agent, context: { activeWorkBlocked?: boolean; requiredForCurrentWorkflow?: boolean } = {}): DisplaySeverity {
  const rawHealth = workerHealth(worker);
  if (context.activeWorkBlocked) return "Blocked";
  if (context.requiredForCurrentWorkflow && rawHealth === "failing") return "Critical";
  if (rawHealth === "healthy") return "Operational";
  if (rawHealth === "degraded") return "Needs attention";
  if (rawHealth === "unstable") return "Degraded";
  if (rawHealth === "failing") return "Needs attention";
  return "Needs attention";
}

function displaySeverityTone(severity: DisplaySeverity): "neutral" | "good" | "warn" | "danger" {
  if (severity === "Operational") return "good";
  if (severity === "Blocked" || severity === "Critical") return "danger";
  return "warn";
}

function explainRuntimeIssue(worker: Agent): string {
  const reputation = workerReputation(worker);
  const rawHealth = workerHealth(worker);
  if (rawHealth === "healthy") return "No current reliability issue detected.";
  if (Number(reputation.recent_empty_replies ?? reputation.empty_replies ?? 0) > 0) return "Empty replies detected.";
  if (Number(reputation.recent_wrong_identity ?? reputation.wrong_identity ?? 0) > 0) return "Identity mismatch in recent replies.";
  if (Number(reputation.recent_timeouts ?? reputation.timeouts ?? 0) > 0) return "Timeout history.";
  if (Number(reputation.recent_failures ?? reputation.failures ?? 0) > 0) return "Recent delivery failures.";
  if (rawHealth === "failing") return "No recent successful reply.";
  if (rawHealth === "unstable") return "Reliability is inconsistent.";
  return "Runtime needs observation.";
}

function runtimeRoomDependency(worker: Agent, rooms: Room[] = [], proposals: Proposal[] = []): string {
  const id = workerId(worker);
  const proposal = proposals.find((item) => text(item.proposed_by || item.proposer, "") === id && text(item.room_id || item.room, ""));
  const proposalRoom = text(proposal?.room_id || proposal?.room, "");
  if (proposalRoom) return `Used in #${proposalRoom}`;
  const room = rooms.find((item) => {
    const members = Array.isArray(item.members) ? item.members.map(asRecord) : [];
    return members.some((member) => text(member.adapter_id || member.id, "") === id);
  });
  if (room?.name) return `Used in #${room.name}`;
  return "No active room dependency detected";
}

function suggestedRuntimeAction(worker: Agent, dependency = "No active room dependency detected"): string {
  const rawHealth = workerHealth(worker);
  const issue = explainRuntimeIssue(worker);
  if (rawHealth === "healthy") return "No action needed.";
  if (dependency.startsWith("Used in #")) return "Inspect latest trace or remove from active room.";
  if (issue.includes("Empty replies")) return "Ignore if unused, or remove from rooms if noisy.";
  if (issue.includes("Identity mismatch")) return "Inspect latest trace before assigning work.";
  if (issue.includes("Timeout")) return "Restart adapter if you need it now.";
  return "Monitor, restart adapter, or disable it if it blocks current work.";
}

function displayImpactForIncident(item: { type: string; raw: unknown; worker?: Agent }): "Low" | "Medium" | "High" {
  const raw = asRecord(item.raw);
  if (text(raw.active_room || raw.goal_id || raw.proposal_id || raw.blocking, "")) return "High";
  if (item.worker && displaySeverityForRuntime(item.worker) === "Degraded") return "Medium";
  if (item.type === "dead_letter" && text(raw.room || raw.room_id || raw.target, "").startsWith("room:")) return "Medium";
  return "Low";
}

function summariseWorkforceState(workers: Agent[], pending: Proposal[], deadLetters: unknown[], daemonStatus: DaemonStatus): {
  status: string;
  needsAttention: Agent[];
  healthy: Agent[];
  unreliable: Agent[];
  highestPriority: string;
  suggestedAction: string;
} {
  if (daemonStatus === "offline") {
    return {
      status: "Daemon unavailable",
      needsAttention: workers,
      healthy: [],
      unreliable: workers,
      highestPriority: "The daemon health check is failing.",
      suggestedAction: "Restart the daemon or check the local service.",
    };
  }
  const healthy = workers.filter((worker) => displaySeverityForRuntime(worker) === "Operational");
  const needsAttention = workers.filter((worker) => displaySeverityForRuntime(worker) !== "Operational");
  const unreliable = workers.filter((worker) => ["unstable", "failing"].includes(workerHealth(worker)));
  const priorityWorker = needsAttention[0];
  return {
    status: needsAttention.length || deadLetters.length ? "Usable with issues" : "Operational",
    needsAttention,
    healthy,
    unreliable,
    highestPriority: priorityWorker ? `${workerId(priorityWorker)}: ${explainRuntimeIssue(priorityWorker)}` : deadLetters.length ? "Historical dead letters are available for review." : "No current operator action required.",
    suggestedAction: priorityWorker ? suggestedRuntimeAction(priorityWorker) : pending.length ? "Review pending proposals." : "Continue monitoring workforce health.",
  };
}

function isRoomNotFoundError(error: unknown): boolean {
  if (error instanceof ApiError && error.status === 404) return true;
  return error instanceof Error && error.message.toLowerCase().includes("room not found");
}

function roomMissingWarning(name: string): string {
  return `Room not found: ${name}`;
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
  if (type === "briefing") return "Operational Briefing";
  if (type === "runtime") return refId ? `Runtime · ${refId}` : "Runtime";
  if (type === "room") return refId ? `Room · #${refId}` : "Room";
  if (type === "mission") return refId ? `Mission · ${refId}` : "Mission";
  if (type === "outcome") return refId ? `Outcome · ${refId}` : "Outcome";
  if (type === "assignment") return refId ? `Assignment · ${refId}` : "Assignment";
  if (type === "memory") return refId ? `Memory · ${refId}` : "Memory";
  if (type === "proposal-queue") return "Proposal Queue";
  if (type === "proposal-detail") return refId ? `Proposal · ${refId}` : "Proposal Detail";
  if (type === "incident") return "Incident";
  if (type === "trace") return refId ? `Trace · ${refId}` : "Trace";
  if (type === "activity-feed") return "Activity Feed";
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
    height: type === "briefing" || type === "trace" || type === "activity-feed" || type === "mission" || type === "outcome" || type === "assignment" || type === "memory" ? 360 : 300,
    refId,
  };
}

function createPresetNodes(workspace: WorkspacePreset, workers: Agent[], rooms: Room[], proposals: Proposal[], deadLetters: unknown[], missions: Mission[] = [], outcomes: Outcome[] = [], assignments: Assignment[] = []): CanvasNode[] {
  const primaryRoom = text(rooms[0]?.name, workspace === "Research" ? "research" : workspace === "Coding" ? "coding" : "ops");
  const primaryMission = missionId(missions.find((mission) => text(mission.status, "") === "active") || missions[0] || {});
  const primaryOutcome = outcomeId(outcomes.find((outcome) => text(outcome.status, "") === "in_progress") || outcomes.find((outcome) => text(outcome.status, "") === "review") || outcomes[0] || {});
  const primaryAssignment = assignmentId(assignments.find((assignment) => text(assignment.status, "") === "in_progress") || assignments.find((assignment) => text(assignment.status, "") === "blocked") || assignments[0] || {});
  const failingWorkers = workers.filter((worker) => ["failing", "unstable", "degraded"].includes(workerHealth(worker)));
  const runtimeWorkers = workspace === "Incident Response" ? failingWorkers : workers;
  const selectedProposal = proposals.find((proposal) => text(proposal.status, "").toLowerCase() === "pending") || proposals[0];
  const traceId = text(selectedProposal ? proposalId(selectedProposal) : asRecord(deadLetters[0]).message_id || asRecord(deadLetters[0]).conversation_id, "");

  if (workspace === "Coding") {
    return [
      createNode("briefing", 40, 40),
      createNode("workforce-summary", 430, 40),
      createNode("room", 820, 40, primaryRoom),
      createNode("proposal-queue", 40, 420),
      createNode("activity-feed", 430, 420),
      createNode("trace", 820, 420, traceId || undefined),
    ];
  }
  if (workspace === "Research") {
    return [
      createNode("mission", 40, 40, primaryMission || undefined),
      createNode("outcome", 40, 400, primaryOutcome || undefined),
      createNode("assignment", 430, 400, primaryAssignment || undefined),
      createNode("room", 430, 40, primaryRoom),
      createNode("trace", 820, 40, traceId || undefined),
      createNode("proposal-queue", 820, 430),
      createNode("workforce-summary", 1210, 430),
    ];
  }
  if (workspace === "Incident Response") {
    return [
      createNode("mission", 40, 40, primaryMission || undefined),
      createNode("assignment", 1210, 430, primaryAssignment || undefined),
      createNode("incident", 430, 40),
      createNode("dead-letter", 820, 40),
      createNode("trace", 1210, 40, traceId || undefined),
      createNode("outcome", 820, 430, primaryOutcome || undefined),
      ...runtimeWorkers.slice(0, 4).map((worker, index) => createNode("runtime", 40 + index * 320, 800, workerId(worker))),
      createNode("proposal-queue", 40, 760),
      createNode("activity-feed", 430, 760),
    ];
  }
  return [
    createNode("briefing", 40, 40),
    createNode("workforce-summary", 430, 40),
    createNode("mission", 40, 420, primaryMission || undefined),
    createNode("outcome", 40, 760, primaryOutcome || undefined),
    createNode("assignment", 430, 710, primaryAssignment || undefined),
    ...runtimeWorkers.slice(0, 6).map((worker, index) => createNode("runtime", 820 + (index % 3) * 320, 40 + Math.floor(index / 3) * 330, workerId(worker))),
    createNode("incident", 820, 710),
    createNode("activity-feed", 820, 1070),
    createNode("dead-letter", 1210, 710),
  ];
}

function nodeTone(type: CanvasNodeType, node: CanvasNode, workers: Agent[], pending: Proposal[], deadLetters: unknown[], missions: Mission[], outcomes: Outcome[], assignments: Assignment[], presence?: WorkforcePresenceResponse): "normal" | "selected" | "degraded" | "failing" | "pending" | "empty" | "loading" | "error" {
  if (type === "briefing") {
    if (pending.length || deadLetters.length || assignments.some((assignment) => assignmentHealth(assignment) === "Blocked")) return "pending";
    return "normal";
  }
  if (type === "runtime") {
    const worker = workers.find((item) => workerId(item) === node.refId);
    if (!worker) return "empty";
    const workerPresence = presenceForWorker(worker, presence);
    if (workerPresence?.presence_state === "needs_attention" || workerPresence?.presence_state === "unavailable") return "degraded";
    const health = workerHealth(worker);
    if (["failing", "unstable", "degraded"].includes(health)) return "degraded";
  }
  if (type === "proposal-queue" || type === "proposal-detail") return pending.length ? "pending" : "empty";
  if (type === "mission") {
    const mission = missions.find((item) => missionId(item) === node.refId) || missions[0];
    if (mission?.status === "blocked") return "degraded";
    if (mission?.status === "review" || mission?.status === "proposed") return "pending";
  }
  if (type === "outcome") {
    const outcome = outcomes.find((item) => outcomeId(item) === node.refId) || outcomes[0];
    if (outcome?.status === "blocked") return "degraded";
    if (outcome?.status === "not_started" || outcome?.status === "in_progress" || outcome?.status === "review") return "pending";
  }
  if (type === "assignment") {
    const assignment = assignments.find((item) => assignmentId(item) === node.refId) || assignments[0];
    if (assignment?.status === "blocked") return "degraded";
    if (assignment?.status === "waiting" || assignment?.status === "review" || assignment?.status === "handoff") return "pending";
    if (!assignment) return "empty";
  }
  if (type === "dead-letter") return deadLetters.length ? "degraded" : "empty";
  if (type === "incident") return deadLetters.length || workers.some((worker) => ["failing", "unstable"].includes(workerHealth(worker))) ? "degraded" : "normal";
  return "normal";
}

function inferCanvasTarget(query: string, workers: Agent[], rooms: Room[], missions: Mission[], outcomes: Outcome[], assignments: Assignment[], proposals: Proposal[], deadLetters: unknown[]): { type: CanvasNodeType; refId?: string } {
  const value = query.trim();
  const normalized = value.toLowerCase();
  if (!value) return { type: "workforce-summary" };
  const runtime = workers.find((worker) => workerId(worker).toLowerCase() === normalized);
  if (runtime) return { type: "runtime", refId: workerId(runtime) };
  const roomName = normalized.startsWith("#") ? normalized.slice(1) : normalized;
  const room = rooms.find((item) => text(item.name, "").toLowerCase() === roomName);
  if (room) return { type: "room", refId: text(room.name, roomName) };
  const mission = missions.find((item) => missionId(item).toLowerCase() === normalized || text(item.title, "").toLowerCase().includes(normalized));
  if (mission) return { type: "mission", refId: missionId(mission) };
  const outcome = outcomes.find((item) => outcomeId(item).toLowerCase() === normalized || text(item.title, "").toLowerCase().includes(normalized));
  if (outcome) return { type: "outcome", refId: outcomeId(outcome) };
  const assignment = assignments.find((item) => assignmentId(item).toLowerCase() === normalized || text(item.title, "").toLowerCase().includes(normalized));
  if (assignment) return { type: "assignment", refId: assignmentId(assignment) };
  const proposal = proposals.find((item) => proposalId(item).toLowerCase() === normalized || text(item.title, "").toLowerCase().includes(normalized));
  if (proposal) return { type: "proposal-detail", refId: proposalId(proposal) };
  const deadLetter = deadLetters.find((item) => {
    const record = asRecord(item);
    return [record.dead_letter_id, record.delivery_id, record.message_id, record.conversation_id].some((candidate) => text(candidate, "").toLowerCase() === normalized);
  });
  if (deadLetter) return { type: "dead-letter" };
  if (normalized.includes("incident")) return { type: "incident" };
  if (normalized.includes("briefing")) return { type: "briefing" };
  if (normalized.includes("mission")) return { type: "mission" };
  if (normalized.includes("outcome")) return { type: "outcome" };
  if (normalized.includes("assignment")) return { type: "assignment" };
  if (normalized.includes("memory")) return { type: "memory" };
  if (normalized.includes("dead")) return { type: "dead-letter" };
  if (normalized.includes("proposal")) return { type: "proposal-queue" };
  if (normalized.includes("activity") || normalized.includes("feed")) return { type: "activity-feed" };
  return { type: "trace", refId: value };
}

export default function App() {
  const [view, setView] = useState<View>("home");
  const [data, setData] = useState<AppData>(initialData);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [daemonStatus, setDaemonStatus] = useState<DaemonStatus>("unknown");
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [nodeErrors, setNodeErrors] = useState<NodeErrors>({});
  const [selectedRuntime, setSelectedRuntime] = useState<string | null>(null);
  const [selectedRoom, setSelectedRoom] = useState("ops");
  const [storedProjects, setStoredProjects] = useState<ProjectRecord[]>(() => readStoredProjects());
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectTab, setProjectTab] = useState<ProjectTab>("conversations");
  const [projectTitleInput, setProjectTitleInput] = useState("");
  const [projectPurposeInput, setProjectPurposeInput] = useState("");
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [selectedOutcomeId, setSelectedOutcomeId] = useState<string | null>(null);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [assignmentTitleInput, setAssignmentTitleInput] = useState("");
  const [assignmentDescriptionInput, setAssignmentDescriptionInput] = useState("");
  const [assignmentOwnerInput, setAssignmentOwnerInput] = useState("");
  const [assignmentContributorsInput, setAssignmentContributorsInput] = useState("");
  const [assignmentMissionInput, setAssignmentMissionInput] = useState("");
  const [assignmentOutcomeInput, setAssignmentOutcomeInput] = useState("");
  const [assignmentRoomInput, setAssignmentRoomInput] = useState("");
  const [handoffToInput, setHandoffToInput] = useState("");
  const [handoffReasonInput, setHandoffReasonInput] = useState("");
  const [roomDetail, setRoomDetail] = useState<RoomDetail>({ messages: [] });
  const [roomMessage, setRoomMessage] = useState("");
  const [roomMember, setRoomMember] = useState("");
  const [roomOperationName, setRoomOperationName] = useState("");
  const [roomOperationPreset, setRoomOperationPreset] = useState("ops");
  const [roomOperationMode, setRoomOperationMode] = useState<RoomOperationMode>("create");
  const [roomSearchQuery, setRoomSearchQuery] = useState("");
  const [roomNotice, setRoomNotice] = useState<string | null>(null);
  const [roomSending, setRoomSending] = useState(false);
  const [lastRoomDispatch, setLastRoomDispatch] = useState<DispatchResponse | null>(null);
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
  const [workTab, setWorkTab] = useState<"missions" | "outcomes" | "assignments">("missions");
  const [memoryNoteTitle, setMemoryNoteTitle] = useState("");
  const [memoryNoteBody, setMemoryNoteBody] = useState("");
  const [memoryScopeType, setMemoryScopeType] = useState("global");
  const [memoryScopeId, setMemoryScopeId] = useState("");
  const [memoryImportance, setMemoryImportance] = useState("high");
  const [projectKnowledgeDraft, setProjectKnowledgeDraft] = useState<ProjectKnowledgeDraft>({ title: "", body: "", importance: "high" });

  const daemonOnline = daemonStatus === "online";

  const workers = useMemo(() => {
    const workforceWorkers = (data.workforce?.workforce || data.workforce?.workers || data.workforce?.agents || []) as Agent[];
    return workforceWorkers.length ? workforceWorkers : data.agents;
  }, [data.agents, data.workforce]);

  const projects = useMemo(() => deriveProjects(data, storedProjects), [data, storedProjects]);

  useEffect(() => {
    if (!selectedProjectId && projects.length) setSelectedProjectId(projectId(projects[0]));
  }, [projects, selectedProjectId]);

  useEffect(() => {
    const project = projects.find((item) => projectId(item) === selectedProjectId);
    if (project?.room_id && selectedRoom !== project.room_id && view === "projects") setSelectedRoom(project.room_id);
  }, [projects, selectedProjectId, selectedRoom, view]);

  const createProject = useCallback(async () => {
    const title = projectTitleInput.trim();
    if (!title) {
      setViewError("Project title is required");
      return;
    }
    const now = new Date().toISOString();
    const roomId = projectSlug(title);
    const project: ProjectRecord = {
      project_id: `local-${projectSlug(title)}`,
      title,
      purpose: projectPurposeInput.trim() || "Organise workforce activity around a clear company outcome.",
      status: "active",
      room_id: roomId,
      outcome_ids: [],
      assignment_ids: [],
      knowledge_ids: [],
      worker_ids: [],
      created_at: now,
      updated_at: now,
      local: true,
    };
    const nextProjects = [project, ...storedProjects.filter((item) => projectId(item) !== project.project_id)];
    setStoredProjects(nextProjects);
    writeStoredProjects(nextProjects);
    setSelectedProjectId(project.project_id);
    setSelectedRoom(roomId);
    setProjectTitleInput("");
    setProjectPurposeInput("");
    setView("projects");
    try {
      await api.createRoom(roomId);
      setRoomNotice(`Project conversation #${roomId} created.`);
    } catch {
      setRoomNotice(`Project saved. Conversation #${roomId} may already exist or can be created from Conversations.`);
    }
    setViewError(null);
  }, [projectPurposeInput, projectTitleInput, storedProjects]);

  const refresh = useCallback(async (background = false) => {
    if (background) {
      setRefreshing(true);
    } else {
      setInitialLoading(true);
    }
    let health = await api.getHealth().catch((healthError: unknown) => healthError) as HealthResponse | Error;
    if (health instanceof Error) {
      if (!background) {
        setGlobalError("Checking SynKraken runtime and attempting recovery...");
        const recovery = await ensureRuntime().catch((error: unknown) => ({
          ok: false,
          message: error instanceof Error ? error.message : "Runtime recovery failed.",
        }));
        if (recovery.ok) {
          health = await api.getHealth().catch((healthError: unknown) => healthError) as HealthResponse | Error;
        } else {
          setDaemonStatus("offline");
          setGlobalError(recovery.message || "SynKraken recovery failed.");
          setInitialLoading(false);
          setRefreshing(false);
          return;
        }
      }
    }
    if (health instanceof Error) {
      setDaemonStatus("offline");
      setGlobalError(health.message || "SynKraken is unavailable");
      if (!background) setInitialLoading(false);
      setRefreshing(false);
      return;
    }

    setDaemonStatus("online");
    setGlobalError(null);
    const [agents, workforce, workforcePresence, workforceHealth, proposals, pending, missions, missionSummary, outcomes, outcomeSummary, assignments, assignmentSummary, recentHandoffs, rooms, incident, deadLetters, liveActivity, canvasRelationships, memories] =
      await Promise.allSettled([
        api.getAgents(),
        api.getWorkforce(),
        api.getWorkforcePresence(),
        api.getWorkforceHealth(),
        api.getProposals(),
        api.getPendingProposals(),
        api.getMissions(),
        api.getMissionSummary(),
        api.getOutcomes(),
        api.getOutcomeSummary(),
        api.getAssignments(),
        api.getAssignmentSummary(),
        api.getRecentHandoffs(20),
        api.getRooms(),
        api.getLatestIncident(),
        api.getDeadLetters(100),
        api.getLiveActivity(80),
        api.getCanvasRelationships(500),
        api.getMemory("limit=300"),
      ]);

    const endpointErrors = [agents, workforce, workforcePresence, workforceHealth, proposals, pending, missions, missionSummary, outcomes, outcomeSummary, assignments, assignmentSummary, recentHandoffs, rooms, incident, deadLetters, liveActivity, canvasRelationships, memories]
      .filter((result): result is PromiseRejectedResult => result.status === "rejected")
      .map((result) => result.reason instanceof Error ? result.reason.message : "Endpoint refresh failed");

    setData((current) => {
      const nextRelationships = canvasRelationships.status === "fulfilled" ? canvasRelationships.value.relationships || [] : current.canvasRelationships;
      return {
        health,
        agents: agents.status === "fulfilled" ? agents.value.agents || [] : current.agents,
        workforce: workforce.status === "fulfilled" ? workforce.value : current.workforce,
        workforcePresence: workforcePresence.status === "fulfilled" ? workforcePresence.value : current.workforcePresence,
        workforceHealth: workforceHealth.status === "fulfilled" ? workforceHealth.value : current.workforceHealth,
        proposals: proposals.status === "fulfilled" ? proposals.value.proposals || [] : current.proposals,
        pending: pending.status === "fulfilled" ? pending.value.proposals || [] : current.pending,
        missions: missions.status === "fulfilled" ? missions.value.missions || [] : current.missions,
        missionSummary: missionSummary.status === "fulfilled" ? missionSummary.value : current.missionSummary,
        outcomes: outcomes.status === "fulfilled" ? outcomes.value.outcomes || [] : current.outcomes,
        outcomeSummary: outcomeSummary.status === "fulfilled" ? outcomeSummary.value : current.outcomeSummary,
        assignments: assignments.status === "fulfilled" ? assignments.value.assignments || [] : current.assignments,
        assignmentSummary: assignmentSummary.status === "fulfilled" ? assignmentSummary.value : current.assignmentSummary,
        recentHandoffs: recentHandoffs.status === "fulfilled" ? recentHandoffs.value.handoffs || [] : current.recentHandoffs,
        rooms: rooms.status === "fulfilled" ? rooms.value.rooms || [] : current.rooms,
        incident: incident.status === "fulfilled" ? incident.value : current.incident,
        deadLetters: deadLetters.status === "fulfilled" ? deadLetters.value.dead_letters || [] : current.deadLetters,
        recentActivity: liveActivity.status === "fulfilled" ? liveActivity.value.activity || [] : current.recentActivity,
        liveActivitySummary: liveActivity.status === "fulfilled" ? liveActivity.value.summary : current.liveActivitySummary,
        canvasRelationships: sameCanvasRelationships(current.canvasRelationships, nextRelationships) ? current.canvasRelationships : nextRelationships,
        memories: memories.status === "fulfilled" ? memories.value.memories || [] : current.memories,
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
      const roomMissing = isRoomNotFoundError(roomError);
      const message = roomMissing
        ? roomMissingWarning(name)
        : roomError instanceof Error ? roomError.message : "Room load failed";
      if (!background) setViewError(roomMissing ? `${message}. Create room or select another room` : message);
      setNodeErrors((current) => ({ ...current, [`room:${name}`]: message }));
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
    if (!selectedMissionId && data.missions.length) {
      setSelectedMissionId(missionId(data.missions[0]));
    }
  }, [data.missions, selectedMissionId]);

  useEffect(() => {
    if (!selectedOutcomeId && data.outcomes.length) {
      setSelectedOutcomeId(outcomeId(data.outcomes[0]));
    }
  }, [data.outcomes, selectedOutcomeId]);

  useEffect(() => {
    if (!selectedAssignmentId && data.assignments.length) {
      setSelectedAssignmentId(assignmentId(data.assignments[0]));
    }
  }, [data.assignments, selectedAssignmentId]);

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
    setRoomSending(true);
    try {
      const route = roomTargetFromComposer(roomMessage, selectedRoom);
      if (!route.body) return;
      const result = route.mode === "note"
        ? await api.recordRoomNote(selectedRoom, route.body)
        : route.mode === "worker" || route.mode === "global"
          ? await api.sendRoomScopedMessage(selectedRoom, route.target, route.body)
          : await api.sendMessage(route.target, route.body, selectedRoom);
      setLastRoomDispatch(result);
      setRoomNotice(route.mode === "note" ? "Room note recorded." : `Sent to ${route.target}. ${deliverySummary(result.deliveries || [])}`);
      setRoomMessage("");
      await loadRoom(selectedRoom);
      await refresh();
    } catch (sendError) {
      setViewError(sendError instanceof Error ? sendError.message : "Room broadcast failed");
    } finally {
      setRoomSending(false);
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

  const createRoom = useCallback(async () => {
    const name = roomOperationName.trim().toLowerCase();
    if (!name) return;
    try {
      if (roomOperationMode === "preset") {
        await api.createRoomPreset(roomOperationPreset, name);
      } else {
        await api.createRoom(name);
      }
      setSelectedRoom(name);
      setRoomOperationName("");
      setRoomNotice(`Room #${name} created.`);
      await refresh();
      await loadRoom(name);
    } catch (roomError) {
      setViewError(roomError instanceof Error ? roomError.message : "Room creation failed");
    }
  }, [loadRoom, refresh, roomOperationMode, roomOperationName, roomOperationPreset]);

  const deleteSelectedRoom = useCallback(async () => {
    if (!selectedRoom) return;
    try {
      await api.deleteRoom(selectedRoom);
      const nextRoom = data.rooms.find((room) => text(room.name, "") !== selectedRoom)?.name || "ops";
      setSelectedRoom(text(nextRoom, "ops"));
      setRoomDetail({ messages: [] });
      setRoomNotice(`Room #${selectedRoom} deleted.`);
      await refresh();
    } catch (roomError) {
      setViewError(roomError instanceof Error ? roomError.message : "Room delete failed");
    }
  }, [data.rooms, refresh, selectedRoom]);

  const addAllWorkersToRoom = useCallback(async () => {
    if (!selectedRoom) return;
    const currentMembers = new Set((roomDetail.room?.members || []).map((member) => text(asRecord(member).adapter_id || asRecord(member).id, "")));
    const workerIds = workers.map(workerId).filter((id) => id && !currentMembers.has(id));
    if (!workerIds.length) {
      setRoomNotice("All returned workers are already in this room.");
      return;
    }
    try {
      for (const id of workerIds) {
        await api.addRoomMember(selectedRoom, id);
      }
      setRoomNotice(`Added ${workerIds.length} workers to #${selectedRoom}.`);
      await loadRoom(selectedRoom);
      await refresh();
    } catch (memberError) {
      setViewError(memberError instanceof Error ? memberError.message : "Add all workers failed");
    }
  }, [loadRoom, refresh, roomDetail.room?.members, selectedRoom, workers]);

  const searchRoomHistory = useCallback(async () => {
    if (!selectedRoom || !roomSearchQuery.trim()) return;
    try {
      const result = await api.searchRoomMessages(selectedRoom, roomSearchQuery.trim(), 100);
      setRoomDetail((current) => ({ ...current, messages: result.messages || [] }));
      setRoomNotice(`${result.messages?.length || 0} room history matches.`);
    } catch (searchError) {
      setViewError(searchError instanceof Error ? searchError.message : "Room history search failed");
    }
  }, [roomSearchQuery, selectedRoom]);

  const summarizeRoom = useCallback(async () => {
    if (!selectedRoom) return;
    try {
      const result = await api.summarizeRoom(selectedRoom);
      setRoomNotice(text(result.summary, "Room summary recorded."));
      await loadRoom(selectedRoom);
    } catch (summaryError) {
      setViewError(summaryError instanceof Error ? summaryError.message : "Room summary failed");
    }
  }, [loadRoom, selectedRoom]);

  const createAssignment = useCallback(async () => {
    if (!assignmentTitleInput.trim() || !assignmentOwnerInput.trim()) return;
    try {
      const contributors = assignmentContributorsInput.split(",").map((item) => item.trim()).filter(Boolean);
      const created = await api.createAssignment({
        title: assignmentTitleInput.trim(),
        description: assignmentDescriptionInput.trim(),
        owner_worker: assignmentOwnerInput.trim(),
        contributor_workers: contributors,
        mission_id: assignmentMissionInput.trim() || null,
        outcome_id: assignmentOutcomeInput.trim() || null,
        room_id: assignmentRoomInput.trim() || null,
      });
      const id = assignmentId(created);
      setSelectedAssignmentId(id || null);
      setAssignmentTitleInput("");
      setAssignmentDescriptionInput("");
      setAssignmentOwnerInput("");
      setAssignmentContributorsInput("");
      setAssignmentMissionInput("");
      setAssignmentOutcomeInput("");
      setAssignmentRoomInput("");
      setView("assignments");
      await refresh();
      setViewError(null);
    } catch (assignmentError) {
      setViewError(assignmentError instanceof Error ? assignmentError.message : "Assignment creation failed");
    }
  }, [assignmentContributorsInput, assignmentDescriptionInput, assignmentMissionInput, assignmentOutcomeInput, assignmentOwnerInput, assignmentRoomInput, assignmentTitleInput, refresh]);

  const updateAssignmentStatus = useCallback(async (status: string) => {
    if (!selectedAssignmentId) return;
    try {
      await api.updateAssignment(selectedAssignmentId, { status });
      await refresh();
      setViewError(null);
    } catch (assignmentError) {
      setViewError(assignmentError instanceof Error ? assignmentError.message : "Assignment status update failed");
    }
  }, [refresh, selectedAssignmentId]);

  const assignSelectedOwner = useCallback(async () => {
    if (!selectedAssignmentId || !assignmentOwnerInput.trim()) return;
    try {
      await api.updateAssignment(selectedAssignmentId, { owner_worker: assignmentOwnerInput.trim() });
      await refresh();
      setViewError(null);
    } catch (assignmentError) {
      setViewError(assignmentError instanceof Error ? assignmentError.message : "Assignment owner update failed");
    }
  }, [assignmentOwnerInput, refresh, selectedAssignmentId]);

  const addSelectedContributor = useCallback(async () => {
    if (!selectedAssignmentId || !assignmentContributorsInput.trim()) return;
    const contributor = assignmentContributorsInput.split(",").map((item) => item.trim()).find(Boolean);
    if (!contributor) return;
    try {
      await api.addAssignmentContributor(selectedAssignmentId, contributor);
      setAssignmentContributorsInput("");
      await refresh();
      setViewError(null);
    } catch (assignmentError) {
      setViewError(assignmentError instanceof Error ? assignmentError.message : "Contributor update failed");
    }
  }, [assignmentContributorsInput, refresh, selectedAssignmentId]);

  const removeSelectedContributor = useCallback(async (workerIdValue: string) => {
    if (!selectedAssignmentId || !workerIdValue) return;
    try {
      await api.removeAssignmentContributor(selectedAssignmentId, workerIdValue);
      await refresh();
      setViewError(null);
    } catch (assignmentError) {
      setViewError(assignmentError instanceof Error ? assignmentError.message : "Contributor removal failed");
    }
  }, [refresh, selectedAssignmentId]);

  const handoffSelectedAssignment = useCallback(async () => {
    if (!selectedAssignmentId || !handoffToInput.trim() || !handoffReasonInput.trim()) return;
    try {
      await api.handoffAssignment(selectedAssignmentId, handoffToInput.trim(), handoffReasonInput.trim());
      setHandoffToInput("");
      setHandoffReasonInput("");
      await refresh();
      setViewError(null);
    } catch (assignmentError) {
      setViewError(assignmentError instanceof Error ? assignmentError.message : "Assignment handoff failed");
    }
  }, [handoffReasonInput, handoffToInput, refresh, selectedAssignmentId]);

  const dispatchCanvasCommand = useCallback((command: CanvasCommandInput) => {
    setView("canvas");
    setCanvasCommand({ ...command, nonce: Date.now() } as CanvasCommand);
    if (command.kind === "workspace") {
      setCanvasWorkspace(command.workspace);
    }
  }, []);

  const createMemoryNote = useCallback(async (scopeType?: string, scopeId?: string) => {
    try {
      await api.createMemoryNote({
        title: memoryNoteTitle,
        body: memoryNoteBody,
        scope_type: scopeType || memoryScopeType,
        scope_id: scopeId || memoryScopeId || undefined,
        importance: memoryImportance,
        actor: "operator",
      });
      setMemoryNoteTitle("");
      setMemoryNoteBody("");
      await refresh(true);
      setViewError(null);
    } catch (memoryError) {
      setViewError(memoryError instanceof Error ? memoryError.message : "Memory note creation failed");
    }
  }, [memoryImportance, memoryNoteBody, memoryNoteTitle, memoryScopeId, memoryScopeType, refresh]);

  const createProjectKnowledgeNote = useCallback(async (project: ProjectRecord) => {
    if (!projectKnowledgeDraft.title.trim() || !projectKnowledgeDraft.body.trim()) {
      setViewError("Project knowledge title and note are required");
      return;
    }
    try {
      await api.createMemoryNote({
        title: projectKnowledgeDraft.title.trim(),
        body: projectKnowledgeDraft.body.trim(),
        scope_type: project.room_id ? "room" : project.mission_id ? "mission" : "global",
        scope_id: project.room_id || project.mission_id || undefined,
        importance: projectKnowledgeDraft.importance,
        actor: "operator",
      });
      setProjectKnowledgeDraft({ title: "", body: "", importance: "high" });
      await refresh(true);
      setViewError(null);
    } catch (memoryError) {
      setViewError(memoryError instanceof Error ? memoryError.message : "Project knowledge save failed");
    }
  }, [projectKnowledgeDraft, refresh]);

  const memoryAction = useCallback(async (memoryId: string, action: "approve" | "reject" | "archive") => {
    try {
      if (action === "approve") await api.approveMemory(memoryId);
      if (action === "reject") await api.rejectMemory(memoryId);
      if (action === "archive") await api.archiveMemory(memoryId);
      await refresh(true);
      setViewError(null);
    } catch (memoryError) {
      setViewError(memoryError instanceof Error ? memoryError.message : "Memory action failed");
    }
  }, [refresh]);

  const commands = useMemo(
    () => [
      { label: "Open Advanced Canvas", run: () => setView("canvas") },
      { label: "Open Home", run: () => setView("home") },
      { label: "Open Projects", run: () => setView("projects") },
      { label: "Create Project", run: () => setView("projects") },
      { label: "Open Advanced", run: () => setView("advanced") },
      { label: "Open Work Internals", run: () => setView("work") },
      { label: "Open Missions", run: () => { setWorkTab("missions"); setView("work"); } },
      { label: "Open Outcomes", run: () => { setWorkTab("outcomes"); setView("work"); } },
      { label: "Open Assignments", run: () => { setWorkTab("assignments"); setView("work"); } },
      { label: "Open Search", run: () => setView("search") },
      { label: "Open Knowledge", run: () => setView("knowledge") },
      { label: "Open Decisions Internals", run: () => setView("governance") },
      { label: "Switch workspace: Coding", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Coding" }) },
      { label: "Switch workspace: Operations", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Operations" }) },
      { label: "Switch workspace: Research", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Research" }) },
      { label: "Switch workspace: Incident Response", run: () => dispatchCanvasCommand({ kind: "workspace", workspace: "Incident Response" }) },
      { label: "Add Workforce Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "workforce-summary" }) },
      { label: "Add Briefing Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "briefing" }) },
      { label: "Add Runtime Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "runtime", refId: workers[0] ? workerId(workers[0]) : undefined }) },
      { label: "Add Room Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "room", refId: data.rooms[0]?.name }) },
      { label: "Add Mission Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "mission", refId: data.missions[0] ? missionId(data.missions[0]) : undefined }) },
      { label: "Add Outcome Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "outcome", refId: data.outcomes[0] ? outcomeId(data.outcomes[0]) : undefined }) },
      { label: "Add Assignment Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "assignment", refId: data.assignments[0] ? assignmentId(data.assignments[0]) : undefined }) },
      { label: "Add Memory Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "memory", refId: data.memories[0]?.memory_id }) },
      { label: "Add Proposal Queue Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "proposal-queue" }) },
      { label: "Add Proposal Detail Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "proposal-detail", refId: data.pending[0] ? proposalId(data.pending[0]) : undefined }) },
      { label: "Add Incident Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "incident" }) },
      { label: "Add Trace Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "trace" }) },
      { label: "Add Dead Letter Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "dead-letter" }) },
      { label: "Add Activity Feed Node", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "activity-feed" }) },
      { label: "Fit Canvas", run: () => dispatchCanvasCommand({ kind: "fit" }) },
      { label: "Reset Layout", run: () => dispatchCanvasCommand({ kind: "reset" }) },
      { label: "Clear Saved Layout", run: () => dispatchCanvasCommand({ kind: "clear-layout" }) },
      { label: "Focus Runtime", run: () => dispatchCanvasCommand({ kind: "focus-runtime" }) },
      { label: "Focus Room", run: () => dispatchCanvasCommand({ kind: "focus-room" }) },
      { label: "Focus Proposal", run: () => dispatchCanvasCommand({ kind: "focus-proposal" }) },
      { label: "Focus Trace", run: () => dispatchCanvasCommand({ kind: "focus-trace" }) },
      { label: "Show Active Workers", run: () => { setView("workforce"); setSelectedRuntime(data.workforcePresence?.workers?.find((worker) => worker.presence_state === "active")?.runtime_id || null); } },
      { label: "Show Workers Needing Attention", run: () => { setView("workforce"); setSelectedRuntime(data.workforcePresence?.workers?.find((worker) => worker.needs_attention)?.runtime_id || null); } },
      { label: "Focus Activity Feed", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "activity-feed" }) },
      { label: "Open Presence Summary", run: () => setView("workforce") },
      { label: "Create Conversation", run: () => { setView("conversations"); setRoomOperationMode("create"); } },
      { label: "Delete Conversation", run: () => { setView("conversations"); void deleteSelectedRoom(); } },
      { label: "Open Conversation", run: () => setView("conversations") },
      { label: "Open Conversation Chat", run: () => setView("conversations") },
      { label: "Add Worker to Conversation", run: () => setView("conversations") },
      { label: "Add All Workers to Conversation", run: () => { setView("conversations"); void addAllWorkersToRoom(); } },
      { label: "Broadcast @everyone", run: () => { setView("conversations"); setRoomMessage("@everyone Who is available?"); } },
      { label: "Message Worker", run: () => { setView("conversations"); setRoomMessage(`@${workers[0] ? workerId(workers[0]) : "worker-id"} `); } },
      { label: "Refresh Conversation", run: () => { setView("conversations"); void loadRoom(selectedRoom); } },
      { label: "Search Conversation History", run: () => setView("conversations") },
      { label: "Create Assignment", run: () => { setWorkTab("assignments"); setView("work"); } },
      { label: "Assign Worker", run: () => { setWorkTab("assignments"); setView("work"); void assignSelectedOwner(); } },
      { label: "Add Contributor", run: () => { setWorkTab("assignments"); setView("work"); void addSelectedContributor(); } },
      { label: "Mark Waiting", run: () => { setWorkTab("assignments"); setView("work"); void updateAssignmentStatus("waiting"); } },
      { label: "Mark Blocked", run: () => { setWorkTab("assignments"); setView("work"); void updateAssignmentStatus("blocked"); } },
      { label: "Request Review", run: () => { setWorkTab("assignments"); setView("work"); void updateAssignmentStatus("review"); } },
      { label: "Complete Assignment", run: () => { setWorkTab("assignments"); setView("work"); void updateAssignmentStatus("completed"); } },
      { label: "View Handoffs", run: () => setView("governance") },
      { label: "Focus Assignment", run: () => dispatchCanvasCommand({ kind: "add", nodeType: "assignment", refId: selectedAssignmentId || (data.assignments[0] ? assignmentId(data.assignments[0]) : undefined) }) },
      ...(data.workforcePresence?.workers?.slice(0, 8).map((worker) => ({
        label: `Focus Worker: ${worker.runtime_id}`,
        run: () => dispatchCanvasCommand({ kind: "focus-runtime", id: worker.runtime_id }),
      })) || []),
      ...data.rooms.slice(0, 8).map((room) => ({
        label: `Focus Room: #${text(room.name, "room")}`,
        run: () => dispatchCanvasCommand({ kind: "focus-room", id: text(room.name, "") }),
      })),
      { label: "Go to Workforce", run: () => setView("workforce") },
      { label: "Go to Home", run: () => setView("home") },
      { label: "Go to Projects", run: () => setView("projects") },
      { label: "Go to Advanced", run: () => setView("advanced") },
      { label: "Go to Work Internals", run: () => setView("work") },
      { label: "Go to Missions", run: () => { setWorkTab("missions"); setView("work"); } },
      { label: "Go to Outcomes", run: () => { setWorkTab("outcomes"); setView("work"); } },
      { label: "Go to Assignments", run: () => { setWorkTab("assignments"); setView("work"); } },
      { label: "Go to Search", run: () => setView("search") },
      { label: "Go to Conversations", run: () => setView("conversations") },
      { label: "Go to Governance", run: () => setView("governance") },
      { label: "Go to Flight Recorder", run: () => setView("flight") },
      { label: "Go to Incidents", run: () => setView("incidents") },
      { label: "Search Runtime", run: () => setView("workforce") },
      { label: "Search Mission", run: () => { setWorkTab("missions"); setView("work"); } },
      { label: "Search Outcome", run: () => { setWorkTab("outcomes"); setView("work"); } },
      { label: "Search Governance", run: () => setView("governance") },
      { label: "Search Trace", run: () => setView("flight") },
      { label: "Live Refresh", run: () => void refresh() },
    ],
    [addAllWorkersToRoom, addSelectedContributor, assignSelectedOwner, data.assignments, data.missions, data.outcomes, data.pending, data.rooms, data.workforcePresence, deleteSelectedRoom, dispatchCanvasCommand, loadRoom, refresh, selectedAssignmentId, selectedRoom, updateAssignmentStatus, workers],
  );

  const isNavActive = useCallback((item: View) => {
    if (item === view) return true;
    if (item === "conversations" && view === "rooms") return true;
    if (item === "knowledge" && view === "memory") return true;
    if (item === "projects" && ["work", "missions", "outcomes", "assignments"].includes(view)) return true;
    if (item === "advanced" && ["governance", "proposals", "proposal-detail", "activity", "flight", "incidents", "canvas", "settings"].includes(view)) return true;
    return false;
  }, [view]);

  return (
    <div className="app-shell min-h-screen bg-abyss text-slate-100">
      <aside className="sidebar fixed inset-y-0 left-0 w-60 border-r border-line bg-panel">
        <div className="window-controls" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <div className="sidebar-brand border-b border-line px-5 py-4">
          <div className="brand-mark">SynKraken</div>
          <div className="brand-subtitle">AI workforce</div>
        </div>
        <nav className="p-3">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${isNavActive(item.id) ? "nav-item-active" : ""}`}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer absolute bottom-0 left-0 right-0 border-t border-line p-4 font-mono text-[11px] text-muted">
          Local daemon
          <br />
          Human approval
          <br />
          Durable record
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

        <section className="main-content p-4">
          {view === "home" && (
            <HomeView
              data={data}
              projects={projects}
              workers={workers}
              daemonStatus={daemonStatus}
              onView={setView}
              onProjectTarget={(target) => {
                if (target.projectId) setSelectedProjectId(target.projectId);
                if (target.tab) setProjectTab(target.tab);
                if (target.roomId) setSelectedRoom(target.roomId);
                setView("projects");
              }}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "projects" && (
            <ProjectsView
              data={data}
              workers={workers}
              projects={projects}
              selectedProjectId={selectedProjectId}
              tab={projectTab}
              titleInput={projectTitleInput}
              purposeInput={projectPurposeInput}
              knowledgeDraft={projectKnowledgeDraft}
              roomDetail={roomDetail}
              roomMessage={roomMessage}
              sending={roomSending}
              onSelectProject={(id) => {
                const project = projects.find((item) => projectId(item) === id);
                setSelectedProjectId(id);
                setProjectTab("overview");
                if (project?.room_id) setSelectedRoom(project.room_id);
              }}
              onTab={setProjectTab}
              onTitleInput={setProjectTitleInput}
              onPurposeInput={setProjectPurposeInput}
              onKnowledgeDraft={setProjectKnowledgeDraft}
              onCreateKnowledge={(project) => void createProjectKnowledgeNote(project)}
              onCreate={createProject}
              onMessage={setRoomMessage}
              onSend={() => void sendRoomMessage()}
              onOpenConversation={(room) => {
                setSelectedRoom(room);
                setView("conversations");
              }}
              onOpenProposal={openProposal}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
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
              onRoomQuickMessage={(room, value) => {
                setSelectedRoom(room);
                setRoomMessage(value);
                setView("conversations");
              }}
              onAddAllWorkers={() => void addAllWorkersToRoom()}
            />
          )}
          {view === "briefing" && (
            <BriefingView
              data={data}
              workers={workers}
              onView={setView}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "work" && (
            <WorkView
              tab={workTab}
              onTab={setWorkTab}
              data={data}
              workers={workers}
              selectedMissionId={selectedMissionId}
              selectedOutcomeId={selectedOutcomeId}
              selectedAssignmentId={selectedAssignmentId}
              titleInput={assignmentTitleInput}
              descriptionInput={assignmentDescriptionInput}
              ownerInput={assignmentOwnerInput}
              contributorsInput={assignmentContributorsInput}
              missionInput={assignmentMissionInput}
              outcomeInput={assignmentOutcomeInput}
              roomInput={assignmentRoomInput}
              handoffToInput={handoffToInput}
              handoffReasonInput={handoffReasonInput}
              onSelectMission={setSelectedMissionId}
              onSelectOutcome={setSelectedOutcomeId}
              onSelectAssignment={setSelectedAssignmentId}
              onTitleInput={setAssignmentTitleInput}
              onDescriptionInput={setAssignmentDescriptionInput}
              onOwnerInput={setAssignmentOwnerInput}
              onContributorsInput={setAssignmentContributorsInput}
              onMissionInput={setAssignmentMissionInput}
              onOutcomeInput={setAssignmentOutcomeInput}
              onRoomInput={setAssignmentRoomInput}
              onHandoffToInput={setHandoffToInput}
              onHandoffReasonInput={setHandoffReasonInput}
              onCreate={() => void createAssignment()}
              onAssignOwner={() => void assignSelectedOwner()}
              onAddContributor={() => void addSelectedContributor()}
              onRemoveContributor={(workerIdValue) => void removeSelectedContributor(workerIdValue)}
              onStatus={(status) => void updateAssignmentStatus(status)}
              onHandoff={() => void handoffSelectedAssignment()}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "advanced" && (
            <AdvancedView
              data={data}
              onView={setView}
            />
          )}
          {view === "missions" && (
            <MissionsView
              data={data}
              selectedMissionId={selectedMissionId}
              onSelectMission={setSelectedMissionId}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "outcomes" && (
            <OutcomesView
              data={data}
              selectedOutcomeId={selectedOutcomeId}
              onSelectOutcome={setSelectedOutcomeId}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "assignments" && (
            <AssignmentsView
              data={data}
              workers={workers}
              selectedAssignmentId={selectedAssignmentId}
              titleInput={assignmentTitleInput}
              descriptionInput={assignmentDescriptionInput}
              ownerInput={assignmentOwnerInput}
              contributorsInput={assignmentContributorsInput}
              missionInput={assignmentMissionInput}
              outcomeInput={assignmentOutcomeInput}
              roomInput={assignmentRoomInput}
              handoffToInput={handoffToInput}
              handoffReasonInput={handoffReasonInput}
              onSelectAssignment={setSelectedAssignmentId}
              onTitleInput={setAssignmentTitleInput}
              onDescriptionInput={setAssignmentDescriptionInput}
              onOwnerInput={setAssignmentOwnerInput}
              onContributorsInput={setAssignmentContributorsInput}
              onMissionInput={setAssignmentMissionInput}
              onOutcomeInput={setAssignmentOutcomeInput}
              onRoomInput={setAssignmentRoomInput}
              onHandoffToInput={setHandoffToInput}
              onHandoffReasonInput={setHandoffReasonInput}
              onCreate={() => void createAssignment()}
              onAssignOwner={() => void assignSelectedOwner()}
              onAddContributor={() => void addSelectedContributor()}
              onRemoveContributor={(workerIdValue) => void removeSelectedContributor(workerIdValue)}
              onStatus={(status) => void updateAssignmentStatus(status)}
              onHandoff={() => void handoffSelectedAssignment()}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "activity" && (
            <ActivityView
              data={data}
              workers={workers}
              rooms={data.rooms}
              missions={data.missions}
              outcomes={data.outcomes}
              assignments={data.assignments}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {(view === "knowledge" || view === "memory") && (
            <KnowledgeView
              memories={data.memories}
              title={memoryNoteTitle}
              body={memoryNoteBody}
              scopeType={memoryScopeType}
              scopeId={memoryScopeId}
              importance={memoryImportance}
              onTitle={setMemoryNoteTitle}
              onBody={setMemoryNoteBody}
              onScopeType={setMemoryScopeType}
              onScopeId={setMemoryScopeId}
              onImportance={setMemoryImportance}
              onCreate={() => void createMemoryNote()}
              onAction={(memoryId, action) => void memoryAction(memoryId, action)}
            />
          )}
          {view === "workforce" && (
            <WorkforceView
              data={data}
              workers={workers}
              proposals={data.proposals}
              missions={data.missions}
              outcomes={data.outcomes}
              rooms={data.rooms}
              daemonStatus={daemonStatus}
              selectedRuntime={selectedRuntime}
              onSelectRuntime={setSelectedRuntime}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {view === "governance" && (
            <GovernanceView
              proposals={data.proposals}
              pending={data.pending}
              handoffs={data.recentHandoffs}
              onOpen={openProposal}
              onAction={proposalAction}
              onReplay={(id) => void loadReplay(id)}
            />
          )}
          {(view === "conversations" || view === "rooms") && (
            <RoomsView
              data={data}
              rooms={data.rooms}
              workers={workers}
              proposals={data.proposals}
              selectedRoom={selectedRoom}
              roomDetail={roomDetail}
              roomError={nodeErrors[`room:${selectedRoom}`]}
              message={roomMessage}
              member={roomMember}
              createName={roomOperationName}
              createPreset={roomOperationPreset}
              createMode={roomOperationMode}
              searchQuery={roomSearchQuery}
              notice={roomNotice}
              sending={roomSending}
              lastDispatch={lastRoomDispatch}
              onSelectRoom={setSelectedRoom}
              onMessage={setRoomMessage}
              onMember={setRoomMember}
              onCreateName={setRoomOperationName}
              onCreatePreset={setRoomOperationPreset}
              onCreateMode={setRoomOperationMode}
              onSearchQuery={setRoomSearchQuery}
              onCreateRoom={() => void createRoom()}
              onDeleteRoom={() => void deleteSelectedRoom()}
              onAddAllWorkers={() => void addAllWorkersToRoom()}
              onRefreshRoom={() => void loadRoom(selectedRoom)}
              onSearchRoom={() => void searchRoomHistory()}
              onSummarizeRoom={() => void summarizeRoom()}
              onSend={() => void sendRoomMessage()}
              onMemberAction={(action, adapterId) => void updateRoomMember(action, adapterId)}
            />
          )}
          {view === "search" && (
            <SearchView
              data={data}
              workers={workers}
              rooms={data.rooms}
              onView={setView}
              onSelectRoom={setSelectedRoom}
              onSelectRuntime={setSelectedRuntime}
              onOpenProposal={openProposal}
              onReplay={(id) => void loadReplay(id)}
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
          {view === "settings" && (
            <SettingsView data={data} daemonStatus={daemonStatus} onRefresh={() => void refresh(false)} />
          )}
          {view === "incidents" && (
            <IncidentsView
              data={data}
              workers={workers}
              rooms={data.rooms}
              proposals={data.proposals}
              missions={data.missions}
              outcomes={data.outcomes}
              daemonStatus={daemonStatus}
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
  const legacySummary = summariseWorkforceState(workers, data.pending, data.deadLetters, online ? "online" : "offline");
  const presenceSummary = data.workforcePresence?.summary;
  const liveSummary = data.liveActivitySummary;
  const needsAttention = Number(presenceSummary?.needs_attention ?? workers.filter((worker) => displaySeverityForRuntime(worker) !== "Operational").length);
  const workforceState = online
    ? needsAttention
      ? "Usable with issues"
      : "Usable"
    : "Offline";

  return (
    <header className="topbar sticky top-0 z-20 border-b border-line bg-abyss/95 px-4 py-3 backdrop-blur">
      <div className="grid grid-cols-[1fr_minmax(260px,520px)_auto] items-center gap-4">
        <button className="daemon-pill flex min-w-0 items-center gap-3 text-left text-sm" onClick={onPalette}>
          <span className={`status-dot ${online ? "bg-cyanop" : "bg-danger"}`} />
          <span className={online ? "text-slate-100" : "text-danger"}>{online ? "Daemon online" : "Daemon offline"}</span>
          <span className="truncate text-muted">{workforceState}</span>
        </button>
        <button className="command-search" onClick={onPalette}>Search or open a view</button>
        <div className="flex items-center justify-end gap-3 text-sm">
          {loading && <span className="text-amberop">Loading</span>}
          {!loading && refreshing && <span className="text-muted">Refreshing</span>}
          {error && <span className="text-danger">Offline</span>}
          <button className="btn" onClick={onRefresh}>Refresh</button>
        </div>
      </div>
    </header>
  );
}

function ActivitySummaryBar({ data }: { data: AppData }) {
  const summary = data.liveActivitySummary;
  return (
    <section className="activity-summary-bar">
      <Metric label="workforce active now" value={`${Number(summary?.active_workers ?? data.workforcePresence?.summary?.active ?? 0)} workers`} />
      <Metric label="recent events" value={Number(summary?.recent_events ?? data.recentActivity.length)} />
      <Metric label="last activity" value={secondsAgo(summary?.last_activity_seconds_ago)} />
    </section>
  );
}

function OperatorSummary({ title = "AI Workforce Summary", data, workers, daemonStatus }: { title?: string; data: AppData; workers: Agent[]; daemonStatus: DaemonStatus }) {
  const summary = summariseWorkforceState(workers, data.pending, data.deadLetters, daemonStatus);
  const presence = data.workforcePresence?.summary;
  const activity = data.recentActivity.length ? data.recentActivity : data.workforcePresence?.recent_activity || [];
  const blocked = daemonStatus === "offline";
  const needsAttention = Number(presence?.needs_attention ?? summary.needsAttention.length);
  const active = Number(presence?.active ?? 0);
  const idle = Number(presence?.idle ?? 0);
  const status = blocked ? "Offline" : needsAttention ? "Usable with issues" : "Usable";
  const highestPriority = text(presence?.highest_priority, summary.highestPriority);
  const suggestedAction = text(presence?.suggested_next_action, summary.suggestedAction);
  return (
    <section className={`operator-summary ${blocked ? "operator-summary-critical" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-mono text-sm uppercase tracking-[0.18em] text-cyanop">{title}</h2>
          <div className={`mt-2 font-mono text-xl ${blocked ? "text-danger" : needsAttention ? "text-amberop" : "text-cyanop"}`}>{status}</div>
        </div>
        <span className={`pill ${blocked ? "status-danger" : needsAttention ? "status-warn" : "status-good"}`}>Presence aware</span>
      </div>
      <div className="operator-summary-grid">
        <Field label="usable" value={blocked ? "No, daemon health is offline." : "Yes, continue with awareness."} />
        <Field label="needs attention" value={needsAttention ? `${needsAttention} worker(s)` : "None"} />
        <Field label="highest priority" value={highestPriority} />
        <Field label="suggested action" value={suggestedAction} />
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-5">
        <Metric label="agents connected" value={workers.length} />
        <Metric label="active" value={active} />
        <Metric label="idle" value={idle} />
        <Metric label="needs attention" value={needsAttention} />
        <Metric label="pending proposals" value={data.pending.length} />
      </div>
      <div className="activity-teasers">
        {(activity || []).slice(0, 3).map((item, index) => (
          <span key={text(item.activity_id || index, String(index))}>{text(item.summary, "No recent activity recorded.")}</span>
        ))}
      </div>
    </section>
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
  onRoomQuickMessage,
  onAddAllWorkers,
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
  onRoomQuickMessage: (room: string, value: string) => void;
  onAddAllWorkers: () => void;
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
    setNodes(createPresetNodes(workspace, workers, data.rooms, data.pending.length ? data.pending : data.proposals, data.deadLetters, data.missions, data.outcomes, data.assignments));
    setSelectedNode(null);
    setTransform({ x: 40, y: 40, scale: 1 });
  }, [data.deadLetters, data.missions, data.outcomes, data.pending, data.proposals, data.rooms, selectedWorkspace, workers]);

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
    const target = inferCanvasTarget(focusQuery, workers, data.rooms, data.missions, data.outcomes, data.assignments, data.proposals, data.deadLetters);
    focusOrCreateNode(target.type, target.refId);
    if (target.type === "room" && target.refId) onSelectRoom(target.refId);
    if (target.type === "proposal-detail" && target.refId) onOpenProposal(target.refId);
  }, [data.assignments, data.deadLetters, data.missions, data.outcomes, data.proposals, data.rooms, focusOrCreateNode, focusQuery, onOpenProposal, onSelectRoom, workers]);

  return (
    <div className="space-y-4">
      <OperatorSummary data={data} workers={workers} daemonStatus={daemonStatus} />
      <div className="operations-shell">
        <div className="canvas-toolbar">
          <div>
            <h1 className="font-mono text-xl text-slate-50">Advanced Canvas</h1>
            <p className="text-xs text-muted">Spatial view for advanced inspection · saved locally</p>
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
              <option value="mission">Mission</option>
              <option value="outcome">Outcome</option>
              <option value="assignment">Assignment</option>
              <option value="memory">Memory</option>
              <option value="proposal-queue">Proposal Queue</option>
              <option value="proposal-detail">Proposal Detail</option>
              <option value="incident">Incident</option>
              <option value="trace">Trace</option>
              <option value="dead-letter">Dead Letter</option>
              <option value="activity-feed">Activity Feed</option>
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
                const tone = nodeTone(node.type, node, workers, data.pending, data.deadLetters, data.missions, data.outcomes, data.assignments, data.workforcePresence);
                const nodeError = nodeErrors[node.id] || (node.type === "room" && node.refId && !data.rooms.some((room) => room.name === node.refId) ? roomMissingWarning(node.refId) : undefined);
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
                    onRoomQuickMessage={onRoomQuickMessage}
                    onAddAllWorkers={onAddAllWorkers}
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
  onRoomQuickMessage,
  onAddAllWorkers,
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
  onRoomQuickMessage: (room: string, value: string) => void;
  onAddAllWorkers: () => void;
  onTraceId: (id: string) => void;
  onLoadTrace: () => void;
  onReplay: (id: string) => void;
  onView: (view: View) => void;
}) {
  const runtime = node.type === "runtime" ? workers.find((item) => workerId(item) === node.refId) : null;
  const runtimePresence = runtime ? presenceForWorker(runtime, data.workforcePresence) : undefined;
  const displayStatus = loading
    ? "loading"
    : error
      ? "Needs attention"
      : refreshing
        ? "polling"
        : runtime
          ? presenceLabel(runtimePresence?.presence_state) || humanHealthFromPresence(runtimePresence, runtime)
          : tone === "degraded" || tone === "pending" ? "Needs attention" : "Operational";
  return (
    <article
      className={`canvas-node canvas-node-${tone} ${selected ? "canvas-node-selected" : ""}`}
      style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
      onMouseDown={onSelect}
    >
      <header className="canvas-node-header" onMouseDown={onDragStart}>
        <span>{node.type.replace("-", " ")}</span>
        <strong>{node.title}</strong>
        <em>
          {runtime && <i className={`canvas-live-indicator ${canvasPresenceIndicatorClass(runtimePresence?.presence_state)}`} />}
          {displayStatus}
        </em>
      </header>
      <div className="canvas-node-meta">
        <span>{node.refId || "daemon"}</span>
        <span>{shortDate(new Date().toISOString())}</span>
      </div>
      <div className="canvas-node-body">
        {error && <div className="text-xs text-danger">{error}</div>}
        {node.type === "room" && error?.startsWith("Room not found:") && <div className="mt-2 text-xs text-amberop">Create room or select another room</div>}
        {node.type === "workforce-summary" && <WorkforceSummaryNode data={data} workers={workers} daemonStatus={daemonStatus} />}
        {node.type === "briefing" && <BriefingNode data={data} workers={workers} onView={onView} />}
        {node.type === "runtime" && <RuntimeNode node={node} data={data} workers={workers} onView={onView} />}
        {node.type === "room" && <RoomNode node={node} data={data} selectedRoom={selectedRoom} onSelectRoom={onSelectRoom} onView={onView} onRoomQuickMessage={onRoomQuickMessage} onAddAllWorkers={onAddAllWorkers} />}
        {node.type === "mission" && <MissionNode node={node} data={data} onView={onView} />}
        {node.type === "outcome" && <OutcomeNode node={node} data={data} onView={onView} />}
        {node.type === "assignment" && <AssignmentNode node={node} data={data} onView={onView} />}
        {node.type === "memory" && <MemoryNode node={node} data={data} onView={onView} />}
        {node.type === "proposal-queue" && <ProposalQueueNode proposals={data.pending} onOpen={onOpenProposal} onAction={onProposalAction} onView={onView} />}
        {node.type === "proposal-detail" && <ProposalDetailNode node={node} proposal={selectedProposal || data.proposals.find((proposal) => proposalId(proposal) === node.refId) || null} onAction={onProposalAction} onReplay={onReplay} />}
        {node.type === "incident" && <IncidentNode data={data} workers={workers} onView={onView} onReplay={onReplay} />}
        {node.type === "trace" && <TraceNode traceId={traceId || node.refId || ""} trace={trace} traceError={traceError} onTraceId={onTraceId} onLoadTrace={onLoadTrace} onReplay={onReplay} />}
        {node.type === "dead-letter" && <DeadLetterNode data={data} onReplay={onReplay} />}
        {node.type === "activity-feed" && <ActivityFeedNode data={data} onReplay={onReplay} onView={onView} />}
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
  const tone = nodeTone(node.type, node, workers, data.pending, data.deadLetters, data.missions, data.outcomes, data.assignments, data.workforcePresence);
  const runtime = node.type === "runtime" ? workers.find((worker) => workerId(worker) === node.refId) : null;
  const runtimePresence = runtime ? presenceForWorker(runtime, data.workforcePresence) : undefined;
  const displayStatus = runtime ? humanHealthFromPresence(runtimePresence, runtime) : tone === "degraded" || tone === "pending" ? "Needs attention" : "Operational";
  const room = node.type === "room" ? data.rooms.find((item) => item.name === node.refId) : null;
  const mission = node.type === "mission" ? data.missions.find((item) => missionId(item) === node.refId) || data.missions[0] : null;
  const outcome = node.type === "outcome" ? data.outcomes.find((item) => outcomeId(item) === node.refId) || data.outcomes[0] : null;
  const assignment = node.type === "assignment" ? data.assignments.find((item) => assignmentId(item) === node.refId) || data.assignments[0] : null;
  const proposal = node.type === "proposal-detail" ? data.proposals.find((item) => proposalId(item) === node.refId) : null;
  const latestDeadLetter = asRecord(data.deadLetters[0]);

  return (
    <aside className="canvas-inspector">
      <div className="canvas-inspector-title">Canvas Inspector</div>
      <div className="canvas-inspector-section">
        <Field label="node type" value={node.type} />
        <Field label="status" value={displayStatus} />
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

      {node.type === "briefing" && (
        <div className="canvas-inspector-section">
          <Field label="active missions" value={data.missions.filter((mission) => text(mission.status, "") === "active").length} />
          <Field label="blocked assignments" value={data.assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked").length} />
          <Field label="pending proposals" value={data.pending.length} />
          <Field label="recommended actions" value={recommendedNextActions(data, workers).length} />
          <button className="btn-cyan" onClick={() => onView("briefing")}>Open Briefing</button>
        </div>
      )}

      {node.type === "runtime" && runtime && (
        <div className="canvas-inspector-section">
          <Field label="presence" value={presenceLabel(runtimePresence?.presence_state)} />
          <Field label="severity" value={humanHealthFromPresence(runtimePresence, runtime)} />
          <Field label="raw health" value={workerHealth(runtime)} />
          <Field label="trust" value={percent(runtimePresence?.trust_score ?? workerReputation(runtime).trust_score ?? runtime.trust_score ?? runtime.trust)} />
          <Field label="cost tier" value={text(runtime.cost_tier || workerReputation(runtime).cost_tier, "medium")} />
          <Field label="last activity" value={text(runtimePresence?.latest_activity_summary, "No recent activity recorded.")} />
          <Field label="issue" value={text(runtimePresence?.attention_reason, explainRuntimeIssue(runtime))} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} />
          <button className="btn-cyan" onClick={() => onView("workforce")}>Open Runtime Detail</button>
        </div>
      )}

      {node.type === "activity-feed" && (
        <div className="canvas-inspector-section">
          <Field label="recent activity" value={data.recentActivity.length || data.workforcePresence?.recent_activity?.length || 0} />
          <Field label="highest priority" value={data.workforcePresence?.summary?.highest_priority || "No active issues detected."} />
          <button className="btn-cyan" onClick={() => onView("search")}>Open Search</button>
        </div>
      )}

      {node.type === "room" && (
        <div className="canvas-inspector-section">
          <Field label="room" value={`#${node.refId || "ops"}`} />
          <Field label="members" value={room?.member_count ?? 0} />
          <Field label="last activity" value={shortDate(room?.last_activity)} />
          <Field label="assignments" value={data.assignments.filter((item) => item.room_id === (node.refId || "ops")).length} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} />
          <button className="btn-cyan" onClick={() => { onSelectRoom(node.refId || "ops"); onView("conversations"); }}>Open Conversation</button>
          <button className="btn" onClick={() => { onSelectRoom(node.refId || "ops"); onView("conversations"); }}>Open Chat</button>
          <button className="btn" onClick={() => { onSelectRoom(node.refId || "ops"); onView("conversations"); }}>Broadcast @everyone</button>
          <button className="btn" onClick={() => { onSelectRoom(node.refId || "ops"); onView("conversations"); }}>Add Workers</button>
        </div>
      )}

      {node.type === "mission" && mission && (
        <div className="canvas-inspector-section">
          <Field label="mission" value={missionTitle(mission)} />
          <Field label="status" value={mission.status} />
          <Field label="priority" value={mission.priority} />
          <Field label="workers" value={(mission.workers || []).length} />
          <Field label="open proposals" value={(mission.proposals || []).filter((proposal) => proposal.status === "proposed").length} />
          <Field label="incidents" value={(mission.incidents || []).length} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} />
          <button className="btn-cyan" onClick={() => onView("work")}>Open Work</button>
        </div>
      )}

      {node.type === "outcome" && outcome && (
        <div className="canvas-inspector-section">
          <Field label="outcome" value={outcomeTitle(outcome)} />
          <Field label="mission" value={outcome.mission_title || outcome.mission_id} />
          <Field label="status" value={outcome.status} />
          <Field label="confidence" value={outcome.confidence} />
          <Field label="workers" value={(outcome.workers || []).length} />
          <Field label="open proposals" value={(outcome.proposals || []).filter((proposal) => proposal.status === "proposed").length} />
          <Field label="incidents" value={(outcome.incidents || []).length} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} />
          <button className="btn-cyan" onClick={() => onView("work")}>Open Work</button>
        </div>
      )}

      {node.type === "assignment" && assignment && (
        <div className="canvas-inspector-section">
          <Field label="assignment" value={assignmentTitle(assignment)} />
          <Field label="status" value={assignmentStatusLabel(assignment.status)} />
          <Field label="owner" value={assignment.owner_worker || "Unassigned"} />
          <Field label="contributors" value={(assignment.contributor_workers || []).length} />
          <Field label="mission" value={assignmentMissionTitle(assignment, data.missions)} />
          <Field label="outcome" value={assignmentOutcomeTitle(assignment, data.outcomes)} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} onReplay={onReplay} />
          <button className="btn-cyan" onClick={() => onView("work")}>Open Work</button>
        </div>
      )}

      {node.type === "proposal-queue" && (
        <div className="canvas-inspector-section">
          <Field label="pending" value={data.pending.length} />
          <Field label="highest visible risk" value={text(data.pending[0]?.risk || data.pending[0]?.risk_level, "none")} />
          <RelationshipJumpRow relationships={relationships} onFocus={onFocus} onOpenProposal={onOpenProposal} />
          <button className="btn-cyan" onClick={() => onView("governance")}>Open Governance</button>
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
          <Field label="needs attention" value={workers.filter((worker) => displaySeverityForRuntime(worker) !== "Operational").map(workerId).join(", ") || "none"} />
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

function BriefingNode({ data, workers, onView }: { data: AppData; workers: Agent[]; onView: (view: View) => void }) {
  const actions = recommendedNextActions(data, workers);
  const activeMissions = data.missions.filter((mission) => text(mission.status, "") === "active").length;
  const blockedAssignments = data.assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked").length;
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="active missions" value={activeMissions} />
        <Field label="blocked assignments" value={blockedAssignments} />
        <Field label="pending proposals" value={data.pending.length} />
        <Field label="actions" value={actions.length} />
      </div>
      <div className="mini-list">
        {actions.slice(0, 3).map((action) => (
          <div className="canvas-mini-row" key={action.label}>
            <span>{action.label}</span>
            <span>{action.targetView}</span>
          </div>
        ))}
        {!actions.length && <span className="text-xs text-muted">No operator action required by current records.</span>}
      </div>
      <button className="btn-cyan" onClick={() => onView("briefing")}>Open Briefing</button>
    </div>
  );
}

function WorkforceSummaryNode({ data, workers, daemonStatus }: { data: AppData; workers: Agent[]; daemonStatus: DaemonStatus }) {
  const summary = summariseWorkforceState(workers, data.pending, data.deadLetters, daemonStatus);
  const presence = data.workforcePresence?.summary;
  return (
    <div className="node-grid">
      <Field label="daemon" value={daemonStatus === "offline" ? "offline" : text(data.health?.status, daemonStatus)} />
      <Field label="workers" value={workers.length} />
      <Field label="state" value={daemonStatus === "offline" ? "Offline" : Number(presence?.needs_attention ?? summary.needsAttention.length) ? "Usable with issues" : "Usable"} />
      <Field label="active" value={Number(presence?.active ?? 0)} />
      <Field label="idle" value={Number(presence?.idle ?? 0)} />
      <Field label="needs attention" value={Number(presence?.needs_attention ?? summary.needsAttention.length)} />
      <Field label="watching" value={Number(presence?.watching ?? 0)} />
      <Field label="pending proposals" value={data.pending.length} />
      <Field label="dead letters" value={data.deadLetters.length} />
    </div>
  );
}

function RuntimeNode({ node, data, workers, onView }: { node: CanvasNode; data: AppData; workers: Agent[]; onView: (view: View) => void }) {
  const worker = workers.find((item) => workerId(item) === node.refId);
  if (!worker) return <EmptyPanel label="Runtime not returned by daemon." />;
  const reputation = workerReputation(worker);
  const presence = presenceForWorker(worker, data.workforcePresence);
  const severity = humanHealthFromPresence(presence, worker);
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="presence" value={presenceLabel(presence?.presence_state)} />
        <Field label="last" value={text(presence?.latest_activity_summary, "No recent activity recorded.")} />
        <Field label="idle for" value={formatIdle(presence?.idle_for_seconds)} />
        <Field label="room" value={presence?.current_room ? `#${presence.current_room}` : "None"} />
        <Field label="health" value={severity} />
        <Field label="trust" value={percent(presence?.trust_score ?? reputation.trust_score ?? worker.trust_score ?? worker.trust)} />
        <Field label="raw health" value={workerHealth(worker)} />
        <Field label="action" value={text(presence?.suggested_action, suggestedRuntimeAction(worker))} />
        {presence?.attention_reason && <Field label="attention" value={presence.attention_reason} />}
      </div>
      <button className="btn-cyan" onClick={() => onView("workforce")}>Focus Runtime Detail</button>
    </div>
  );
}

function RoomNode({ node, data, selectedRoom, onSelectRoom, onView, onRoomQuickMessage, onAddAllWorkers }: { node: CanvasNode; data: AppData; selectedRoom: string; onSelectRoom: (room: string) => void; onView: (view: View) => void; onRoomQuickMessage: (room: string, value: string) => void; onAddAllWorkers: () => void }) {
  const roomName = node.refId || selectedRoom;
  const room = data.rooms.find((item) => item.name === roomName);
  const roomProposals = data.proposals.filter((proposal) => text(proposal.room_id || proposal.room, "") === roomName);
  const latestReplies = data.recentActivity.filter((item) => text(item.room || item.room_id, "") === roomName || text(item.summary, "").includes(`#${roomName}`)).slice(0, 2);
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="room" value={`#${roomName}`} />
        <Field label="members" value={room?.member_count ?? 0} />
        <Field label="latest replies" value={latestReplies.length || "open chat"} />
        <Field label="last activity" value={shortDate(room?.last_activity)} />
      </div>
      <div className="mini-list">
        {latestReplies.map((item) => (
          <div className="mini-row" key={item.activity_id || `${item.runtime}-${item.timestamp}`}>
            <span>{text(item.runtime || item.actor, "activity")}</span>
            <span>{shortDate(item.timestamp)}</span>
          </div>
        ))}
        {!latestReplies.length && <span className="text-xs text-muted">No latest replies returned.</span>}
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="btn-cyan" onClick={() => { onSelectRoom(roomName); onView("conversations"); }}>Open Chat</button>
        <button className="btn" onClick={() => onRoomQuickMessage(roomName, "@everyone Who is available?")}>@everyone</button>
        <button className="btn" onClick={() => { onSelectRoom(roomName); onAddAllWorkers(); }}>Add Workers</button>
        <button className="btn" onClick={() => { onSelectRoom(roomName); onView("conversations"); }}>Show Members</button>
        <span className="pill status-warn">{roomProposals.length} proposals</span>
      </div>
    </div>
  );
}

function MissionNode({ node, data, onView }: { node: CanvasNode; data: AppData; onView: (view: View) => void }) {
  const mission = data.missions.find((item) => missionId(item) === node.refId) || data.missions[0];
  if (!mission) return <EmptyPanel label="No mission returned by daemon." />;
  const openProposals = (mission.proposals || []).filter((proposal) => text(proposal.status, "") === "proposed").length;
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="mission" value={missionTitle(mission)} />
        <Field label="status" value={mission.status} />
        <Field label="priority" value={mission.priority} />
        <Field label="workers" value={(mission.workers || []).length} />
        <Field label="rooms" value={(mission.rooms || []).length} />
        <Field label="open proposals" value={openProposals} />
        <Field label="incidents" value={(mission.incidents || []).length} />
        <Field label="risk" value={mission.risk_level || "medium"} />
      </div>
      <p className="line-clamp-node text-sm text-slate-200">{text((mission.activity || [])[0]?.summary || mission.goal, "No recent mission activity recorded.")}</p>
      <button className="btn-cyan" onClick={() => onView("work")}>Open Work</button>
    </div>
  );
}

function OutcomeNode({ node, data, onView }: { node: CanvasNode; data: AppData; onView: (view: View) => void }) {
  const outcome = data.outcomes.find((item) => outcomeId(item) === node.refId) || data.outcomes[0];
  if (!outcome) return <EmptyPanel label="No outcome returned by daemon." />;
  const openProposals = (outcome.proposals || []).filter((proposal) => text(proposal.status, "") === "proposed").length;
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="outcome" value={outcomeTitle(outcome)} />
        <Field label="mission" value={outcome.mission_title || outcome.mission_id} />
        <Field label="status" value={outcome.status} />
        <Field label="confidence" value={outcome.confidence} />
        <Field label="workers" value={(outcome.workers || []).length} />
        <Field label="evidence" value={outcome.evidence_count ?? (outcome.traces || []).length} />
        <Field label="open proposals" value={openProposals} />
        <Field label="incidents" value={(outcome.incidents || []).length} />
      </div>
      <p className="line-clamp-node text-sm text-slate-200">{text((outcome.activity || [])[0]?.summary || outcome.description, "No recent outcome activity recorded.")}</p>
      <button className="btn-cyan" onClick={() => onView("work")}>Open Work</button>
    </div>
  );
}

function AssignmentNode({ node, data, onView }: { node: CanvasNode; data: AppData; onView: (view: View) => void }) {
  const assignment = data.assignments.find((item) => assignmentId(item) === node.refId) || data.assignments[0];
  if (!assignment) return <EmptyPanel label="No assignment returned by daemon." />;
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="assignment" value={assignmentTitle(assignment)} />
        <Field label="status" value={assignmentStatusLabel(assignment.status)} />
        <Field label="owner" value={assignment.owner_worker || "Unassigned"} />
        <Field label="contributors" value={(assignment.contributor_workers || []).length} />
        <Field label="mission" value={assignmentMissionTitle(assignment, data.missions)} />
        <Field label="outcome" value={assignmentOutcomeTitle(assignment, data.outcomes)} />
        <Field label="room" value={assignment.room_id ? `#${assignment.room_id}` : "None"} />
        <Field label="handoffs" value={(assignment.handoffs || []).length} />
      </div>
      <p className="line-clamp-node text-sm text-slate-200">{text(assignment.description, "No assignment description recorded.")}</p>
      <button className="btn-cyan" onClick={() => onView("work")}>Open Work</button>
    </div>
  );
}

function MemoryNode({ node, data, onView }: { node: CanvasNode; data: AppData; onView: (view: View) => void }) {
  const memory = data.memories.find((item) => memoryId(item) === node.refId);
  const approved = data.memories.filter((item) => item.status === "approved");
  const pending = data.memories.filter((item) => item.status === "proposed");
  const rejected = data.memories.filter((item) => item.status === "rejected");
  const archived = data.memories.filter((item) => item.status === "archived");
  return (
    <div className="space-y-3">
      <div className="node-grid">
        <Field label="approved" value={approved.length} />
        <Field label="pending" value={pending.length} />
        <Field label="rejected" value={rejected.length} />
        <Field label="archived" value={archived.length} />
      </div>
      {memory ? (
        <div className="mini-list">
          <div className="mini-row"><span>{text(memory.title, memoryId(memory))}</span><span>{text(memory.status, "proposed")}</span></div>
          <p className="line-clamp-node text-sm text-slate-200">{memoryBody(memory)}</p>
        </div>
      ) : (
        <div className="mini-list">
          {approved.slice(0, 4).map((item) => <div className="mini-row" key={memoryId(item)}><span>{text(item.title, memoryId(item))}</span><span>{text(item.scope_type, "global")}</span></div>)}
          {!approved.length && <span className="text-sm text-muted">No approved memory.</span>}
        </div>
      )}
      <button className="btn-cyan" onClick={() => onView("knowledge")}>Open Knowledge</button>
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
      <button className="btn mt-2" onClick={() => onView("governance")}>Open Governance</button>
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
  const attention = workers.filter((worker) => displaySeverityForRuntime(worker) !== "Operational");
  const latest = asRecord(data.deadLetters[0]);
  const traceId = text(latest.message_id || latest.conversation_id || latest.dead_letter_id, "");
  return (
    <div className="space-y-3">
      <Field label="summary" value={traceId || text(asRecord(data.incident?.incident).summary, "No incident returned.")} />
      <Field label="needs attention" value={attention.map(workerId).join(", ") || "none"} />
      <Field label="recommended action" value={attention.length ? "Inspect affected runtime only if it is in current work." : "Monitor workforce health."} />
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
            <span className="text-amberop">{text(record.reason || record.error || record.status, "failed")}</span>
            {id && <button className="micro-btn" onClick={() => onReplay(id)}>replay</button>}
          </div>
        );
      })}
      {!data.deadLetters.length && <EmptyPanel label="No dead letters returned." />}
    </div>
  );
}

function ActivityFeedNode({ data, onReplay, onView }: { data: AppData; onReplay: (id: string) => void; onView: (view: View) => void }) {
  const activity = data.recentActivity.length ? data.recentActivity : data.workforcePresence?.recent_activity || [];
  return (
    <div className="mini-list activity-feed-node">
      {activity.slice(0, 8).map((item, index) => {
        const traceId = text(item.trace_id || item.proposal_id || item.activity_id, "");
        return (
          <div className={`activity-row activity-${text(item.severity, "info")}`} key={text(item.activity_id || index, String(index))}>
            <div>
              <strong>{text(item.summary, "Activity recorded.")}</strong>
              <span>{shortDate(item.timestamp)} · {activityEventType(item)}</span>
            </div>
            {traceId && <button className="micro-btn" onClick={() => onReplay(traceId)}>trace</button>}
          </div>
        );
      })}
      {!activity.length && <EmptyPanel label="No recent activity recorded." />}
      <button className="btn mt-2" onClick={() => onView("search")}>Open Search</button>
    </div>
  );
}

function BriefingView({ data, workers, onView, onReplay }: { data: AppData; workers: Agent[]; onView: (view: View) => void; onReplay: (id: string) => void }) {
  const workerStatuses = workers.map((worker) => operatorWorkerStatus(worker, presenceForWorker(worker, data.workforcePresence)));
  const activeMissions = data.missions.filter((mission) => text(mission.status, "") === "active");
  const completedMissions = data.missions.filter((mission) => text(mission.status, "") === "completed");
  const atRiskMissions = data.missions.filter((mission) => missionHealth(mission, data.assignments, data.recentActivity) === "At Risk");
  const openOutcomes = data.outcomes.filter((outcome) => !["completed", "cancelled"].includes(text(outcome.status, "")));
  const completedOutcomes = data.outcomes.filter((outcome) => text(outcome.status, "") === "completed");
  const blockedOutcomes = data.outcomes.filter((outcome) => outcomeHealth(outcome, data.assignments) === "Blocked");
  const assignedAssignments = data.assignments.filter((assignment) => assignmentHealth(assignment) === "Assigned");
  const inProgressAssignments = data.assignments.filter((assignment) => assignmentHealth(assignment) === "In Progress");
  const waitingAssignments = data.assignments.filter((assignment) => assignmentHealth(assignment) === "Waiting");
  const blockedAssignments = data.assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked");
  const actions = recommendedNextActions(data, workers);
  const activity = meaningfulActivity(data).slice(0, 8);
  const criticalIncident = asRecord(data.deadLetters[0]);

  return (
    <div className="briefing-screen">
      <SectionHeader title="Operational Briefing" subtitle="Deterministic briefing over active work, blockers, changes, and operator review." />
      <section className="briefing-hero">
        <div>
          <h2>Recommended Next Actions</h2>
          <p>Prioritized from proposals, blocked work, ownership gaps, incidents, and stale waiting assignments.</p>
        </div>
        <button className="btn" onClick={() => onView("search")}>Open Search</button>
      </section>
      <div className="briefing-actions">
        {actions.map((action) => (
          <button className="briefing-action" key={`${action.priority}-${action.label}`} onClick={() => onView(action.targetView)}>
            <span>{action.label}</span>
            <small>{action.detail}</small>
          </button>
        ))}
        {!actions.length && <EmptyPanel label="No operator action required by current daemon records." />}
      </div>

      <div className="briefing-grid">
        <Panel title="Workforce Snapshot">
          <div className="snapshot-grid">
            <Metric label="Available" value={workerStatuses.filter((status) => status === "Available").length} />
            <Metric label="Monitor" value={workerStatuses.filter((status) => status === "Monitor").length} />
            <Metric label="Avoid" value={workerStatuses.filter((status) => status === "Avoid for now").length} />
            <Metric label="Unavailable" value={workerStatuses.filter((status) => status === "Unavailable").length} />
          </div>
        </Panel>
        <Panel title="Mission Snapshot">
          <div className="snapshot-grid">
            <Metric label="Active missions" value={activeMissions.length} />
            <Metric label="Completed missions" value={completedMissions.length} />
            <Metric label="At-risk missions" value={atRiskMissions.length} />
          </div>
          <HealthList items={data.missions.slice(0, 5).map((mission) => ({ title: missionTitle(mission), health: missionHealth(mission, data.assignments, data.recentActivity), detail: text(mission.status, "unknown") }))} />
        </Panel>
        <Panel title="Outcome Snapshot">
          <div className="snapshot-grid">
            <Metric label="Open outcomes" value={openOutcomes.length} />
            <Metric label="Completed outcomes" value={completedOutcomes.length} />
            <Metric label="Blocked outcomes" value={blockedOutcomes.length} />
          </div>
          <HealthList items={data.outcomes.slice(0, 5).map((outcome) => ({ title: outcomeTitle(outcome), health: outcomeHealth(outcome, data.assignments), detail: text(outcome.status, "unknown") }))} />
        </Panel>
        <Panel title="Assignment Snapshot">
          <div className="snapshot-grid">
            <Metric label="Assigned" value={assignedAssignments.length} />
            <Metric label="In progress" value={inProgressAssignments.length} />
            <Metric label="Waiting" value={waitingAssignments.length} />
            <Metric label="Blocked" value={blockedAssignments.length} />
          </div>
          <HealthList items={data.assignments.slice(0, 5).map((assignment) => ({ title: assignmentTitle(assignment), health: assignmentHealth(assignment), detail: text(assignment.owner_worker, "No owner") }))} />
        </Panel>
        <Panel title="Recent Activity">
          <div className="mini-list">
            {activity.map((item, index) => {
              const traceId = text(item.trace_id || item.proposal_id || item.activity_id, "");
              return (
                <div className="mini-row" key={text(item.activity_id || index, String(index))}>
                  <span>{text(item.summary, "Activity recorded.")}</span>
                  {traceId ? <button className="micro-btn" onClick={() => onReplay(traceId)}>trace</button> : <span>{shortDate(item.timestamp)}</span>}
                </div>
              );
            })}
            {!activity.length && <span className="text-sm text-muted">No recent activity records returned.</span>}
          </div>
        </Panel>
        <Panel title="Needs Operator Review">
          <div className="snapshot-grid">
            <Metric label="Proposal approvals" value={data.pending.length} />
            <Metric label="Blocked assignments" value={blockedAssignments.length} />
            <Metric label="Critical incidents" value={data.deadLetters.length ? 1 : 0} />
          </div>
          <div className="mini-list mt-3">
            {data.pending.slice(0, 3).map((proposal) => (
              <button className="mini-row" key={proposalId(proposal)} onClick={() => onView("proposals")}>
                <span>{text(proposal.title || proposal.summary, proposalId(proposal))}</span>
                <span>{text(proposal.risk || proposal.risk_level, "risk")}</span>
              </button>
            ))}
            {blockedAssignments.slice(0, 3).map((assignment) => (
              <button className="mini-row" key={assignmentId(assignment)} onClick={() => onView("assignments")}>
                <span>{assignmentTitle(assignment)}</span>
                <span>{assignment.owner_worker || "No owner"}</span>
              </button>
            ))}
            {data.deadLetters.length > 0 && (
              <button className="mini-row" onClick={() => onView("incidents")}>
                <span>{text(criticalIncident.reason || criticalIncident.error || criticalIncident.status, "Latest incident")}</span>
                <span>{text(criticalIncident.adapter_id || criticalIncident.target || criticalIncident.source, "runtime")}</span>
              </button>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function HealthList({ items }: { items: { title: string; health: string; detail: string }[] }) {
  return (
    <div className="health-list">
      {items.map((item) => (
        <div className="health-row" key={`${item.title}-${item.health}`}>
          <span>{item.title}</span>
          <span className={`pill ${statusClass(item.health)}`}>{item.health}</span>
          <small>{item.detail}</small>
        </div>
      ))}
      {!items.length && <span className="text-sm text-muted">No records returned.</span>}
    </div>
  );
}

function dayGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function workerBriefingLines(data: AppData, workers: Agent[]): string[] {
  const activity = meaningfulActivity(data);
  const lines = activity
    .map((item) => {
      const runtime = activityRuntime(item);
      const room = activityRoom(item);
      const summary = text(item.summary, "");
      if (!runtime && !summary) return "";
      if (summary.toLowerCase().includes("timeout")) return `${runtime || "A worker"} timed out${room ? ` in #${room}` : ""}.`;
      if (summary.toLowerCase().includes("replied") || activityEventType(item).includes("reply")) return `${runtime || "A worker"} replied${room ? ` in #${room}` : ""} ${shortDate(item.timestamp)}.`;
      return summary || `${runtime || "SynKraken"} recorded activity ${shortDate(item.timestamp)}.`;
    })
    .filter(Boolean)
    .slice(0, 3);
  if (lines.length) return lines;
  return workers.slice(0, 3).map((worker) => `${workerId(worker)} is ${operatorWorkerStatus(worker, presenceForWorker(worker, data.workforcePresence)).toLowerCase()}.`);
}

function homeNeeds(data: AppData, workers: Agent[], daemonStatus: DaemonStatus): string[] {
  const needs: string[] = [];
  if (daemonStatus === "offline") needs.push("Reconnect the daemon before dispatching work.");
  if (data.pending.length) needs.push(`${data.pending.length} approval${data.pending.length === 1 ? "" : "s"} awaiting review.`);
  const pendingMemory = data.memories.filter((memory) => text(memory.status, "") === "proposed").length;
  if (pendingMemory) needs.push(`${pendingMemory} knowledge item${pendingMemory === 1 ? "" : "s"} awaiting review.`);
  const blocked = data.assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked").length;
  if (blocked) needs.push(`${blocked} blocked assignment${blocked === 1 ? "" : "s"} need a decision.`);
  const attentionWorkers = workers.filter((worker) => operatorWorkerStatus(worker, presenceForWorker(worker, data.workforcePresence)) !== "Available").length;
  if (attentionWorkers) needs.push(`${attentionWorkers} worker${attentionWorkers === 1 ? "" : "s"} need watching.`);
  return needs.slice(0, 4);
}

function projectBriefingLines(projects: ProjectRecord[], data: AppData): string[] {
  return projects.slice(0, 3).map((project) => {
    const recommendation = projectRecommendations(project, data)[0];
    const health = projectHealth(project, data).toLowerCase();
    if (recommendation) return `${projectTitle(project)}: ${recommendation.title}.`;
    return `${projectTitle(project)} is ${health}.`;
  });
}

function HomeView({ data, projects, workers, daemonStatus, onView, onProjectTarget, onReplay }: { data: AppData; projects: ProjectRecord[]; workers: Agent[]; daemonStatus: DaemonStatus; onView: (view: View) => void; onProjectTarget: (target: ProjectTarget) => void; onReplay: (id: string) => void }) {
  const actions = recommendedNextActions(data, workers);
  const activeAssignments = data.assignments.filter((assignment) => ["assigned", "in_progress", "waiting", "review"].includes(text(assignment.status, ""))).slice(0, 5);
  const activeMissions = data.missions.filter((mission) => ["active", "review", "blocked"].includes(text(mission.status, ""))).slice(0, 4);
  const rooms = data.rooms.slice(0, 5);
  const attentionWorkers = workers.filter((worker) => operatorWorkerStatus(worker, presenceForWorker(worker, data.workforcePresence)) !== "Available").slice(0, 5);
  const activity = meaningfulActivity(data).slice(0, 5);
  const briefingLines = projects.length ? projectBriefingLines(projects, data) : workerBriefingLines(data, workers);
  const needs = homeNeeds(data, workers, daemonStatus);
  const projectActions = projects.flatMap((project) => projectRecommendations(project, data).map((recommendation) => ({ project, recommendation })));
  const primaryProjectAction = projectActions[0];
  const primaryAction = actions[0];
  const activeProject = projects.find((project) => text(project.status, "") === "active") || projects[0];
  return (
    <div className="home-screen living-home space-y-8">
      <section className="home-hero workforce-briefing">
        <div>
          <p className="eyebrow">Company Briefing</p>
          <h1>{dayGreeting()} Howard.</h1>
          <div className="briefing-lines">
            {activeProject && <p>{projectTitle(activeProject)} is {text(activeProject.status, "active")}.</p>}
            {briefingLines.map((line) => <p key={line}>{line}</p>)}
          </div>
        </div>
        <button className="btn-cyan" onClick={() => onView("projects")}>Open Projects</button>
      </section>

      <section className="briefing-answer-grid" data-screen-answers="what happened, what matters, what should I do next">
        <article className="briefing-answer">
          <div className="section-kicker">What happened?</div>
          <div className="activity-card-list">
            {activity.slice(0, 4).map((item, index) => {
              const traceId = text(item.trace_id || item.proposal_id || item.activity_id, "");
              return (
                <article className="activity-card" key={text(item.activity_id || index, String(index))}>
                  <div><strong>{text(item.summary, "Activity recorded.")}</strong><span>{shortDate(item.timestamp)} · {activityEventType(item)}</span></div>
                  {traceId && <button className="text-link" onClick={() => onReplay(traceId)}>Replay</button>}
                </article>
              );
            })}
            {!activity.length && <p className="quiet-copy">No recent workforce activity has been recorded.</p>}
          </div>
        </article>
        <article className="briefing-answer">
          <div className="section-kicker">What needs me?</div>
          <div className="chief-list">
            {needs.map((need) => <div className="chief-line" key={need}>{need}</div>)}
            {!needs.length && <p className="quiet-copy">Nothing is waiting for operator judgement right now.</p>}
          </div>
        </article>
        <article className="briefing-answer primary-next-action">
          <div className="section-kicker">Recommended next action</div>
          {primaryProjectAction ? (
            <button className="next-action-card" onClick={() => onProjectTarget({ projectId: projectId(primaryProjectAction.project), tab: primaryProjectAction.recommendation.tab, roomId: primaryProjectAction.project.room_id })}>
              <span>{primaryProjectAction.recommendation.action}</span>
              <small>{projectTitle(primaryProjectAction.project)}: {primaryProjectAction.recommendation.why}</small>
            </button>
          ) : primaryAction ? (
            <button className="next-action-card" onClick={() => ["proposals", "assignments", "missions", "outcomes", "work", "governance"].includes(primaryAction.targetView) ? onProjectTarget(projectForAction(primaryAction, projects, data)) : onView(primaryAction.targetView)}>
              <span>{primaryAction.label}</span>
              <small>{primaryAction.detail}</small>
            </button>
          ) : (
            <button className="next-action-card" onClick={() => onView(projects.length ? "projects" : "projects")}>
              <span>{projects.length ? "Continue the active project" : "Create a project"}</span>
              <small>{projects.length ? "No urgent action is waiting. Continue in the project workspace." : "Create a project to organise workforce activity."}</small>
            </button>
          )}
        </article>
      </section>

      <section className="home-grid contextual-home-grid">
        <article className="home-card home-card-large">
          <div className="section-kicker">Project recommendations</div>
          <div className="action-list">
            {projectActions.slice(1, 5).map(({ project, recommendation }) => (
              <button className="action-card" key={`${projectId(project)}-${recommendation.title}`} onClick={() => onProjectTarget({ projectId: projectId(project), tab: recommendation.tab, roomId: project.room_id })}>
                <span>{recommendation.title}</span>
                <small>{projectTitle(project)} · {recommendation.action}</small>
              </button>
            ))}
            {!projectActions.slice(1, 5).length && actions.slice(1, 5).map((action) => (
              <button className="action-card" key={`${action.priority}-${action.label}`} onClick={() => ["proposals", "assignments", "missions", "outcomes", "work", "governance"].includes(action.targetView) ? onProjectTarget(projectForAction(action, projects, data)) : onView(action.targetView)}>
                <span>{action.label}</span>
                <small>{action.detail}</small>
              </button>
            ))}
            {!projectActions.slice(1, 5).length && actions.length <= 1 && <p className="quiet-copy">No recommendations right now. Your active projects appear healthy.</p>}
          </div>
        </article>

        <article className="home-card">
          <div className="section-kicker">Pending approval</div>
          <div className="mini-list">
            {data.pending.slice(0, 4).map((proposal) => <button className="mini-row" key={proposalId(proposal)} onClick={() => onProjectTarget(projectForAction({ priority: 10, label: "Review proposal", detail: "", targetView: "proposals", refId: proposalId(proposal) }, projects, data))}><span>{text(proposal.title || proposal.summary, proposalId(proposal))}</span><span>{text(proposal.risk || proposal.risk_level, "risk")}</span></button>)}
            {!data.pending.length && <p className="quiet-copy">No approvals waiting.</p>}
          </div>
        </article>
      </section>

      <section className="home-grid">
        <article className="home-card">
          <div className="section-kicker">Active work</div>
          <div className="mini-list">
            {activeAssignments.map((assignment) => <button className="mini-row" key={assignmentId(assignment)} onClick={() => onProjectTarget(projectForAction({ priority: 7, label: "Open project work", detail: "", targetView: "assignments", refId: assignmentId(assignment) }, projects, data))}><span>{assignmentTitle(assignment)}</span><span>{assignment.owner_worker || assignmentStatusLabel(assignment.status)}</span></button>)}
            {activeMissions.map((mission) => <button className="mini-row" key={missionId(mission)} onClick={() => onProjectTarget(projectForAction({ priority: 7, label: "Open project", detail: "", targetView: "missions", refId: missionId(mission) }, projects, data))}><span>{missionTitle(mission)}</span><span>{text(mission.status, "active")}</span></button>)}
            {!activeAssignments.length && !activeMissions.length && <p className="quiet-copy">No active project work yet. Create a project, start a conversation, or ask the workforce for a deliverable.</p>}
          </div>
        </article>

        <article className="home-card">
          <div className="section-kicker">Active Projects</div>
          <div className="project-card-list">
            {projects.slice(0, 4).map((project) => {
              const action = projectRecommendedAction(project, data);
              return (
                <button className="home-project-card" key={projectId(project)} onClick={() => onProjectTarget({ projectId: projectId(project), tab: action.tab, roomId: project.room_id })}>
                  <strong>{projectTitle(project)}</strong>
                  <span>{projectHealth(project, data)} · {projectCurrentFocus(project, data)}</span>
                  <small>{action.label}</small>
                </button>
              );
            })}
            {!projects.length && <p className="quiet-copy">No active projects. Create a project to organise workforce activity.</p>}
          </div>
        </article>

        <article className="home-card">
          <div className="section-kicker">Workers to monitor</div>
          <div className="mini-list">
            {attentionWorkers.map((worker) => {
              const presence = presenceForWorker(worker, data.workforcePresence);
              return <button className="mini-row" key={workerId(worker)} onClick={() => onView("workforce")}><span>{workerId(worker)}</span><span>{operatorWorkerStatus(worker, presence)}</span></button>;
            })}
            {!attentionWorkers.length && <p className="quiet-copy">All available workers look usable.</p>}
          </div>
        </article>
      </section>

      <details className="home-card diagnostics-disclosure">
        <summary>Diagnostics and activity details</summary>
        <div className="section-kicker">Recent replies and activity</div>
        <div className="activity-card-list">
          {activity.map((item, index) => {
            const traceId = text(item.trace_id || item.proposal_id || item.activity_id, "");
            return (
              <article className="activity-card" key={text(item.activity_id || index, String(index))}>
                <div><strong>{text(item.summary, "Activity recorded.")}</strong><span>{shortDate(item.timestamp)} · {activityEventType(item)}</span></div>
                {traceId && <button className="text-link" onClick={() => onReplay(traceId)}>Replay</button>}
              </article>
            );
          })}
          {!activity.length && <p className="quiet-copy">No recent activity recorded.</p>}
        </div>
      </details>
    </div>
  );
}

function ProjectsView({
  data,
  workers,
  projects,
  selectedProjectId,
  tab,
  titleInput,
  purposeInput,
  knowledgeDraft,
  roomDetail,
  roomMessage,
  sending,
  onSelectProject,
  onTab,
  onTitleInput,
  onPurposeInput,
  onKnowledgeDraft,
  onCreateKnowledge,
  onCreate,
  onMessage,
  onSend,
  onOpenConversation,
  onOpenProposal,
  onReplay,
}: {
  data: AppData;
  workers: Agent[];
  projects: ProjectRecord[];
  selectedProjectId: string | null;
  tab: ProjectTab;
  titleInput: string;
  purposeInput: string;
  knowledgeDraft: ProjectKnowledgeDraft;
  roomDetail: RoomDetail;
  roomMessage: string;
  sending: boolean;
  onSelectProject: (id: string) => void;
  onTab: (tab: ProjectTab) => void;
  onTitleInput: (value: string) => void;
  onPurposeInput: (value: string) => void;
  onKnowledgeDraft: (draft: ProjectKnowledgeDraft) => void;
  onCreateKnowledge: (project: ProjectRecord) => void;
  onCreate: () => void;
  onMessage: (value: string) => void;
  onSend: () => void;
  onOpenConversation: (room: string) => void;
  onOpenProposal: (id: string) => void;
  onReplay: (id: string) => void;
}) {
  const selected = projects.find((project) => projectId(project) === selectedProjectId) || projects[0] || null;
  if (!projects.length) {
    return (
      <div className="projects-screen">
        <SectionHeader title="Projects" subtitle="Organise conversations, knowledge, deliverables, workers, and decisions around company work." />
        <ExperienceEmptyState title="No active projects." body="Create a project to organise workforce activity." action="Create Project" />
        <ProjectCreatePanel titleInput={titleInput} purposeInput={purposeInput} onTitleInput={onTitleInput} onPurposeInput={onPurposeInput} onCreate={onCreate} />
      </div>
    );
  }
  return (
    <div className="projects-screen">
      <SectionHeader title="Projects" subtitle="Company workspaces powered by the AI workforce." />
      <div className="project-workspace">
        <aside className="project-list">
          <ProjectCreatePanel titleInput={titleInput} purposeInput={purposeInput} onTitleInput={onTitleInput} onPurposeInput={onPurposeInput} onCreate={onCreate} compact />
          {projects.map((project) => (
            <button className={`project-list-item ${selected && projectId(selected) === projectId(project) ? "project-list-item-active" : ""}`} key={projectId(project)} onClick={() => onSelectProject(projectId(project))}>
              <strong>{projectTitle(project)}</strong>
              <span>{projectCurrentFocus(project, data)}</span>
              <small>{projectRecommendedAction(project, data).label}</small>
            </button>
          ))}
        </aside>
        {selected && (
          <main className="project-detail">
            <header className="project-header">
              <div>
                <p className="eyebrow">Project</p>
                <h2>{projectTitle(selected)}</h2>
                <p>{text(selected.purpose, "No purpose recorded yet.")}</p>
              </div>
              <button className="btn" onClick={() => selected.room_id && onOpenConversation(selected.room_id)}>Open full conversation</button>
            </header>
            <div className="project-tabs">
              {(["overview", "conversations", "knowledge", "deliverables", "team", "decisions"] as ProjectTab[]).map((item) => (
                <button className={`seg ${tab === item ? "seg-active" : ""}`} key={item} onClick={() => onTab(item)}>{item[0].toUpperCase() + item.slice(1)}</button>
              ))}
            </div>
            {tab === "overview" && <ProjectOverview project={selected} data={data} workers={workers} onTab={onTab} onOpenProposal={onOpenProposal} />}
            {tab === "conversations" && <ProjectConversations project={selected} roomDetail={roomDetail} message={roomMessage} sending={sending} onMessage={onMessage} onSend={onSend} />}
            {tab === "knowledge" && <ProjectKnowledge project={selected} data={data} draft={knowledgeDraft} onDraft={onKnowledgeDraft} onCreate={() => onCreateKnowledge(selected)} />}
            {tab === "deliverables" && <ProjectDeliverables project={selected} data={data} onOpenProposal={onOpenProposal} />}
            {tab === "team" && <ProjectTeam project={selected} data={data} workers={workers} />}
            {tab === "decisions" && <ProjectDecisions project={selected} data={data} onOpenProposal={onOpenProposal} onReplay={onReplay} />}
          </main>
        )}
      </div>
    </div>
  );
}

function ProjectCreatePanel({ titleInput, purposeInput, compact = false, onTitleInput, onPurposeInput, onCreate }: { titleInput: string; purposeInput: string; compact?: boolean; onTitleInput: (value: string) => void; onPurposeInput: (value: string) => void; onCreate: () => void }) {
  return (
    <section className={`project-create-panel ${compact ? "project-create-panel-compact" : ""}`}>
      {!compact && <div className="section-kicker">Create Project</div>}
      <input className="input" value={titleInput} onChange={(event) => onTitleInput(event.target.value)} placeholder="Project name" />
      <textarea className="textarea" value={purposeInput} onChange={(event) => onPurposeInput(event.target.value)} placeholder="Purpose" />
      <button className="btn-cyan" onClick={onCreate}>Create Project</button>
    </section>
  );
}

function ProjectOverview({ project, data, workers, onTab, onOpenProposal }: { project: ProjectRecord; data: AppData; workers: Agent[]; onTab: (tab: ProjectTab) => void; onOpenProposal: (id: string) => void }) {
  const activity = projectActivity(project, data).slice(0, 6);
  const deliverables = projectDeliverables(project, data);
  const workerIds = projectWorkers(project, data, workers);
  const decisions = projectDecisions(project, data);
  const nextAction = projectRecommendedAction(project, data);
  return (
    <section className="project-tab-panel">
      <ProjectCoPilot project={project} data={data} onTab={onTab} onOpenProposal={onOpenProposal} />
      <article className="project-narrative">
        <div>
          <div className="section-kicker">Project Narrative</div>
          <h3>{projectTitle(project)}</h3>
        </div>
        <div className="project-narrative-fields">
          <Field label="Purpose" value={text(project.purpose, "No purpose recorded yet.")} />
          <Field label="Current focus" value={projectCurrentFocus(project, data)} />
          <Field label="Latest activity" value={projectLatestActivity(project, data)} />
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Recommended next action</div>
            <button className="project-next-action" onClick={() => nextAction.proposalId ? onOpenProposal(nextAction.proposalId) : onTab(nextAction.tab)}>
              <span>{nextAction.label}</span>
              <small>{nextAction.detail}</small>
            </button>
          </div>
        </div>
      </article>

      <section className="project-hero-deliverables">
        <div className="project-section-head">
          <div>
            <div className="section-kicker">Produced Work</div>
            <h3>Deliverables</h3>
          </div>
          <button className="text-link" onClick={() => onTab("deliverables")}>See all</button>
        </div>
        <div className="deliverable-hero-row">
          {deliverables.slice(0, 3).map((deliverable) => (
            <DeliverableCard deliverable={deliverable} onOpenProposal={onOpenProposal} key={deliverable.deliverable_id} />
          ))}
          {!deliverables.length && <ExperienceEmptyState title="Nothing has been produced yet." body="Ask the workforce to create a deliverable for this project." action="Start Conversation" />}
        </div>
      </section>

      <div className="project-overview-grid">
        <article className="project-soft-panel">
          <div className="section-kicker">Activity timeline</div>
          <div className="project-activity-feed">
            {activity.map((item, index) => <div className="project-activity-item" key={text(item.activity_id || index, String(index))}><span>{projectActivitySentence(item)}</span><small>{shortDate(item.timestamp)}</small></div>)}
            {!activity.length && <p className="quiet-copy">No project activity yet. Start the conversation or ask for the first deliverable.</p>}
          </div>
        </article>
        <article className="project-soft-panel">
          <div className="section-kicker">Decisions</div>
          <div className="mini-list">
            {decisions.pending.slice(0, 3).map((proposal) => <button className="mini-row" key={proposalId(proposal)} onClick={() => onOpenProposal(proposalId(proposal))}><span>{decisionTitle(proposal)}</span><span>Review</span></button>)}
            {!decisions.pending.length && <p className="quiet-copy">No project decisions are waiting.</p>}
          </div>
        </article>
        <article className="project-soft-panel">
          <div className="section-kicker">Team</div>
          <div className="mini-list">
            {workerIds.slice(0, 5).map((id) => <div className="mini-row" key={id}><span>{id}</span><span>{workerFocus(id, project, data)}</span></div>)}
            {!workerIds.length && <p className="quiet-copy">No workers are contributing yet. Invite them in the project conversation.</p>}
          </div>
        </article>
      </div>
    </section>
  );
}

function ProjectCoPilot({ project, data, onTab, onOpenProposal }: { project: ProjectRecord; data: AppData; onTab: (tab: ProjectTab) => void; onOpenProposal: (id: string) => void }) {
  const health = projectHealth(project, data);
  const recommendations = projectRecommendations(project, data);
  const inbox = projectInbox(project, data);
  return (
    <section className="project-copilot" data-project-copilot="deterministic project assistant, no AI generation">
      <div className="project-copilot-header">
        <div>
          <div className="section-kicker">Project Co-Pilot</div>
          <h3>{health}</h3>
          <p>{projectHealthDetail(project, data)}</p>
        </div>
        <button className="btn" onClick={() => onTab(recommendations[0]?.tab || "conversations")}>{recommendations[0]?.action || "Continue Project"}</button>
      </div>
      <div className="project-copilot-grid">
        <article className="project-copilot-panel">
          <div className="section-kicker">Recommended next actions</div>
          <div className="project-action-card-list">
            {recommendations.map((recommendation) => (
              <button className="project-action-card" key={recommendation.title} onClick={() => recommendation.proposalId ? onOpenProposal(recommendation.proposalId) : onTab(recommendation.tab)}>
                <strong>{recommendation.title}</strong>
                <span>Why: {recommendation.why}</span>
                <small>Suggested Action: {recommendation.action}</small>
              </button>
            ))}
            {!recommendations.length && <p className="quiet-copy">No recommendations right now. Your project appears healthy.</p>}
          </div>
        </article>
        <article className="project-copilot-panel">
          <div className="section-kicker">Inbox</div>
          <div className="project-inbox-list">
            {inbox.map((item) => (
              <button className="project-inbox-item" key={item.id} onClick={() => item.proposalId ? onOpenProposal(item.proposalId) : onTab(item.tab)}>
                <span>{item.title}</span>
                <small>{item.detail}{item.timestamp ? ` · ${shortDate(item.timestamp)}` : ""}</small>
              </button>
            ))}
            {!inbox.length && <p className="quiet-copy">No project events yet. Start a conversation or ask the workforce to create a deliverable.</p>}
          </div>
        </article>
      </div>
    </section>
  );
}

function ProjectConversations({ project, roomDetail, message, sending, onMessage, onSend }: { project: ProjectRecord; roomDetail: RoomDetail; message: string; sending: boolean; onMessage: (value: string) => void; onSend: () => void }) {
  const prompts = [
    "Ask @everyone for the next useful deliverable.",
    "Dispatch Claude to draft the current proposal.",
    "Ask Hermes to coordinate handoff and next steps.",
  ];
  return (
    <section className="project-conversation-surface">
      <div className="project-conversation-toolbar">
        {prompts.map((prompt) => <button className="micro-btn" key={prompt} onClick={() => onMessage(prompt)} type="button">{prompt}</button>)}
      </div>
      <div className="room-chat-transcript">
        {roomDetail.messages.map((item) => (
          <article className={`message-row chat-row ${text(item.source, "") === "operator" ? "chat-row-operator" : "chat-row-worker"}`} key={item.message_id || `${item.source}-${item.timestamp}`}>
            <div className="message-meta"><span>{text(item.source, "unknown")}</span><span>{shortDate(item.timestamp)}</span></div>
            <TokenText value={text(item.body, "[empty reply] - worker responded without text.")} />
          </article>
        ))}
        {!roomDetail.messages.length && <ExperienceEmptyState title="No project conversation yet." body="Start with a clear instruction or ask @everyone who is available for this project." action="Start Conversation" />}
      </div>
      <form className="room-chat-composer" onSubmit={(event) => { event.preventDefault(); onSend(); }}>
        <textarea className="textarea room-chat-input" value={message} onChange={(event) => onMessage(event.target.value)} placeholder={`Talk to the workforce about ${projectTitle(project)}. Use @everyone or @worker-id.`} disabled={sending} />
        <div className="composer-footer">
          <span>Project room: #{project.room_id || "unassigned"}</span>
          <button className="btn-cyan" type="submit" disabled={sending || !message.trim()}>{sending ? "Sending..." : "Send"}</button>
        </div>
      </form>
    </section>
  );
}

function ProjectKnowledge({ project, data, draft, onDraft, onCreate }: { project: ProjectRecord; data: AppData; draft: ProjectKnowledgeDraft; onDraft: (draft: ProjectKnowledgeDraft) => void; onCreate: () => void }) {
  const knowledge = projectKnowledge(project, data);
  return (
    <section className="project-knowledge-layout">
      <article className="project-note-editor">
        <div className="section-kicker">Project Notes</div>
        <input className="input" value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} placeholder="Knowledge title" />
        <textarea className="textarea" value={draft.body} onChange={(event) => onDraft({ ...draft, body: event.target.value })} placeholder={`Add or revise knowledge for ${projectTitle(project)}.`} />
        <div className="composer-footer">
          <select className="input" value={draft.importance} onChange={(event) => onDraft({ ...draft, importance: event.target.value })}>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="critical">Critical</option>
          </select>
          <button className="btn-cyan" onClick={onCreate} disabled={!draft.title.trim() || !draft.body.trim()}>Save Knowledge</button>
        </div>
      </article>
      <div className="knowledge-notes-grid">
        {["Positioning", "Requirements", "Architecture", "Research", "Lessons Learned"].map((section) => {
          const items = knowledge.filter((memory) => `${memory.title} ${memory.body} ${memory.memory_type}`.toLowerCase().includes(section.toLowerCase().split(" ")[0]));
          return <ProjectKnowledgeSection title={section} memories={items.length ? items : knowledge.filter((_, index) => index < 2 && section === "Requirements")} onRevise={(memory) => onDraft({ title: text(memory.title, memoryId(memory)), body: memoryBody(memory), importance: text(memory.importance, "high") })} key={section} />;
        })}
        {!knowledge.length && <ExperienceEmptyState title="No project knowledge yet." body="Teach the workforce project requirements, positioning, research, architecture, or lessons learned." action="Add Knowledge" />}
      </div>
    </section>
  );
}

function ProjectDeliverables({ project, data, onOpenProposal }: { project: ProjectRecord; data: AppData; onOpenProposal: (id: string) => void }) {
  const deliverables = projectDeliverables(project, data);
  return (
    <section className="deliverable-grid" data-deliverables="PRD, Research, Proposal, Architecture, Code Review, Article, Specification, Report">
      {deliverables.map((deliverable) => <DeliverableCard deliverable={deliverable} onOpenProposal={onOpenProposal} key={deliverable.deliverable_id} />)}
      {!deliverables.length && <ExperienceEmptyState title="Nothing has been produced yet." body="Ask the workforce to create a deliverable." action="Start Conversation" />}
    </section>
  );
}

function DeliverableCard({ deliverable, onOpenProposal }: { deliverable: DeliverableRecord; onOpenProposal: (id: string) => void }) {
  const canOpen = deliverable.source_type === "proposal" && Boolean(deliverable.source_id);
  return (
    <article className="deliverable-card">
      <span>{deliverable.deliverable_type}</span>
      <h3>{deliverable.title}</h3>
      <Field label="Status" value={deliverableStatusLabel(deliverable.status)} />
      <Field label="Owner" value={deliverable.owner || "No owner recorded"} />
      <Field label="Last updated" value={shortDate(deliverable.updated_at)} />
      <Field label="Open action" value={deliverableActionLabel(deliverable)} />
      <button className="text-link" type="button" disabled={!canOpen} onClick={() => canOpen && onOpenProposal(text(deliverable.source_id, ""))}>{deliverableActionLabel(deliverable)}</button>
    </article>
  );
}

function ProjectKnowledgeSection({ title, memories, onRevise }: { title: string; memories: WorkforceMemory[]; onRevise: (memory: WorkforceMemory) => void }) {
  return (
    <section className="memory-section project-memory-section">
      <div className="section-kicker">{title}</div>
      <div className="memory-card-list">
        {memories.slice(0, 4).map((memory) => (
          <article className="memory-card" key={memoryId(memory)}>
            <div>
              <h3>{text(memory.title, memoryId(memory))}</h3>
              <p>{memoryBody(memory)}</p>
              <small>{text(memory.status, "proposed")} · {text(memory.importance, "medium")}</small>
            </div>
            <button className="text-link" onClick={() => onRevise(memory)}>Revise</button>
          </article>
        ))}
        {!memories.length && <p className="quiet-copy">Nothing captured here yet.</p>}
      </div>
    </section>
  );
}

function ProjectTeam({ project, data, workers }: { project: ProjectRecord; data: AppData; workers: Agent[] }) {
  const workerIds = projectWorkers(project, data, workers);
  return (
    <section className="worker-card-grid">
      {workerIds.map((id) => {
        const worker = workers.find((item) => workerId(item) === id);
        const presence = presenceForRuntime(id, data.workforcePresence);
        return (
          <article className="worker-card" key={id}>
            <div className="worker-card-head"><span>{id}</span><span className={`pill status-${operatorWorkerTone(operatorWorkerStatus(worker, presence))}`}>{operatorWorkerStatus(worker, presence)}</span></div>
            <div className="worker-card-body">
              <Field label="Current contribution" value={workerFocus(id, project, data)} />
              <Field label="Last activity" value={projectWorkerLastActivity(id, project, data)} />
              <Field label="Suggested use" value={workerRecommendedUse(id, project, data)} />
            </div>
          </article>
        );
      })}
      {!workerIds.length && <ExperienceEmptyState title="No project team yet." body="Add workers by talking to them in the project conversation or assigning project work." action="Open Conversation" />}
    </section>
  );
}

function ProjectDecisions({ project, data, onOpenProposal, onReplay }: { project: ProjectRecord; data: AppData; onOpenProposal: (id: string) => void; onReplay: (id: string) => void }) {
  const decisions = projectDecisions(project, data);
  const handoffs = data.recentHandoffs.filter((handoff) => project.assignment_ids.includes(text(handoff.assignment_id, "")) || projectAssignments(project, data).some((assignment) => assignmentId(assignment) === handoff.assignment_id));
  return (
    <section className="home-grid">
      <DecisionSection title="Needs a decision" proposals={decisions.pending} onOpenProposal={onOpenProposal} />
      <DecisionSection title="Approved" proposals={decisions.approved} onOpenProposal={onOpenProposal} />
      <DecisionSection title="Rejected" proposals={decisions.rejected} onOpenProposal={onOpenProposal} />
      <article className="home-card">
        <div className="section-kicker">Recent handoffs</div>
        <div className="mini-list">
          {handoffs.map((handoff, index) => {
            const id = text(handoff.handoff_id || handoff.assignment_id || index, String(index));
            return <button className="mini-row" key={id} onClick={() => onReplay(id)}><span>{text(handoff.from_worker, "Worker")} handed work to {text(handoff.to_worker, "worker")}</span><span>{shortDate(handoff.timestamp || handoff.created_at)}</span></button>;
          })}
          {!handoffs.length && <p className="quiet-copy">No handoffs have happened in this project yet.</p>}
        </div>
      </article>
    </section>
  );
}

function AdvancedView({ data, onView }: { data: AppData; onView: (view: View) => void }) {
  const items: { title: string; detail: string; view: View; count?: number }[] = [
    { title: "Governance", detail: "Proposal internals, approvals, execution records.", view: "governance", count: data.proposals.length },
    { title: "Assignments", detail: "Implementation ownership and handoff internals.", view: "assignments", count: data.assignments.length },
    { title: "Outcomes", detail: "Outcome records behind project deliverables.", view: "outcomes", count: data.outcomes.length },
    { title: "Missions", detail: "Mission records behind projects.", view: "missions", count: data.missions.length },
    { title: "Traces", detail: "Flight recorder and replay inspection.", view: "flight" },
    { title: "Canvas", detail: "Advanced spatial inspection.", view: "canvas" },
    { title: "Incidents", detail: "Operational issues and recovery evidence.", view: "incidents", count: data.deadLetters.length },
    { title: "Runtime Diagnostics", detail: "Raw worker health and runtime details.", view: "workforce" },
    { title: "Proposal Internals", detail: "Pending queue and proposal detail records.", view: "proposals", count: data.pending.length },
    { title: "Dead Letters", detail: "Failed deliveries and replay evidence.", view: "incidents", count: data.deadLetters.length },
    { title: "Memory Internals", detail: "Raw governed memory records.", view: "memory", count: data.memories.length },
    { title: "Settings", detail: "Daemon status and local Console settings.", view: "settings" },
  ];
  return (
    <div className="advanced-screen">
      <SectionHeader title="Advanced" subtitle="Technical inspection surfaces. Daily project work should not require this area." />
      <div className="advanced-grid" data-advanced-contains="Governance, Assignments, Outcomes, Missions, Traces, Canvas, Incidents, Runtime Diagnostics, Proposal Internals, Dead Letters, Memory Internals">
        {items.map((item) => (
          <button className="advanced-card" key={item.title} onClick={() => onView(item.view)}>
            <span>{item.count == null ? "Inspect" : numberText(item.count)}</span>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

function DecisionSection({ title, proposals, onOpenProposal }: { title: string; proposals: Proposal[]; onOpenProposal: (id: string) => void }) {
  return (
    <article className="home-card">
      <div className="section-kicker">{title}</div>
      <div className="mini-list">
        {proposals.map((proposal) => <button className="mini-row" key={proposalId(proposal)} onClick={() => onOpenProposal(proposalId(proposal))}><span>{decisionTitle(proposal)}</span><span>{decisionActionLabel(proposal)}</span></button>)}
        {!proposals.length && <p className="quiet-copy">No project decisions here yet. Worker proposals will appear here in plain language.</p>}
      </div>
    </article>
  );
}

function projectDecisions(project: ProjectRecord, data: AppData): { pending: Proposal[]; approved: Proposal[]; rejected: Proposal[] } {
  const proposals = data.proposals.filter((proposal) =>
    (!!project.room_id && text(proposal.room_id || proposal.room, "") === project.room_id)
    || (!!project.mission_id && text(proposal.mission_id || proposal.goal_id, "") === project.mission_id),
  );
  return {
    pending: proposals.filter((proposal) => text(proposal.status, "") === "proposed"),
    approved: proposals.filter((proposal) => text(proposal.status, "") === "approved" || text(proposal.status, "") === "executed"),
    rejected: proposals.filter((proposal) => text(proposal.status, "") === "rejected"),
  };
}

function workerFocus(workerIdValue: string, project: ProjectRecord, data: AppData): string {
  const assignment = projectAssignments(project, data).find((item) => item.owner_worker === workerIdValue || (item.contributor_workers || []).includes(workerIdValue));
  if (assignment) return assignmentTitle(assignment);
  const deliverable = projectDeliverables(project, data).find((item) => item.owner === workerIdValue);
  if (deliverable) return deliverable.title;
  return "Available for project work";
}

function WorkView(props: {
  tab: "missions" | "outcomes" | "assignments";
  onTab: (tab: "missions" | "outcomes" | "assignments") => void;
  data: AppData;
  workers: Agent[];
  selectedMissionId: string | null;
  selectedOutcomeId: string | null;
  selectedAssignmentId: string | null;
  titleInput: string;
  descriptionInput: string;
  ownerInput: string;
  contributorsInput: string;
  missionInput: string;
  outcomeInput: string;
  roomInput: string;
  handoffToInput: string;
  handoffReasonInput: string;
  onSelectMission: (id: string | null) => void;
  onSelectOutcome: (id: string | null) => void;
  onSelectAssignment: (id: string | null) => void;
  onTitleInput: (value: string) => void;
  onDescriptionInput: (value: string) => void;
  onOwnerInput: (value: string) => void;
  onContributorsInput: (value: string) => void;
  onMissionInput: (value: string) => void;
  onOutcomeInput: (value: string) => void;
  onRoomInput: (value: string) => void;
  onHandoffToInput: (value: string) => void;
  onHandoffReasonInput: (value: string) => void;
  onCreate: () => void;
  onAssignOwner: () => void;
  onAddContributor: () => void;
  onRemoveContributor: (workerIdValue: string) => void;
  onStatus: (status: string) => void;
  onHandoff: () => void;
  onReplay: (id: string) => void;
}) {
  const active = props.data.assignments.filter((assignment) => ["assigned", "in_progress"].includes(text(assignment.status, ""))).length + props.data.missions.filter((mission) => text(mission.status, "") === "active").length;
  const blocked = props.data.assignments.filter((assignment) => assignmentHealth(assignment) === "Blocked").length + props.data.outcomes.filter((outcome) => outcomeHealth(outcome, props.data.assignments) === "Blocked").length;
  const review = props.data.assignments.filter((assignment) => text(assignment.status, "") === "review").length + props.data.outcomes.filter((outcome) => text(outcome.status, "") === "review").length;
  const completed = props.data.assignments.filter((assignment) => text(assignment.status, "") === "completed").length + props.data.outcomes.filter((outcome) => text(outcome.status, "") === "completed").length;
  return (
    <div className="space-y-6">
      <SectionHeader title="Work" subtitle="Define outcomes, assign ownership, and keep the workforce moving." />
      <div className="summary-row">
        <Metric label="Active" value={active} />
        <Metric label="Blocked" value={blocked} />
        <Metric label="Review" value={review} />
        <Metric label="Completed" value={completed} />
      </div>
      <div className="segmented-control">
        {(["missions", "outcomes", "assignments"] as const).map((tab) => <button className={`seg ${props.tab === tab ? "seg-active" : ""}`} key={tab} onClick={() => props.onTab(tab)}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}
      </div>
      {props.tab === "missions" && <MissionsView data={props.data} selectedMissionId={props.selectedMissionId} onSelectMission={props.onSelectMission} onReplay={props.onReplay} />}
      {props.tab === "outcomes" && <OutcomesView data={props.data} selectedOutcomeId={props.selectedOutcomeId} onSelectOutcome={props.onSelectOutcome} onReplay={props.onReplay} />}
      {props.tab === "assignments" && (
        <AssignmentsView
          data={props.data}
          workers={props.workers}
          selectedAssignmentId={props.selectedAssignmentId}
          titleInput={props.titleInput}
          descriptionInput={props.descriptionInput}
          ownerInput={props.ownerInput}
          contributorsInput={props.contributorsInput}
          missionInput={props.missionInput}
          outcomeInput={props.outcomeInput}
          roomInput={props.roomInput}
          handoffToInput={props.handoffToInput}
          handoffReasonInput={props.handoffReasonInput}
          onSelectAssignment={props.onSelectAssignment}
          onTitleInput={props.onTitleInput}
          onDescriptionInput={props.onDescriptionInput}
          onOwnerInput={props.onOwnerInput}
          onContributorsInput={props.onContributorsInput}
          onMissionInput={props.onMissionInput}
          onOutcomeInput={props.onOutcomeInput}
          onRoomInput={props.onRoomInput}
          onHandoffToInput={props.onHandoffToInput}
          onHandoffReasonInput={props.onHandoffReasonInput}
          onCreate={props.onCreate}
          onAssignOwner={props.onAssignOwner}
          onAddContributor={props.onAddContributor}
          onRemoveContributor={props.onRemoveContributor}
          onStatus={props.onStatus}
          onHandoff={props.onHandoff}
          onReplay={props.onReplay}
        />
      )}
    </div>
  );
}

function MissionsView({
  data,
  selectedMissionId,
  onSelectMission,
  onReplay,
}: {
  data: AppData;
  selectedMissionId: string | null;
  onSelectMission: (id: string | null) => void;
  onReplay: (id: string) => void;
}) {
  const missions = data.missions;
  const selected = missions.find((mission) => missionId(mission) === selectedMissionId) || missions[0] || null;
  const summary = data.missionSummary;
  if (!missions.length) {
    return (
      <ExperienceEmptyState
        title="No active missions."
        body="Missions are useful once there is a larger objective to govern. Start by defining the outcome you want the workforce to produce."
        action="Start with an outcome"
      />
    );
  }
  return (
    <div className="space-y-4">
      <SectionHeader title="Mission Centre" subtitle="Governance containers for meaningful AI workforce outcomes." />
      <Panel title="Mission Summary">
        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="Active Missions" value={Number(summary?.active_missions ?? missions.filter((mission) => mission.status === "active").length)} />
          <Metric label="Blocked Missions" value={Number(summary?.blocked_missions ?? missions.filter((mission) => mission.status === "blocked").length)} />
          <Metric label="Review Missions" value={Number(summary?.review_missions ?? missions.filter((mission) => mission.status === "review").length)} />
          <Metric label="Completed Missions" value={Number(summary?.completed_missions ?? missions.filter((mission) => mission.status === "completed").length)} />
        </div>
      </Panel>
      <Panel title="Mission Progress">
        <div className="grid gap-3 md:grid-cols-3">
          <Metric label="outcomes completed" value={`${Number(selected?.progress?.completed ?? 0)} / ${Number(selected?.progress?.total ?? 0)}`} />
          <Metric label="progress" value={`${Number(selected?.progress?.percent ?? 0)}%`} />
          <Metric label="outcomes blocked" value={(selected?.outcomes || []).filter((outcome) => outcome.status === "blocked").length} />
        </div>
      </Panel>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Panel title="Mission Table" flush>
          <div className="ops-table ops-table-missions">
            <div className="ops-head">
              <span>Mission</span><span>Status</span><span>Priority</span><span>Workers</span><span>Recent Activity</span><span>Open Proposals</span><span>Incidents</span><span>Last Updated</span>
            </div>
            {missions.map((mission) => {
              const id = missionId(mission);
              const openProposals = (mission.proposals || []).filter((proposal) => text(proposal.status, "") === "proposed").length;
              return (
                <button key={id} className={`ops-row ${selected && missionId(selected) === id ? "ops-row-active" : ""}`} onClick={() => onSelectMission(id)}>
                  <span className="runtime-cell">{missionTitle(mission)}<small>{id}</small></span>
                  <span className={`pill ${statusClass(mission.status)}`}>{text(mission.status, "unknown")}</span>
                  <span className={`pill ${statusClass(mission.priority)}`}>{text(mission.priority, "medium")}</span>
                  <span>{(mission.workers || []).length}</span>
                  <span>{text((mission.activity || [])[0]?.summary, "No recent activity recorded.")}</span>
                  <span>{openProposals}</span>
                  <span>{(mission.incidents || []).length}</span>
                  <span>{shortDate(mission.updated_at)}</span>
                </button>
              );
            })}
          </div>
        </Panel>
        <MissionDetailView mission={selected} memories={data.memories} onReplay={onReplay} />
      </div>
    </div>
  );
}

function MissionDetailView({ mission, memories, onReplay }: { mission: Mission | null; memories: WorkforceMemory[]; onReplay: (id: string) => void }) {
  if (!mission) return <Panel title="Mission Detail"><EmptyPanel label="Select a mission to inspect governance context." /></Panel>;
  const workers = (mission.workers || []).map(asRecord);
  const rooms = (mission.rooms || []).map(asRecord);
  const traces = (mission.traces || []).map(asRecord);
  const incidents = (mission.incidents || []).map(asRecord);
  const relationships = (mission.relationships || []).map(asRecord);
  const outcomes = mission.outcomes || [];
  const assignments = mission.assignments || [];
  return (
    <aside className="space-y-4">
      <Panel title="Mission Overview">
        <h2 className="font-mono text-xl text-slate-50">{missionTitle(mission)}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-200">{text(mission.description, "No mission description recorded.")}</p>
        <div className="mt-4 compact-grid">
          <Field label="status" value={mission.status} />
          <Field label="priority" value={mission.priority} />
          <Field label="owner" value={mission.owner || "Unassigned"} />
          <Field label="goal" value={mission.goal || "No goal recorded."} />
        </div>
      </Panel>
      <Panel title="Workers Involved">
        <div className="mini-list">
          {workers.map((worker) => <div className="mini-row" key={text(worker.adapter_id)}><span>{text(worker.runtime_name || worker.adapter_id, "worker")}</span><span>{text(worker.status || worker.role, "linked")}</span></div>)}
          {!workers.length && <span className="text-sm text-muted">No linked workers.</span>}
        </div>
      </Panel>
      <Panel title="Outcomes">
        <div className="mini-list">
          {outcomes.map((outcome) => (
            <div className="mini-row" key={outcomeId(outcome)}>
              <span>{outcomeTitle(outcome)}</span>
              <span>{text(outcome.status, "not_started")}</span>
            </div>
          ))}
          {!outcomes.length && <span className="text-sm text-muted">No linked outcomes.</span>}
        </div>
      </Panel>
      <Panel title="Assignments">
        <div className="mini-list">
          {assignmentGroups.map((group) => {
            const groupItems = assignments.filter((assignment) => assignment.status === group.status);
            if (!groupItems.length) return null;
            return (
              <div className="mini-row" key={group.status}>
                <span>{group.label}</span>
                <span>{groupItems.map(assignmentTitle).join(", ")}</span>
              </div>
            );
          })}
          {!assignments.length && <span className="text-sm text-muted">No linked assignments.</span>}
        </div>
      </Panel>
      <MemoryScopePanel memories={memories} scopeType="mission" scopeId={missionId(mission)} />
      <Panel title="Recent Activity">
        <div className="mini-list">
          {(mission.activity || []).slice(0, 8).map((item, index) => (
            <div className="mini-row" key={text(item.activity_id || index, String(index))}>
              <span>{text(item.summary, "Activity recorded.")}</span>
              <span>{shortDate(item.timestamp)}</span>
            </div>
          ))}
          {!(mission.activity || []).length && <span className="text-sm text-muted">No mission activity returned.</span>}
        </div>
      </Panel>
      <Panel title="Linked Proposals">
        <div className="mini-list">
          {(mission.proposals || []).map((proposal) => <div className="mini-row" key={proposalId(proposal)}><span>{text(proposal.title, proposalId(proposal))}</span><span>{text(proposal.status, "proposed")}</span></div>)}
          {!(mission.proposals || []).length && <span className="text-sm text-muted">No linked proposals.</span>}
        </div>
      </Panel>
      <Panel title="Linked Incidents">
        <div className="mini-list">
          {incidents.map((incident) => <div className="mini-row" key={text(incident.incident_id)}><span>{text(incident.incident_id, "incident")}</span><span>{text(incident.incident_type, "impact")}</span></div>)}
          {!incidents.length && <span className="text-sm text-muted">No linked incidents.</span>}
        </div>
      </Panel>
      <Panel title="Related Traces">
        <div className="chip-row">
          {traces.map((trace) => <button className="chip" key={text(trace.trace_id)} onClick={() => onReplay(text(trace.trace_id, ""))}>{text(trace.trace_id, "trace")}</button>)}
          {rooms.map((room) => <span className="chip" key={text(room.room_name)}>#{text(room.room_name, "room")}</span>)}
          {!traces.length && !rooms.length && <span className="text-sm text-muted">No traces or rooms linked.</span>}
        </div>
      </Panel>
      <Panel title="Outcome">
        <TokenText value={text(mission.outcome, "No outcome recorded yet.")} />
      </Panel>
      <Panel title="Risk">
        <div className="compact-grid">
          <Field label="risk level" value={mission.risk_level || "medium"} />
          <Field label="relationships" value={relationships.length} />
        </div>
      </Panel>
    </aside>
  );
}

function OutcomesView({
  data,
  selectedOutcomeId,
  onSelectOutcome,
  onReplay,
}: {
  data: AppData;
  selectedOutcomeId: string | null;
  onSelectOutcome: (id: string | null) => void;
  onReplay: (id: string) => void;
}) {
  const outcomes = data.outcomes;
  const selected = outcomes.find((outcome) => outcomeId(outcome) === selectedOutcomeId) || outcomes[0] || null;
  const summary = data.outcomeSummary;
  if (!outcomes.length) {
    return (
      <ExperienceEmptyState
        title="No outcomes yet."
        body="Outcomes describe the result you want, before deciding which worker should own it."
        action="Create Outcome"
      />
    );
  }
  return (
    <div className="space-y-4">
      <SectionHeader title="Outcome Centre" subtitle="Desired results, evidence, approval pressure, and value progress." />
      <Panel title="Outcome Summary">
        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="Completed" value={Number(summary?.completed ?? outcomes.filter((outcome) => outcome.status === "completed").length)} />
          <Metric label="In Progress" value={Number(summary?.in_progress ?? outcomes.filter((outcome) => outcome.status === "in_progress").length)} />
          <Metric label="Review" value={Number(summary?.review ?? outcomes.filter((outcome) => outcome.status === "review").length)} />
          <Metric label="Blocked" value={Number(summary?.blocked ?? outcomes.filter((outcome) => outcome.status === "blocked").length)} />
        </div>
      </Panel>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_440px]">
        <Panel title="Outcome Table" flush>
          <div className="ops-table ops-table-outcomes">
            <div className="ops-head">
              <span>Outcome</span><span>Mission</span><span>Status</span><span>Confidence</span><span>Workers</span><span>Recent Activity</span><span>Open Proposals</span><span>Incidents</span><span>Last Updated</span>
            </div>
            {outcomes.map((outcome) => {
              const id = outcomeId(outcome);
              const openProposals = (outcome.proposals || []).filter((proposal) => text(proposal.status, "") === "proposed").length;
              return (
                <button key={id} className={`ops-row ${selected && outcomeId(selected) === id ? "ops-row-active" : ""}`} onClick={() => onSelectOutcome(id)}>
                  <span className="runtime-cell">{outcomeTitle(outcome)}<small>{id}</small></span>
                  <span>{text(outcome.mission_title || outcome.mission_id, "Mission")}</span>
                  <span className={`pill ${statusClass(outcome.status)}`}>{text(outcome.status, "not_started")}</span>
                  <span className={`pill ${statusClass(outcome.confidence)}`}>{text(outcome.confidence, "medium")}</span>
                  <span>{(outcome.workers || []).length}</span>
                  <span>{text((outcome.activity || [])[0]?.summary, "No recent activity recorded.")}</span>
                  <span>{openProposals}</span>
                  <span>{(outcome.incidents || []).length}</span>
                  <span>{shortDate(outcome.updated_at)}</span>
                </button>
              );
            })}
          </div>
        </Panel>
        <OutcomeDetailView outcome={selected} memories={data.memories} onReplay={onReplay} />
      </div>
    </div>
  );
}

function OutcomeDetailView({ outcome, memories, onReplay }: { outcome: Outcome | null; memories: WorkforceMemory[]; onReplay: (id: string) => void }) {
  if (!outcome) return <Panel title="Outcome Detail"><EmptyPanel label="Select an outcome to inspect value progress." /></Panel>;
  const workers = (outcome.workers || []).map(asRecord);
  const traces = (outcome.traces || []).map(asRecord);
  const incidents = (outcome.incidents || []).map(asRecord);
  const relationships = (outcome.relationships || []).map(asRecord);
  const assignments = outcome.assignments || [];
  return (
    <aside className="space-y-4">
      <Panel title="Outcome Overview">
        <h2 className="font-mono text-xl text-slate-50">{outcomeTitle(outcome)}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-200">{text(outcome.description, "No outcome description recorded.")}</p>
        <div className="mt-4 compact-grid">
          <Field label="status" value={outcome.status} />
          <Field label="confidence" value={outcome.confidence} />
          <Field label="owner" value={outcome.owner || "Unassigned"} />
          <Field label="completed" value={outcome.completed_at ? shortDate(outcome.completed_at) : "Not completed"} />
        </div>
      </Panel>
      <Panel title="Mission Context">
        <div className="compact-grid">
          <Field label="mission" value={outcome.mission_title || outcome.mission_id} />
          <Field label="mission id" value={outcome.mission_id} />
        </div>
      </Panel>
      <Panel title="Workers Contributing">
        <div className="mini-list">
          {workers.map((worker) => <div className="mini-row" key={text(worker.adapter_id)}><span>{text(worker.runtime_name || worker.adapter_id, "worker")}</span><span>{text(worker.status || worker.role, "linked")}</span></div>)}
          {!workers.length && <span className="text-sm text-muted">No linked workers.</span>}
        </div>
      </Panel>
      <Panel title="Assignments">
        <div className="mini-list">
          {assignments.map((assignment) => (
            <div className="mini-row" key={assignmentId(assignment)}>
              <span>{assignmentTitle(assignment)}</span>
              <span>{assignment.owner_worker || assignmentStatusLabel(assignment.status)}</span>
            </div>
          ))}
          {!assignments.length && <span className="text-sm text-muted">No assignments contributing to this outcome.</span>}
        </div>
      </Panel>
      <MemoryScopePanel memories={memories} scopeType="outcome" scopeId={outcomeId(outcome)} />
      <Panel title="Recent Activity">
        <div className="mini-list">
          {(outcome.activity || []).slice(0, 8).map((item, index) => (
            <div className="mini-row" key={text(item.activity_id || index, String(index))}>
              <span>{text(item.summary, "Activity recorded.")}</span>
              <span>{shortDate(item.timestamp)}</span>
            </div>
          ))}
          {!(outcome.activity || []).length && <span className="text-sm text-muted">No outcome activity returned.</span>}
        </div>
      </Panel>
      <Panel title="Evidence">
        <div className="chip-row">
          {traces.map((trace) => <button className="chip" key={text(trace.trace_id)} onClick={() => onReplay(text(trace.trace_id, ""))}>{text(trace.trace_id, "trace")}</button>)}
          {!traces.length && <span className="text-sm text-muted">No trace evidence linked.</span>}
        </div>
      </Panel>
      <Panel title="Linked Proposals">
        <div className="mini-list">
          {(outcome.proposals || []).map((proposal) => <div className="mini-row" key={proposalId(proposal)}><span>{text(proposal.title, proposalId(proposal))}</span><span>{text(proposal.status, "proposed")}</span></div>)}
          {!(outcome.proposals || []).length && <span className="text-sm text-muted">No linked proposals.</span>}
        </div>
      </Panel>
      <Panel title="Linked Incidents">
        <div className="mini-list">
          {incidents.map((incident) => <div className="mini-row" key={text(incident.incident_id)}><span>{text(incident.incident_id, "incident")}</span><span>{text(incident.incident_type, "impact")}</span></div>)}
          {!incidents.length && <span className="text-sm text-muted">No linked incidents.</span>}
        </div>
      </Panel>
      <Panel title="Decision History">
        <div className="mini-list">
          {relationships.filter((relationship) => text(relationship.target_type, "") === "decision").map((relationship) => <div className="mini-row" key={text(relationship.relationship_id)}><span>{text(relationship.target_id, "decision")}</span><span>{text(relationship.kind, "linked")}</span></div>)}
          {!relationships.some((relationship) => text(relationship.target_type, "") === "decision") && <span className="text-sm text-muted">No decision relationships returned.</span>}
        </div>
      </Panel>
      <Panel title="Outcome Confidence">
        <Field label="confidence" value={outcome.confidence || "medium"} />
      </Panel>
      <Panel title="Outcome Status">
        <Field label="status" value={outcome.status || "not_started"} />
      </Panel>
    </aside>
  );
}

const assignmentGroups: { status: string; label: string }[] = [
  { status: "assigned", label: "Assigned" },
  { status: "in_progress", label: "In Progress" },
  { status: "waiting", label: "Waiting" },
  { status: "blocked", label: "Blocked" },
  { status: "review", label: "Review" },
  { status: "completed", label: "Completed" },
];

function AssignmentsView({
  data,
  workers,
  selectedAssignmentId,
  titleInput,
  descriptionInput,
  ownerInput,
  contributorsInput,
  missionInput,
  outcomeInput,
  roomInput,
  handoffToInput,
  handoffReasonInput,
  onSelectAssignment,
  onTitleInput,
  onDescriptionInput,
  onOwnerInput,
  onContributorsInput,
  onMissionInput,
  onOutcomeInput,
  onRoomInput,
  onHandoffToInput,
  onHandoffReasonInput,
  onCreate,
  onAssignOwner,
  onAddContributor,
  onRemoveContributor,
  onStatus,
  onHandoff,
  onReplay,
}: {
  data: AppData;
  workers: Agent[];
  selectedAssignmentId: string | null;
  titleInput: string;
  descriptionInput: string;
  ownerInput: string;
  contributorsInput: string;
  missionInput: string;
  outcomeInput: string;
  roomInput: string;
  handoffToInput: string;
  handoffReasonInput: string;
  onSelectAssignment: (id: string | null) => void;
  onTitleInput: (value: string) => void;
  onDescriptionInput: (value: string) => void;
  onOwnerInput: (value: string) => void;
  onContributorsInput: (value: string) => void;
  onMissionInput: (value: string) => void;
  onOutcomeInput: (value: string) => void;
  onRoomInput: (value: string) => void;
  onHandoffToInput: (value: string) => void;
  onHandoffReasonInput: (value: string) => void;
  onCreate: () => void;
  onAssignOwner: () => void;
  onAddContributor: () => void;
  onRemoveContributor: (workerIdValue: string) => void;
  onStatus: (status: string) => void;
  onHandoff: () => void;
  onReplay: (id: string) => void;
}) {
  const assignments = data.assignments;
  const selected = assignments.find((assignment) => assignmentId(assignment) === selectedAssignmentId) || assignments[0] || null;
  const summary = data.assignmentSummary;
  const extraGroups = Array.from(new Set(assignments.map((assignment) => text(assignment.status, "assigned"))))
    .filter((status) => !assignmentGroups.some((group) => group.status === status))
    .map((status) => ({ status, label: assignmentStatusLabel(status) }));
  const groups = [...assignmentGroups, ...extraGroups];
  const emptyAssignments = !assignments.length;

  return (
    <div className="space-y-4">
      <SectionHeader title="Assignments" subtitle="Give work an owner, contributors, and a visible handoff trail." />
      {!emptyAssignments && (
        <Panel title="Current ownership">
          <div className="grid gap-3 md:grid-cols-6">
            <Metric label="Assigned" value={Number(summary?.assigned ?? assignments.filter((assignment) => assignment.status === "assigned").length)} />
            <Metric label="In Progress" value={Number(summary?.in_progress ?? assignments.filter((assignment) => assignment.status === "in_progress").length)} />
            <Metric label="Waiting" value={Number(summary?.waiting ?? assignments.filter((assignment) => assignment.status === "waiting").length)} />
            <Metric label="Blocked" value={Number(summary?.blocked ?? assignments.filter((assignment) => assignment.status === "blocked").length)} />
            <Metric label="Review" value={Number(summary?.review ?? assignments.filter((assignment) => assignment.status === "review").length)} />
            <Metric label="Completed" value={Number(summary?.completed ?? assignments.filter((assignment) => assignment.status === "completed").length)} />
          </div>
        </Panel>
      )}
      {emptyAssignments && (
        <ExperienceEmptyState
          title="Nothing is currently assigned."
          body="Create work for the workforce by giving one worker clear ownership. Contributors and handoffs can be added later."
          action="New Assignment"
        />
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_440px]">
        <section className="space-y-4">
          <Panel title={emptyAssignments ? "New Assignment" : "Create Assignment"}>
            <div className="grid gap-3 md:grid-cols-2">
              <input className="input" value={titleInput} onChange={(event) => onTitleInput(event.target.value)} placeholder="assignment title" />
              <input className="input" value={ownerInput} onChange={(event) => onOwnerInput(event.target.value)} placeholder="owner worker" list="assignment-worker-list" />
              <input className="input" value={contributorsInput} onChange={(event) => onContributorsInput(event.target.value)} placeholder="contributors, comma separated" />
              <input className="input" value={roomInput} onChange={(event) => onRoomInput(event.target.value)} placeholder="room id" />
              <select className="input" value={missionInput} onChange={(event) => onMissionInput(event.target.value)}>
                <option value="">mission optional</option>
                {data.missions.map((mission) => <option value={missionId(mission)} key={missionId(mission)}>{missionTitle(mission)}</option>)}
              </select>
              <select className="input" value={outcomeInput} onChange={(event) => onOutcomeInput(event.target.value)}>
                <option value="">outcome optional</option>
                {data.outcomes.map((outcome) => <option value={outcomeId(outcome)} key={outcomeId(outcome)}>{outcomeTitle(outcome)}</option>)}
              </select>
              <textarea className="textarea md:col-span-2" value={descriptionInput} onChange={(event) => onDescriptionInput(event.target.value)} placeholder="description" />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn-cyan" onClick={onCreate}>Create Assignment</button>
              <button className="btn" onClick={onAssignOwner}>Assign Worker</button>
              <button className="btn" onClick={onAddContributor}>Add Contributor</button>
            </div>
            <datalist id="assignment-worker-list">
              {workers.map((worker) => <option value={workerId(worker)} key={workerId(worker)} />)}
            </datalist>
          </Panel>
          {!emptyAssignments && groups.map((group) => {
            const groupAssignments = assignments.filter((assignment) => text(assignment.status, "assigned") === group.status);
            if (!groupAssignments.length) return null;
            return (
              <Panel title={group.label} key={group.status}>
                <div className="assignment-card-grid">
                  {groupAssignments.map((assignment) => {
                    const id = assignmentId(assignment);
                    return (
                      <button className={`assignment-card ${selected && assignmentId(selected) === id ? "assignment-card-active" : ""}`} key={id} onClick={() => onSelectAssignment(id)}>
                        <div>
                          <h3>{assignmentTitle(assignment)}</h3>
                          <small>{id}</small>
                        </div>
                        <div className="compact-grid mt-3">
                          <Field label="owner" value={assignment.owner_worker || "Unassigned"} />
                          <Field label="contributors" value={(assignment.contributor_workers || []).join(", ") || "None"} />
                          <Field label="mission" value={assignmentMissionTitle(assignment, data.missions)} />
                          <Field label="outcome" value={assignmentOutcomeTitle(assignment, data.outcomes)} />
                          <Field label="status" value={assignmentStatusLabel(assignment.status)} />
                          <Field label="last activity" value={shortDate(assignment.last_activity || assignment.updated_at)} />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </Panel>
            );
          })}
        </section>
        <AssignmentDetailView
          assignment={selected}
          data={data}
          handoffToInput={handoffToInput}
          handoffReasonInput={handoffReasonInput}
          onHandoffToInput={onHandoffToInput}
          onHandoffReasonInput={onHandoffReasonInput}
          onRemoveContributor={onRemoveContributor}
          onStatus={onStatus}
          onHandoff={onHandoff}
          onReplay={onReplay}
        />
      </div>
    </div>
  );
}

function AssignmentDetailView({
  assignment,
  data,
  handoffToInput,
  handoffReasonInput,
  onHandoffToInput,
  onHandoffReasonInput,
  onRemoveContributor,
  onStatus,
  onHandoff,
  onReplay,
}: {
  assignment: Assignment | null;
  data: AppData;
  handoffToInput: string;
  handoffReasonInput: string;
  onHandoffToInput: (value: string) => void;
  onHandoffReasonInput: (value: string) => void;
  onRemoveContributor: (workerIdValue: string) => void;
  onStatus: (status: string) => void;
  onHandoff: () => void;
  onReplay: (id: string) => void;
}) {
  if (!assignment) return <Panel title="Assignment Detail"><EmptyPanel label="Select or create an assignment to inspect workforce ownership." /></Panel>;
  const handoffs = assignment.handoffs || data.recentHandoffs.filter((handoff) => handoff.assignment_id === assignmentId(assignment));
  const traces = (assignment.traces || []).map(asRecord);
  const proposals = assignment.proposals || [];
  const activity = assignment.activity || [];

  return (
    <aside className="space-y-4">
      <Panel title="Assignment Detail">
        <h2 className="font-mono text-xl text-slate-50">{assignmentTitle(assignment)}</h2>
        <p className="mt-2 text-sm leading-6 text-slate-200">{text(assignment.description, "No assignment description recorded.")}</p>
        <div className="mt-4 compact-grid">
          <Field label="status" value={assignmentStatusLabel(assignment.status)} />
          <Field label="owner" value={assignment.owner_worker || "Unassigned"} />
          <Field label="mission" value={assignmentMissionTitle(assignment, data.missions)} />
          <Field label="outcome" value={assignmentOutcomeTitle(assignment, data.outcomes)} />
          <Field label="room" value={assignment.room_id ? `#${assignment.room_id}` : "None"} />
          <Field label="updated" value={shortDate(assignment.updated_at)} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn" onClick={() => onStatus("in_progress")}>Mark In Progress</button>
          <button className="btn" onClick={() => onStatus("waiting")}>Mark Waiting</button>
          <button className="btn-amber" onClick={() => onStatus("blocked")}>Mark Blocked</button>
          <button className="btn" onClick={() => onStatus("review")}>Request Review</button>
          <button className="btn-cyan" onClick={() => onStatus("completed")}>Complete Assignment</button>
        </div>
      </Panel>
      <Panel title="Contributors">
        <div className="chip-row">
          {(assignment.contributor_workers || []).map((workerIdValue) => (
            <button className="chip" key={workerIdValue} onClick={() => onRemoveContributor(workerIdValue)}>{workerIdValue} remove</button>
          ))}
          {!(assignment.contributor_workers || []).length && <span className="text-sm text-muted">No contributors assigned.</span>}
        </div>
      </Panel>
      <MemoryScopePanel memories={data.memories} scopeType="assignment" scopeId={assignmentId(assignment)} />
      <Panel title="Handoff Timeline">
        <div className="handoff-timeline">
          <div className="handoff-step">
            <strong>{handoffs[0]?.from_worker || assignment.owner_worker || "Owner"}</strong>
            <span>{handoffs.length ? "Initial owner" : "Current owner"}</span>
          </div>
          {handoffs.map((handoff, index) => (
            <div className="handoff-step" key={text(handoff.handoff_id || index, String(index))}>
              <strong>{text(handoff.from_worker, "worker")} {"->"} {text(handoff.to_worker, "worker")}</strong>
              <span>{text(handoff.reason || handoff.context_summary || handoff.summary, "Handoff recorded.")}</span>
              <small>{shortDate(handoff.timestamp || handoff.created_at)}</small>
            </div>
          ))}
          {!handoffs.length && <span className="text-sm text-muted">No handoffs recorded.</span>}
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
          <input className="input" value={handoffToInput} onChange={(event) => onHandoffToInput(event.target.value)} placeholder="new owner" />
          <input className="input" value={handoffReasonInput} onChange={(event) => onHandoffReasonInput(event.target.value)} placeholder="handoff reason" />
          <button className="btn-cyan" onClick={onHandoff}>Handoff</button>
        </div>
      </Panel>
      <Panel title="Activity">
        <div className="mini-list">
          {activity.slice(0, 8).map((item, index) => (
            <div className="mini-row" key={text(item.activity_id || index, String(index))}>
              <span>{text(item.summary, "Activity recorded.")}</span>
              <span>{shortDate(item.timestamp)}</span>
            </div>
          ))}
          {!activity.length && <span className="text-sm text-muted">No assignment activity returned.</span>}
        </div>
      </Panel>
      <Panel title="Related Room">
        <Field label="room" value={assignment.room_id ? `#${assignment.room_id}` : "No linked room"} />
      </Panel>
      <Panel title="Related Outcome">
        <Field label="outcome" value={assignmentOutcomeTitle(assignment, data.outcomes)} />
      </Panel>
      <Panel title="Related Mission">
        <Field label="mission" value={assignmentMissionTitle(assignment, data.missions)} />
      </Panel>
      <Panel title="Related Proposals">
        <div className="mini-list">
          {proposals.map((proposal) => <div className="mini-row" key={proposalId(proposal)}><span>{text(proposal.title, proposalId(proposal))}</span><span>{text(proposal.status, "proposed")}</span></div>)}
          {!proposals.length && <span className="text-sm text-muted">No related proposals.</span>}
        </div>
      </Panel>
      <Panel title="Related Traces">
        <div className="chip-row">
          {traces.map((trace) => <button className="chip" key={text(trace.trace_id)} onClick={() => onReplay(text(trace.trace_id, ""))}>{text(trace.trace_id, "trace")}</button>)}
          {!traces.length && <span className="text-sm text-muted">No related traces.</span>}
        </div>
      </Panel>
    </aside>
  );
}

function memoryId(memory: WorkforceMemory): string {
  return text(memory.memory_id, "");
}

function memoryBody(memory: WorkforceMemory): string {
  return text(memory.body || memory.content, "No memory body recorded.");
}

function scopedMemories(memories: WorkforceMemory[], scopeType: string, scopeId?: string): WorkforceMemory[] {
  return memories.filter((memory) => text(memory.status, "") === "approved" && text(memory.scope_type, "global") === scopeType && (scopeType === "global" || text(memory.scope_id, "") === text(scopeId, "")));
}

function MemoryScopePanel({
  memories,
  scopeType,
  scopeId,
  onPrimeNote,
}: {
  memories: WorkforceMemory[];
  scopeType: string;
  scopeId?: string;
  onPrimeNote?: () => void;
}) {
  const items = scopedMemories(memories, scopeType, scopeId).slice(0, 8);
  return (
    <Panel title="Approved Knowledge">
      <div className="mini-list">
        {items.map((memory) => (
          <div className="mini-row" key={memoryId(memory)}>
            <span>{text(memory.title, memoryId(memory))}</span>
            <span>{text(memory.importance, "medium")} · {memoryId(memory).slice(0, 8)}</span>
          </div>
        ))}
        {!items.length && <span className="text-sm text-muted">No approved memory for this scope.</span>}
      </div>
      {onPrimeNote && <button className="btn mt-3" onClick={onPrimeNote}>Add scoped memory note</button>}
    </Panel>
  );
}

function KnowledgeView({
  memories,
  title,
  body,
  scopeType,
  scopeId,
  importance,
  onTitle,
  onBody,
  onScopeType,
  onScopeId,
  onImportance,
  onCreate,
  onAction,
}: {
  memories: WorkforceMemory[];
  title: string;
  body: string;
  scopeType: string;
  scopeId: string;
  importance: string;
  onTitle: (value: string) => void;
  onBody: (value: string) => void;
  onScopeType: (value: string) => void;
  onScopeId: (value: string) => void;
  onImportance: (value: string) => void;
  onCreate: () => void;
  onAction: (memoryId: string, action: "approve" | "reject" | "archive") => void;
}) {
  const [typeFilter, setTypeFilter] = useState("");
  const [scopeFilter, setScopeFilter] = useState("");
  const [importanceFilter, setImportanceFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const filtered = memories.filter((memory) => {
    if (typeFilter && memory.memory_type !== typeFilter) return false;
    if (scopeFilter && memory.scope_type !== scopeFilter) return false;
    if (importanceFilter && memory.importance !== importanceFilter) return false;
    if (statusFilter && memory.status !== statusFilter) return false;
    return true;
  });
  const statuses = ["approved", "proposed", "rejected", "archived"];
  const types = Array.from(new Set(memories.map((memory) => memory.memory_type).filter(Boolean))).sort();
  const company = memories.filter((memory) => text(memory.status, "") === "approved" && text(memory.scope_type, "global") === "global");
  const projects = memories.filter((memory) => text(memory.status, "") === "approved" && ["room", "mission", "outcome", "assignment"].includes(text(memory.scope_type, "")));
  const people = memories.filter((memory) => text(memory.status, "") === "approved" && text(memory.scope_type, "") === "runtime");
  const technical = memories.filter((memory) => text(memory.status, "") === "approved" && (text(memory.memory_type, "").includes("technical") || text(memory.memory_type, "").includes("runtime") || text(memory.source_type, "").includes("trace")));
  const lessons = memories.filter((memory) => text(memory.status, "") === "approved" && (text(memory.memory_type, "").includes("lesson") || text(memory.memory_type, "").includes("observation") || text(memory.importance, "") === "critical"));
  const pendingReview = memories.filter((memory) => text(memory.status, "") === "proposed");
  const archivedMemory = memories.filter((memory) => text(memory.status, "") === "archived");
  return (
    <div className="space-y-4">
      <SectionHeader title="Knowledge" subtitle="What the workforce should know before it works." />
      <Panel title="Teach Workforce">
        <div className="grid gap-3 xl:grid-cols-[1fr_1fr_160px_1fr_160px_auto]">
          <input className="input" value={title} onChange={(event) => onTitle(event.target.value)} placeholder="Title" />
          <input className="input" value={body} onChange={(event) => onBody(event.target.value)} placeholder="What should the workforce remember?" />
          <select className="input" value={scopeType} onChange={(event) => onScopeType(event.target.value)}>
            {["global", "room", "mission", "outcome", "assignment", "runtime"].map((item) => <option key={item}>{item}</option>)}
          </select>
          <input className="input" value={scopeId} onChange={(event) => onScopeId(event.target.value)} placeholder="Where should this apply?" />
          <select className="input" value={importance} onChange={(event) => onImportance(event.target.value)}>
            {["low", "medium", "high", "critical"].map((item) => <option key={item}>{item}</option>)}
          </select>
          <button className="btn-cyan" onClick={onCreate}>Teach Workforce</button>
        </div>
      </Panel>
      <div className="knowledge-notes-grid" data-knowledge-sections="Company, Projects, People, Technical, Lessons Learned, Pending Review">
        <MemorySection title="Company" memories={company} onAction={onAction} />
        <MemorySection title="Projects" memories={projects} onAction={onAction} />
        <MemorySection title="People" memories={people} onAction={onAction} />
        <MemorySection title="Technical" memories={technical} onAction={onAction} />
        <MemorySection title="Lessons Learned" memories={lessons} onAction={onAction} />
        <MemorySection title="Pending Review" memories={pendingReview} onAction={onAction} />
      </div>
      <details className="knowledge-admin raw-details">
        <summary>Filters and archived records</summary>
        <div className="grid gap-3 md:grid-cols-4">
            <select className="input" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="">all types</option>
              {types.map((item) => <option key={item}>{item}</option>)}
            </select>
            <select className="input" value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value)}>
              <option value="">all scopes</option>
              {["global", "room", "mission", "outcome", "assignment", "runtime"].map((item) => <option key={item}>{item}</option>)}
            </select>
            <select className="input" value={importanceFilter} onChange={(event) => setImportanceFilter(event.target.value)}>
              <option value="">all importance</option>
              {["low", "medium", "high", "critical"].map((item) => <option key={item}>{item}</option>)}
            </select>
            <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">all statuses</option>
              {statuses.map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
          <MemorySection title="Archived" memories={archivedMemory} onAction={onAction} />
      </details>
      <Panel title="Knowledge records" flush>
        <div className="ops-table memory-table">
          <div className="ops-head">
            <span>Title</span><span>Type</span><span>Scope</span><span>Status</span><span>Importance</span><span>Source</span><span>Created By</span><span>Updated</span><span>Actions</span>
          </div>
          {filtered.map((memory) => (
            <div className="ops-row static-row" key={memoryId(memory)}>
              <span><strong>{text(memory.title, memoryId(memory))}</strong><small>{memoryBody(memory)}</small></span>
              <span>{memory.memory_type}</span>
              <span>{text(memory.scope_type, "global")}{memory.scope_id ? `:${memory.scope_id}` : ""}</span>
              <span>{text(memory.status, "proposed")}</span>
              <span>{text(memory.importance, "medium")}</span>
              <span>{text(memory.source_type, "operator")}{memory.source_id ? `:${memory.source_id}` : ""}</span>
              <span>{text(memory.created_by, "operator")}</span>
              <span>{shortDate(memory.updated_at || memory.created_at)}</span>
              <span className="chip-row">
                {memory.status !== "approved" && <button className="micro-btn" onClick={() => onAction(memoryId(memory), "approve")}>approve</button>}
                {memory.status !== "rejected" && <button className="micro-btn" onClick={() => onAction(memoryId(memory), "reject")}>reject</button>}
                {memory.status !== "archived" && <button className="micro-btn" onClick={() => onAction(memoryId(memory), "archive")}>archive</button>}
              </span>
            </div>
          ))}
          {!filtered.length && <EmptyPanel label="No memory records match the filters." />}
        </div>
      </Panel>
    </div>
  );
}

function MemorySection({ title, memories, onAction }: { title: string; memories: WorkforceMemory[]; onAction: (memoryId: string, action: "approve" | "reject" | "archive") => void }) {
  return (
    <section className="memory-section">
      <div className="section-kicker">{title}</div>
      <div className="memory-card-list">
        {memories.slice(0, 4).map((memory) => (
          <article className="memory-card" key={memoryId(memory)}>
            <div>
              <h3>{text(memory.title, memoryId(memory))}</h3>
              <p>{memoryBody(memory)}</p>
              <small>{text(memory.scope_type, "global")}{memory.scope_id ? ` · ${memory.scope_id}` : ""} · {text(memory.importance, "medium")}</small>
            </div>
            <div className="memory-actions">
              {memory.status !== "approved" && <button className="text-link" onClick={() => onAction(memoryId(memory), "approve")}>Approve</button>}
              {memory.status !== "rejected" && <button className="text-link" onClick={() => onAction(memoryId(memory), "reject")}>Reject</button>}
              {memory.status !== "archived" && <button className="text-link" onClick={() => onAction(memoryId(memory), "archive")}>Archive</button>}
            </div>
          </article>
        ))}
        {!memories.length && <p className="quiet-copy">Nothing here.</p>}
      </div>
    </section>
  );
}

function ActivityView({
  data,
  workers,
  rooms,
  missions,
  outcomes,
  assignments,
  onReplay,
}: {
  data: AppData;
  workers: Agent[];
  rooms: Room[];
  missions: Mission[];
  outcomes: Outcome[];
  assignments: Assignment[];
  onReplay: (id: string) => void;
}) {
  const [runtimeFilter, setRuntimeFilter] = useState("");
  const [roomFilter, setRoomFilter] = useState("");
  const [missionFilter, setMissionFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [assignmentFilter, setAssignmentFilter] = useState("");
  const [activeMissionOnly, setActiveMissionOnly] = useState(false);
  const [eventFilter, setEventFilter] = useState("");
  const activity = data.recentActivity.length ? data.recentActivity : data.workforcePresence?.recent_activity || [];
  const eventTypes = Array.from(new Set(activity.map(activityEventType).filter(Boolean))).sort();
  const filtered = activity.filter((item) => {
    const runtime = activityRuntime(item);
    const room = activityRoom(item);
    const eventType = activityEventType(item);
    if (runtimeFilter && runtime !== runtimeFilter) return false;
    if (roomFilter && room !== roomFilter) return false;
    if (missionFilter && !(item.mission_ids || []).includes(missionFilter) && item.mission_id !== missionFilter) return false;
    if (outcomeFilter && !(item.outcome_ids || []).includes(outcomeFilter) && item.outcome_id !== outcomeFilter) return false;
    if (assignmentFilter && text(item.assignment_id, "") !== assignmentFilter) return false;
    if (activeMissionOnly) {
      const activeIds = missions.filter((mission) => mission.status === "active").map(missionId);
      if (!activeIds.some((id) => (item.mission_ids || []).includes(id) || item.mission_id === id)) return false;
    }
    if (eventFilter && eventType !== eventFilter) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      <SectionHeader title="Activity" subtitle="A readable timeline of what just happened." />
      <details className="raw-details">
        <summary>Filters</summary>
        <div className="grid gap-3 md:grid-cols-7">
          <select className="input" value={runtimeFilter} onChange={(event) => setRuntimeFilter(event.target.value)}>
            <option value="">all runtimes</option>
            {workers.map((worker) => {
              const id = workerId(worker);
              return <option value={id} key={id}>{id}</option>;
            })}
          </select>
          <select className="input" value={roomFilter} onChange={(event) => setRoomFilter(event.target.value)}>
            <option value="">all rooms</option>
            {rooms.map((room) => {
              const name = text(room.name, "");
              return <option value={name} key={name}>#{name}</option>;
            })}
          </select>
          <select className="input" value={missionFilter} onChange={(event) => setMissionFilter(event.target.value)}>
            <option value="">all missions</option>
            {missions.map((mission) => {
              const id = missionId(mission);
              return <option value={id} key={id}>{missionTitle(mission)}</option>;
            })}
          </select>
          <select className="input" value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value)}>
            <option value="">all outcomes</option>
            {outcomes.map((outcome) => {
              const id = outcomeId(outcome);
              return <option value={id} key={id}>{outcomeTitle(outcome)}</option>;
            })}
          </select>
          <select className="input" value={assignmentFilter} onChange={(event) => setAssignmentFilter(event.target.value)}>
            <option value="">all assignments</option>
            {assignments.map((assignment) => {
              const id = assignmentId(assignment);
              return <option value={id} key={id}>{assignmentTitle(assignment)}</option>;
            })}
          </select>
          <select className="input" value={eventFilter} onChange={(event) => setEventFilter(event.target.value)}>
            <option value="">all event types</option>
            {eventTypes.map((eventType) => <option value={eventType} key={eventType}>{eventType}</option>)}
          </select>
          <label className="check-label"><input type="checkbox" checked={activeMissionOnly} onChange={(event) => setActiveMissionOnly(event.target.checked)} /> active missions</label>
        </div>
      </details>
      <section className="living-timeline" data-timeline-first="true">
          {filtered.map((item, index) => {
            const traceId = text(item.trace_id || item.proposal_id || item.activity_id, "");
            const mission = missions.find((candidate) => missionId(candidate) === item.mission_id);
            const outcome = outcomes.find((candidate) => outcomeId(candidate) === item.outcome_id);
            const assignment = assignments.find((candidate) => assignmentId(candidate) === text(item.assignment_id, ""));
            return (
              <article className="living-timeline-item" key={text(item.activity_id || index, String(index))}>
                <time>{shortDate(item.timestamp)}</time>
                <div>
                  <h3>{text(item.summary, "Activity recorded.")}</h3>
                  <p>
                    {activityRuntime(item) || "operator"}
                    {activityRoom(item) ? ` in #${activityRoom(item)}` : ""}
                    {mission ? ` · ${missionTitle(mission)}` : ""}
                    {outcome ? ` · ${outcomeTitle(outcome)}` : ""}
                    {assignment ? ` · ${assignmentTitle(assignment)}` : ""}
                  </p>
                  <details className="raw-details">
                    <summary>Details</summary>
                    <div className="compact-grid mt-3">
                      <Field label="event type" value={activityEventType(item)} />
                      <Field label="trace" value={traceId || "None"} />
                    </div>
                  </details>
                </div>
                {traceId && <button className="text-link" onClick={() => onReplay(traceId)}>Replay</button>}
              </article>
            );
          })}
          {!filtered.length && <ExperienceEmptyState title="No recent activity matches these filters." body="Clear filters or open a conversation to create new activity." action="Clear Filters" />}
      </section>
    </div>
  );
}

function WorkforceView({
  data,
  workers,
  proposals,
  missions,
  outcomes,
  rooms,
  daemonStatus,
  selectedRuntime,
  onSelectRuntime,
  onReplay,
}: {
  data: AppData;
  workers: Agent[];
  proposals: Proposal[];
  missions: Mission[];
  outcomes: Outcome[];
  rooms: Room[];
  daemonStatus: DaemonStatus;
  selectedRuntime: string | null;
  onSelectRuntime: (runtime: string | null) => void;
  onReplay: (id: string) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("health");
  const selected = workers.find((worker) => workerId(worker) === selectedRuntime) || null;
  const selectedPresence = selectedRuntime ? presenceForRuntime(selectedRuntime, data.workforcePresence) : undefined;
  const presenceRows = data.workforcePresence?.workers?.length
    ? data.workforcePresence.workers
    : workers.map((worker) => ({
      runtime_id: workerId(worker),
      display_name: workerId(worker),
      health_status: workerHealth(worker),
      trust_score: Math.round(workerTrust(worker) * 100),
      presence_state: workerHealth(worker) === "healthy" ? "idle" : "needs_attention",
      latest_activity_summary: text(workerReputation(worker).latest_delivery_status || worker.latest_delivery_status, "No recent activity recorded."),
      latest_activity_at: text(workerReputation(worker).last_seen, ""),
      current_activity: workerHealth(worker) === "healthy" ? "Idle" : "Needs attention",
      last_meaningful_action: text(workerReputation(worker).latest_delivery_status || worker.latest_delivery_status, "No recent activity recorded."),
      seconds_since_activity: null,
      idle_for_seconds: null,
      needs_attention: displaySeverityForRuntime(worker) !== "Operational",
      attention_reason: explainRuntimeIssue(worker),
      suggested_action: suggestedRuntimeAction(worker),
    })) as WorkforcePresenceWorker[];
  const sortedPresence = [...presenceRows].sort((left, right) => {
    const leftWorker = workers.find((worker) => workerId(worker) === presenceId(left));
    const rightWorker = workers.find((worker) => workerId(worker) === presenceId(right));
    if (sortKey === "health") return (healthRank[text(left.health_status, "healthy").toLowerCase()] ?? 2) - (healthRank[text(right.health_status, "healthy").toLowerCase()] ?? 2);
    if (sortKey === "trust") return Number(right.trust_score ?? 0) - Number(left.trust_score ?? 0);
    if (sortKey === "latency") return workerLatency(leftWorker || {}) - workerLatency(rightWorker || {});
    return Number(right.needs_attention) - Number(left.needs_attention);
  });

  return (
    <div className="space-y-4">
      <SectionHeader title="Workforce" subtitle="Who is available, what they are doing, and what to watch." />
      <div className="toolbar">
        {(["health", "trust", "latency", "incidents"] as SortKey[]).map((key) => (
          <button key={key} className={`seg ${sortKey === key ? "seg-active" : ""}`} onClick={() => setSortKey(key)}>
            sort {key}
          </button>
        ))}
      </div>
      <section className="worker-card-grid" data-worker-cards="Can I use this worker, what are they doing, what should I watch">
          {sortedPresence.map((presence) => {
            const id = presenceId(presence);
            const worker = workers.find((item) => workerId(item) === id);
            const status = operatorWorkerStatus(worker, presence);
            const reason = text(presence.attention_reason, worker ? explainRuntimeIssue(worker) : "No current reliability issue detected.");
            const action = text(presence.suggested_action, worker ? suggestedRuntimeAction(worker, runtimeRoomDependency(worker, rooms, proposals)) : "No action needed.");
            const currentContext = presence.current_room ? `#${presence.current_room}` : text(presence.current_mission?.title || missionForWorker(id, missions)?.title || presence.current_outcome?.title || outcomeForWorker(id, outcomes)?.title, "No active work");
            return (
              <button key={id} className={`worker-card ${selectedRuntime === id ? "worker-card-active" : ""}`} onClick={() => onSelectRuntime(id)}>
                <div className="worker-card-head">
                  <span>{text(presence.display_name, id)}</span>
                  <span className={`pill presence-chip status-${operatorWorkerTone(status)}`}>{status}</span>
                </div>
                <div className="worker-card-body">
                  <Field label="Working in" value={currentContext} />
                  <Field label="Last reply" value={lastMeaningfulAction(presence)} />
                  <Field label="Watch" value={reason} />
                  <Field label="Recommended action" value={action} />
                </div>
                <details className="raw-details" onClick={(event) => event.stopPropagation()}>
                  <summary>Raw health and trust</summary>
                  <div className="compact-grid mt-3">
                    <Field label="raw health" value={text(presence.health_status, worker ? workerHealth(worker) : "unknown")} />
                    <Field label="trust" value={percent(presence.trust_score)} />
                    <Field label="assignments" value={numberText(presence.current_assignment_count)} />
                    <Field label="idle" value={presence.seconds_since_activity ?? presence.idle_for_seconds ?? "unknown"} />
                  </div>
                </details>
              </button>
            );
          })}
          {!sortedPresence.length && <ExperienceEmptyState title="No workers discovered." body="Run runtime discovery or add an adapter before assigning work." action="Open Settings" />}
      </section>
      {selected && (
        <RuntimeDrawer runtime={selected} presence={selectedPresence} rooms={rooms} proposals={proposals} memories={data.memories} onClose={() => onSelectRuntime(null)} onReplay={onReplay} />
      )}
    </div>
  );
}

function RuntimeDrawer({
  runtime,
  presence,
  rooms,
  proposals,
  memories,
  onClose,
  onReplay,
}: {
  runtime: Agent;
  presence?: WorkforcePresenceWorker;
  rooms: Room[];
  proposals: Proposal[];
  memories: WorkforceMemory[];
  onClose: () => void;
  onReplay: (id: string) => void;
}) {
  const id = workerId(runtime);
  const reputation = workerReputation(runtime);
  const linked = proposals.filter((proposal) => text(proposal.proposed_by || proposal.proposer, "") === id);
  const dependency = runtimeRoomDependency(runtime, rooms, proposals);
  const severity = humanHealthFromPresence(presence, runtime);
  const operatorStatus = operatorWorkerStatus(runtime, presence);
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
        <Field label="presence" value={presenceLabel(presence?.presence_state)} />
        <Field label="operator status" value={operatorStatus} />
        <Field label="display severity" value={severity} />
        <Field label="raw health" value={workerHealth(runtime)} />
        <Field label="trust" value={percent(presence?.trust_score ?? reputation.trust_score ?? runtime.trust_score ?? runtime.trust)} />
        <Field label="idle for" value={formatIdle(presence?.idle_for_seconds)} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Panel title="Presence Summary">
          <div className="compact-grid">
            <Field label="last activity" value={text(presence?.latest_activity_summary, "No recent activity recorded.")} />
            <Field label="current mission" value={text(presence?.current_mission?.title, "None")} />
            <Field label="current outcome" value={text(presence?.current_outcome?.title, "None")} />
            <Field label="Current Assignment Count" value={numberText(presence?.current_assignment_count)} />
            <Field label="owned assignments" value={numberText(asRecord(presence?.assignment_counts).owned)} />
            <Field label="contributor assignments" value={numberText(asRecord(presence?.assignment_counts).contributor)} />
            <Field label="assignments waiting" value={numberText(asRecord(presence?.assignment_counts).waiting)} />
            <Field label="assignments blocked" value={numberText(asRecord(presence?.assignment_counts).blocked)} />
            <Field label="assignments in review" value={numberText(asRecord(presence?.assignment_counts).review)} />
            <Field label="current room" value={presence?.current_room ? `#${presence.current_room}` : "None"} />
            <Field label="current task" value={presence?.current_task_id || "None"} />
            <Field label="suggested action" value={text(presence?.suggested_action, suggestedRuntimeAction(runtime, dependency))} />
          </div>
        </Panel>
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
          <p className="text-sm text-slate-200">{text(presence?.attention_reason, explainRuntimeIssue(runtime))}</p>
          <p className="mt-3 text-xs text-slate-300">Impact: {operatorWorkerImpact(operatorStatus, runtime, presence)}</p>
          <p className="mt-3 text-xs text-muted">Room context: {dependency}</p>
          <p className="mt-3 text-xs text-amberop">Suggested action: {text(presence?.suggested_action, suggestedRuntimeAction(runtime, dependency))}</p>
          <p className="mt-3 text-xs text-muted">Raw status: {text(reputation.incident_summary || runtime.incident_summary || workerHealth(runtime), "none")}</p>
        </Panel>
        <MemoryScopePanel memories={memories} scopeType="runtime" scopeId={id} />
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
  data,
  rooms,
  workers,
  proposals,
  selectedRoom,
  roomDetail,
  roomError,
  message,
  member,
  createName,
  createPreset,
  createMode,
  searchQuery,
  notice,
  sending,
  lastDispatch,
  onSelectRoom,
  onMessage,
  onMember,
  onCreateName,
  onCreatePreset,
  onCreateMode,
  onSearchQuery,
  onCreateRoom,
  onDeleteRoom,
  onAddAllWorkers,
  onRefreshRoom,
  onSearchRoom,
  onSummarizeRoom,
  onSend,
  onMemberAction,
}: {
  data: AppData;
  rooms: Room[];
  workers: Agent[];
  proposals: Proposal[];
  selectedRoom: string;
  roomDetail: RoomDetail;
  roomError?: string;
  message: string;
  member: string;
  createName: string;
  createPreset: string;
  createMode: RoomOperationMode;
  searchQuery: string;
  notice?: string | null;
  sending: boolean;
  lastDispatch?: DispatchResponse | null;
  onSelectRoom: (room: string) => void;
  onMessage: (value: string) => void;
  onMember: (value: string) => void;
  onCreateName: (value: string) => void;
  onCreatePreset: (value: string) => void;
  onCreateMode: (value: RoomOperationMode) => void;
  onSearchQuery: (value: string) => void;
  onCreateRoom: () => void;
  onDeleteRoom: () => void;
  onAddAllWorkers: () => void;
  onRefreshRoom: () => void;
  onSearchRoom: () => void;
  onSummarizeRoom: () => void;
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
  const selectedRoomExists = rooms.some((room) => text(room.name, "") === selectedRoom);
  const selectedRoomRecord = rooms.find((room) => text(room.name, "") === selectedRoom) || roomDetail.room;
  const activeWorkers = (selectedRoomRecord?.most_active_workers || [])
    .map((item) => `${text(item.runtime, "runtime")} (${numberText(item.events)})`)
    .join(", ");
  const localRoomWarning = roomError || (!selectedRoomExists ? roomMissingWarning(selectedRoom) : "");
  const memberIds = members.map((item) => text(item.adapter_id || item.id, "")).filter(Boolean);
  const presentWorkers = memberIds
    .map((id) => presenceForRuntime(id, data.workforcePresence))
    .filter(Boolean) as WorkforcePresenceWorker[];
  const activeCount = presentWorkers.filter((item) => item.presence_state === "active").length;
  const idleCount = presentWorkers.filter((item) => item.presence_state === "idle").length;
  const attentionCount = presentWorkers.filter((item) => item.needs_attention || item.presence_state === "needs_attention").length;
  const recentBroadcasts = roomDetail.messages.filter((item) => text(item.source, "") === "operator" || text(item.source, "").startsWith("synkraken-")).slice(-4);
  const recentReplies = roomDetail.messages.filter((item) => memberIds.includes(text(item.source, ""))).slice(-4);
  const roomDeadLetters = data.deadLetters.map(asRecord).filter((item) => text(item.target || item.original_target || item.reply_context, "").includes(`room:${selectedRoom}`));
  const latestMessage = roomDetail.messages[roomDetail.messages.length - 1];
  const lastBroadcast = [...roomDetail.messages].reverse().find((item) => text(item.source, "") === "operator");
  const deliveries = lastDispatch?.deliveries || [];
  const injectedIds = Array.from(new Set(deliveries.flatMap((delivery) => (delivery.injected_memory_ids || []) as string[])));
  const roomAssignments = data.assignments.filter((assignment) =>
    assignment.room_id === selectedRoom
    || memberIds.includes(text(assignment.owner_worker, ""))
    || (assignment.contributor_workers || []).some((workerIdValue) => memberIds.includes(workerIdValue)),
  );
  const blockedRoomAssignments = roomAssignments.filter((assignment) => assignment.status === "blocked");
  const roomHandoffs = data.recentHandoffs.filter((handoff) => roomAssignments.some((assignment) => assignmentId(assignment) === handoff.assignment_id));

  return (
    <div className="rooms-screen">
      <div className="rooms-topbar">
        <div>
          <SectionHeader title="Conversations" subtitle="Talk to the workforce. Management and diagnostics stay in drawers until needed." />
        </div>
      </div>
      <div className="rooms-layout">
        <aside className="rooms-column rooms-left">
          <div className="rooms-column-header">
            <h3>Conversations</h3>
            <button className="micro-btn" onClick={onRefreshRoom}>refresh</button>
          </div>
          <div className="room-list-scroll">
            {allRooms.map((room) => {
              const name = text(room.name, "room");
              return (
                <button key={name} className={`room-tab ${selectedRoom === name ? "room-tab-active" : ""}`} onClick={() => onSelectRoom(name)}>
                  <span>#{name}</span>
                  <span>{numberText(room.member_count)} members</span>
                </button>
              );
            })}
          </div>
          <div className="room-create-panel">
            <select className="input" value={createMode} onChange={(event) => onCreateMode(event.target.value as RoomOperationMode)}>
              <option value="create">Create room</option>
              <option value="preset">Create preset</option>
            </select>
            {createMode === "preset" && (
              <select className="input" value={createPreset} onChange={(event) => onCreatePreset(event.target.value)}>
                <option value="ops">ops</option>
                <option value="review">review</option>
                <option value="planning">planning</option>
              </select>
            )}
            <input className="input" value={createName} onChange={(event) => onCreateName(event.target.value)} placeholder="room-name" />
            <button className="btn-cyan w-full" onClick={onCreateRoom}>Create Room</button>
            <div className="grid grid-cols-2 gap-2">
              <button className="btn" onClick={onRefreshRoom}>Refresh</button>
              <button className="btn-danger" onClick={onDeleteRoom}>Delete</button>
            </div>
            <button className="btn w-full" disabled title="Daemon API gap: no room rename endpoint">Rename unavailable</button>
          </div>
        </aside>

        <main className="rooms-column rooms-chat">
          <header className="room-chat-header">
            <div>
              <h2>#{selectedRoom}</h2>
              <p>{recentReplies.length ? `${recentReplies.length} recent replies` : "No recent replies"} · {members.length || roomDetail.room?.member_count || 0} workers available</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn" onClick={() => onMessage("@everyone Who is available?")}>@everyone</button>
              <button className="btn" onClick={onSearchRoom}>Search conversation</button>
              <button className="btn" onClick={onSummarizeRoom}>Summarise</button>
            </div>
          </header>
          {localRoomWarning && (
            <div className="room-warning">
              <strong>{localRoomWarning}</strong>
              <span>Create room or select another room.</span>
            </div>
          )}
          {notice && <div className="room-notice">{notice}</div>}
          <div className="room-chat-transcript" data-fixed-height="room-transcript-scroll">
            {roomDetail.messages.map((item) => (
              <article className={`message-row chat-row ${text(item.source, "") === "operator" ? "chat-row-operator" : memberIds.includes(text(item.source, "")) ? "chat-row-worker" : "chat-row-system"}`} key={item.message_id || `${item.source}-${item.timestamp}`}>
                <div className="message-meta">
                  <span>{text(item.source, "unknown") === "operator" ? "operator" : `@${text(item.source, "unknown")}`}</span>
                  <span>{shortDate(item.timestamp)}</span>
                </div>
                <TokenText value={text(item.body, "[empty reply] - worker responded without text.")} />
              </article>
            ))}
            {!roomDetail.messages.length && <EmptyPanel label={members.length ? "No replies yet. Check delivery results or worker status." : "This room has no workers yet. Add workers or use Add All."} />}
          </div>
          <form className="room-chat-composer" data-sticky-composer="true" onSubmit={(event) => { event.preventDefault(); onSend(); }}>
            <textarea
              className="textarea room-chat-input"
              value={message}
              onChange={(event) => onMessage(event.target.value)}
              onKeyDown={(event) => {
                if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                  event.preventDefault();
                  onSend();
                }
              }}
              placeholder="Use @everyone or @worker-id to dispatch. Plain text records a room note."
              disabled={sending}
            />
            <div className="composer-footer">
              <span>Use @everyone or @worker-id to dispatch. Plain text records a room note.</span>
              <button className="btn-cyan" type="submit" disabled={sending || !message.trim()}>{sending ? "Sending..." : "Send"}</button>
            </div>
            {localRoomWarning && <div className="composer-error">Cannot send until the room exists or another room is selected.</div>}
          </form>
        </main>

        <aside className="conversation-drawer-stack">
          <details className="room-side-details">
            <summary>Members · {members.length}</summary>
            <section className="member-controls">
            <div className="rooms-column-header">
              <h3>Members</h3>
            </div>
            <div className="flex gap-2">
              <input className="input" value={member} onChange={(event) => onMember(event.target.value)} placeholder="runtime id" list="runtime-list" />
              <button className="btn-cyan" onClick={() => onMemberAction("add", member)}>Add</button>
            </div>
            <button className="btn w-full" onClick={onAddAllWorkers}>Add All Workers</button>
            <datalist id="runtime-list">
              {workers.map((worker) => <option value={workerId(worker)} key={workerId(worker)} />)}
            </datalist>
            </section>
            <div className="room-member-list" data-independent-scroll="members">
            {members.map((memberRecord) => {
              const adapterId = text(memberRecord.adapter_id || memberRecord.id, "");
              const presence = presenceForRuntime(adapterId, data.workforcePresence);
              const memberWorker = workers.find((worker) => workerId(worker) === adapterId);
              const status = operatorWorkerStatus(memberWorker, presence);
              return (
                <div className="room-member-presence" key={adapterId}>
                  <div>
                    <strong>@{adapterId}</strong>
                    <span className={`pill presence-chip status-${operatorWorkerTone(status)}`}>{status}</span>
                  </div>
                  <p>{text(presence?.latest_activity_summary, "No recent activity recorded.")}</p>
                  {presence?.needs_attention && <p className="text-amberop">{presence.attention_reason}</p>}
                  <button className="micro-btn" onClick={() => onMemberAction("remove", adapterId)}>remove</button>
                </div>
              );
            })}
            {!members.length && <span className="text-sm text-muted">This room has no workers yet. Add workers or use Add All.</span>}
            </div>
          </details>
          <details className="delivery-summary">
            <summary>Delivery Results · {deliverySummary(deliveries)}</summary>
            <div className="mt-3 space-y-2">
              {deliveries.map((delivery, index) => <DeliveryRow delivery={delivery} key={`${text(delivery.delivery_target || delivery.adapter_id, "target")}-${index}`} compact />)}
              {!deliveries.length && <EmptyPanel label="No replies yet. Check delivery results or worker status." />}
            </div>
          </details>
          <details className="room-side-details">
            <summary>Knowledge and work context</summary>
            <div className="mini-list mt-3">
              <Field label="conversation knowledge" value={text(roomDetail.memory?.notes || roomDetail.memory?.current_focus || roomDetail.memory?.objective, "No room notes returned.")} />
              <Field label="included knowledge" value={injectedIds.length ? injectedIds.join(", ") : "No knowledge was included in the last dispatch."} />
              <Field label="most active workers" value={activeWorkers || "No worker activity"} />
              <Field label="last broadcast" value={lastBroadcast ? shortDate(lastBroadcast.timestamp) : "No broadcasts yet"} />
              <Field label="recent failures" value={roomDeadLetters.length} />
              {roomAssignments.slice(0, 5).map((assignment) => (
                <div className="mini-row" key={assignmentId(assignment)}>
                  <span>{assignmentTitle(assignment)}</span>
                  <span>{assignment.owner_worker || assignmentStatusLabel(assignment.status)}</span>
                </div>
              ))}
              {!roomAssignments.length && <span className="text-sm text-muted">No current assignments owned by workers in this room.</span>}
            </div>
            <div className="mt-3">
              <MemoryScopePanel memories={data.memories} scopeType="room" scopeId={selectedRoom} />
            </div>
          </details>
          <details className="room-side-details">
            <summary>Governance and diagnostics</summary>
            <div className="mini-list mt-3">
              {roomHandoffs.slice(0, 4).map((handoff, index) => (
                <div className="mini-row" key={text(handoff.handoff_id || index, String(index))}>
                  <span>{text(handoff.from_worker, "worker")} {"->"} {text(handoff.to_worker, "worker")}</span>
                  <span>{text(handoff.reason || handoff.context_summary, "Handoff")}</span>
                </div>
              ))}
              {roomProposals.slice(0, 4).map((proposal) => (
                <div className="mini-row" key={proposalId(proposal)}>
                  <span>{text(proposal.title, "proposal")}</span>
                  <span className={statusClass(proposal.status)}>{text(proposal.status)}</span>
                </div>
              ))}
              {!roomHandoffs.length && !roomProposals.length && <span className="text-sm text-muted">No room-linked proposals or handoffs returned.</span>}
            </div>
          </details>
        </aside>
      </div>
    </div>
  );
}

function DeliverySummaryPanel({ deliveries }: { deliveries: DeliveryRecord[] }) {
  return (
    <details className="delivery-summary mt-4" open>
      <summary>Delivery summary · {deliverySummary(deliveries)}</summary>
      <div className="mt-3 grid gap-2">
        {deliveries.map((delivery, index) => (
          <DeliveryRow delivery={delivery} key={`${text(delivery.delivery_target || delivery.adapter_id, "target")}-${index}`} compact />
        ))}
      </div>
    </details>
  );
}

function DeliveryRow({ delivery, compact = false }: { delivery: DeliveryRecord; compact?: boolean }) {
  const target = text(delivery.delivery_target || delivery.adapter_id, "unknown");
  return (
    <article className={`delivery-row ${compact ? "delivery-row-compact" : ""}`}>
      <div>
        <div className="font-mono text-sm text-slate-100">@{target}</div>
        <div className="mt-1 text-xs text-muted">{deliveryStatusCopy(delivery)}</div>
      </div>
      <span className={`pill ${deliveryTone(delivery)}`}>{deliveryStatusLabel(delivery)}</span>
      <Field label="duration" value={delivery.duration_ms == null ? "-" : duration(Number(delivery.duration_ms))} />
      <Field label="attempts" value={delivery.attempts || 1} />
      <div className="delivery-preview">
        <TokenText value={deliveryPreview(delivery)} />
      </div>
      <details className="raw-details delivery-details">
        <summary>Raw details</summary>
        <pre className="json-block mt-2">{prettyJson(delivery)}</pre>
      </details>
    </article>
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

function GovernanceView({
  proposals,
  pending,
  handoffs,
  onOpen,
  onAction,
  onReplay,
}: {
  proposals: Proposal[];
  pending: Proposal[];
  handoffs: HandoffRecord[];
  onOpen: (id: string) => void;
  onAction: (id: string, action: "approve" | "reject" | "execute") => void;
  onReplay: (id: string) => void;
}) {
  const executed = proposals.filter((proposal) => text(proposal.status, "") === "executed").slice(0, 8);
  const decided = proposals.filter((proposal) => ["approved", "rejected"].includes(text(proposal.status, ""))).slice(0, 8);
  return (
    <div className="space-y-6">
      <SectionHeader title="Governance" subtitle="Things waiting for your judgement." />
      <section className="governance-inbox" data-governance-inbox="Awaiting Review, Recent Decisions, Recent Handoffs, Executed Actions">
        <article className="home-card home-card-large">
          <div className="section-kicker">Awaiting Review</div>
          <ProposalRows proposals={pending} onOpen={onOpen} onAction={onAction} queue />
        </article>
        <article className="home-card">
          <div className="section-kicker">Recent Handoffs</div>
          <div className="mini-list">
            {handoffs.slice(0, 6).map((handoff, index) => {
              const id = text(handoff.handoff_id || handoff.assignment_id || index, String(index));
              return <button className="mini-row" key={id} onClick={() => onReplay(id)}><span>{text(handoff.from_worker, "worker")} {"->"} {text(handoff.to_worker, "worker")}</span><span>{text(handoff.status, "recorded")}</span></button>;
            })}
            {!handoffs.length && <p className="quiet-copy">No handoffs returned.</p>}
          </div>
        </article>
      </section>
      <section className="home-grid">
        <article className="home-card">
          <div className="section-kicker">Recent Decisions</div>
          <div className="mini-list">
            {decided.map((proposal) => <button className="mini-row" key={proposalId(proposal)} onClick={() => onOpen(proposalId(proposal))}><span>{text(proposal.title || proposal.summary, proposalId(proposal))}</span><span>{text(proposal.status, "decided")}</span></button>)}
            {!decided.length && <p className="quiet-copy">No recent approvals or rejections.</p>}
          </div>
        </article>
        <article className="home-card">
          <div className="section-kicker">Executed Actions</div>
          <div className="mini-list">
            {executed.map((proposal) => <button className="mini-row" key={proposalId(proposal)} onClick={() => onOpen(proposalId(proposal))}><span>{text(proposal.title || proposal.summary, proposalId(proposal))}</span><span>{shortDate(proposal.executed_at || proposal.created_at)}</span></button>)}
            {!executed.length && <p className="quiet-copy">No executed proposals returned.</p>}
          </div>
        </article>
      </section>
    </div>
  );
}

function SearchView({
  data,
  workers,
  rooms,
  onView,
  onSelectRoom,
  onSelectRuntime,
  onOpenProposal,
  onReplay,
}: {
  data: AppData;
  workers: Agent[];
  rooms: Room[];
  onView: (view: View) => void;
  onSelectRoom: (room: string) => void;
  onSelectRuntime: (runtime: string | null) => void;
  onOpenProposal: (id: string) => void;
  onReplay: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLowerCase();
  const results = [
    ...workers.map((worker) => ({
      kind: "Worker",
      title: workerId(worker),
      detail: `${operatorWorkerStatus(worker, presenceForWorker(worker, data.workforcePresence))} · ${explainRuntimeIssue(worker)}`,
      action: () => { onSelectRuntime(workerId(worker)); onView("workforce"); },
    })),
    ...rooms.map((room) => ({
      kind: "Conversation",
      title: `#${text(room.name, "room")}`,
      detail: room.last_activity ? `Last active ${shortDate(room.last_activity)}` : `${numberText(room.member_count)} workers`,
      action: () => { onSelectRoom(text(room.name, "ops")); onView("conversations"); },
    })),
    ...data.missions.map((mission) => ({
      kind: "Mission",
      title: missionTitle(mission),
      detail: `${text(mission.status, "active")} · ${text(mission.owner, "unassigned")}`,
      action: () => onView("work"),
    })),
    ...data.outcomes.map((outcome) => ({
      kind: "Outcome",
      title: outcomeTitle(outcome),
      detail: `${text(outcome.status, "not started")} · ${text(outcome.confidence, "medium")} confidence`,
      action: () => onView("work"),
    })),
    ...data.assignments.map((assignment) => ({
      kind: "Assignment",
      title: assignmentTitle(assignment),
      detail: `${assignmentStatusLabel(assignment.status)} · ${assignment.owner_worker || "unassigned"}`,
      action: () => onView("work"),
    })),
    ...data.memories.map((memory) => ({
      kind: "Knowledge",
      title: text(memory.title, memoryId(memory)),
      detail: `${text(memory.status, "proposed")} · ${text(memory.scope_type, "global")}`,
      action: () => onView("knowledge"),
    })),
    ...data.proposals.map((proposal) => ({
      kind: "Governance",
      title: text(proposal.title || proposal.summary, proposalId(proposal)),
      detail: `${text(proposal.status, "proposed")} · ${text(proposal.risk || proposal.risk_level, "risk")}`,
      action: () => onOpenProposal(proposalId(proposal)),
    })),
    ...data.deadLetters.map((item) => {
      const record = asRecord(item);
      const id = text(record.trace_id || record.message_id || record.delivery_id || record.dead_letter_id, "");
      return {
        kind: "Incident",
        title: text(record.summary || record.error || record.reason, id || "Delivery issue"),
        detail: text(record.target || record.original_target || record.status, "delivery issue"),
        action: () => { if (id) onReplay(id); else onView("incidents"); },
      };
    }),
    ...meaningfulActivity(data).map((item) => {
      const id = text(item.trace_id || item.activity_id || item.proposal_id, "");
      return {
        kind: "Trace",
        title: text(item.summary, id || "Activity"),
        detail: `${activityEventType(item)} · ${shortDate(item.timestamp)}`,
        action: () => { if (id) onReplay(id); else onView("activity"); },
      };
    }),
  ].filter((result) => {
    if (!normalized) return true;
    return `${result.kind} ${result.title} ${result.detail}`.toLowerCase().includes(normalized);
  }).slice(0, 40);

  return (
    <div className="search-screen">
      <SectionHeader title="Search" subtitle="Find workers, conversations, work, knowledge, incidents, and traces from one place." />
      <div className="spotlight-search">
        <input autoFocus className="input spotlight-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search SynKraken" />
        <div className="spotlight-results" data-global-search="workers, rooms, missions, outcomes, assignments, memory, incidents, traces">
          {results.map((result, index) => (
            <button className="spotlight-result" key={`${result.kind}-${result.title}-${index}`} onClick={result.action}>
              <span>{result.kind}</span>
              <strong>{result.title}</strong>
              <small>{result.detail}</small>
            </button>
          ))}
          {!results.length && <ExperienceEmptyState title="No results." body="Try a worker, room, outcome, assignment, knowledge note, incident, or trace id." action="Search" />}
        </div>
      </div>
    </div>
  );
}

function SettingsView({ data, daemonStatus, onRefresh }: { data: AppData; daemonStatus: DaemonStatus; onRefresh: () => void }) {
  return (
    <div className="space-y-6">
      <SectionHeader title="Settings" subtitle="Daemon status, runtime configuration context, and Console preferences." />
      <section className="home-grid">
        <article className="home-card">
          <div className="section-kicker">Daemon</div>
          <div className="compact-grid mt-3">
            <Field label="status" value={daemonStatus === "online" ? "Online" : "Offline"} />
            <Field label="endpoint" value={DAEMON_URL} />
            <Field label="started" value={shortDate(data.health?.started_at)} />
            <Field label="workspace" value={text(data.health?.default_workspace, "Local")} />
          </div>
          <button className="btn-cyan mt-4" onClick={onRefresh}>Refresh status</button>
        </article>
        <article className="home-card">
          <div className="section-kicker">Runtime configuration</div>
          <p className="quiet-copy">Runtime discovery, adapter setup, and service lifecycle remain daemon/CLI operations in this sprint.</p>
        </article>
        <article className="home-card">
          <div className="section-kicker">Console preferences</div>
          <p className="quiet-copy">Light macOS-style interface, operator-first navigation, and raw technical fields behind details are active for this redesign.</p>
        </article>
      </section>
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
    <div className="proposal-inbox-list">
      {proposals.map((proposal) => {
        const id = proposalId(proposal);
        return (
          <article className={`proposal-inbox-item ${queue ? "proposal-inbox-item-awaiting" : ""}`} key={id}>
            <div>
              <div className="proposal-inbox-meta">
                <span className={`pill ${statusClass(proposal.risk || proposal.risk_level)}`}>{text(proposal.risk || proposal.risk_level, "risk")}</span>
                <span>{shortDate(proposal.created_at)}</span>
                <span>{text(proposal.proposed_by || proposal.proposer, "unknown")}</span>
              </div>
              <button className="link-button proposal-title-button" onClick={() => onOpen(id)}>{text(proposal.title || proposal.summary, "Untitled proposal")}</button>
              <p>{text(proposal.summary || proposal.reason || proposal.body, "Review details before deciding.")}</p>
              <small>{text(proposal.room_id || proposal.room, "No room")} · {text(proposal.goal_id || proposal.goal, "No linked goal")}</small>
            </div>
            <ProposalActions id={id} onAction={onAction} />
          </article>
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
  data,
  workers,
  rooms,
  proposals,
  missions,
  outcomes,
  daemonStatus,
  workforceHealth,
  incident,
  deadLetters,
  onReplay,
}: {
  data: AppData;
  workers: Agent[];
  rooms: Room[];
  proposals: Proposal[];
  missions: Mission[];
  outcomes: Outcome[];
  daemonStatus: DaemonStatus;
  workforceHealth?: WorkforceHealthResponse;
  incident?: IncidentResponse;
  deadLetters: unknown[];
  onReplay: (id: string) => void;
}) {
  const attentionWorkers = workers.filter((worker) => {
    const presence = presenceForWorker(worker, data.workforcePresence);
    return presence?.needs_attention || displaySeverityForRuntime(worker) !== "Operational";
  });
  const activeIncidents = [
    ...attentionWorkers.map((worker) => {
      const presence = presenceForWorker(worker, data.workforcePresence);
      return {
        type: "runtime",
        runtime: workerId(worker),
        summary: text(presence?.attention_reason, explainRuntimeIssue(worker)),
        raw: worker,
        worker,
        presence,
      };
    }),
    ...deadLetters.slice(0, 8).map((item) => ({ type: "dead_letter", runtime: text(asRecord(item).adapter_id || asRecord(item).target, "unknown"), summary: text(asRecord(item).reason || asRecord(item).error, "Dead letter recorded."), raw: item })),
  ];
  const recentIncidents = (workforceHealth?.recent_incidents || []) as unknown[];
  const grouped = activeIncidents.reduce<Record<OperatorPriority, typeof activeIncidents>>(
    (groups, item) => {
      const presence = "presence" in item ? item.presence as WorkforcePresenceWorker | undefined : undefined;
      const inActiveRoom = Boolean(presence?.current_room && presence.presence_state !== "idle");
      const priority: OperatorPriority = daemonStatus === "offline"
        ? "Needs action now"
        : inActiveRoom || presence?.presence_state === "active"
          ? "Needs action now"
          : item.type === "dead_letter"
            ? "Historical / low impact"
            : "Watch list";
      groups[priority].push(item);
      return groups;
    },
    { "Needs action now": [], "Watch list": [], "Historical / low impact": [] },
  );

  return (
    <div className="space-y-4">
      <SectionHeader title="Incident Centre" subtitle="Prioritized runtime issues, dead letters, and operator recovery actions." />
      <OperatorSummary title="Incident Operator Summary" data={data} workers={workers} daemonStatus={daemonStatus} />
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="needs action now" value={grouped["Needs action now"].length} />
        <Metric label="watch list" value={grouped["Watch list"].length} />
        <Metric label="dead letters" value={deadLetters.length} />
        <Metric label="recent incident notes" value={recentIncidents.length} />
      </div>
      {(["Needs action now", "Watch list", "Historical / low impact"] as OperatorPriority[]).map((priority) => (
        <Panel title={priority} key={priority}>
          <div className="grid gap-4 xl:grid-cols-2">
            {grouped[priority].map((item, index) => (
              <IncidentCard
                item={item}
                rooms={rooms}
                proposals={proposals}
                missions={missions}
                outcomes={outcomes}
                priority={priority}
                onReplay={onReplay}
                key={`${item.type}-${item.runtime}-${index}`}
              />
            ))}
            {!grouped[priority].length && <EmptyPanel label={`No ${priority.toLowerCase()} items.`} />}
          </div>
        </Panel>
      ))}
      <details className="raw-details">
        <summary>Latest incident raw context</summary>
        <pre className="json-block mt-2">{prettyJson(incident || {})}</pre>
      </details>
    </div>
  );
}

function IncidentCard({
  item,
  rooms,
  proposals,
  missions,
  outcomes,
  priority,
  onReplay,
}: {
  item: { type: string; runtime: string; summary: string; raw: unknown; worker?: Agent; presence?: WorkforcePresenceWorker };
  rooms: Room[];
  proposals: Proposal[];
  missions: Mission[];
  outcomes: Outcome[];
  priority: OperatorPriority;
  onReplay: (id: string) => void;
}) {
  const raw = asRecord(item.raw);
  const replayId = text(raw.message_id || raw.conversation_id || raw.delivery_id || raw.dead_letter_id, "");
  const severity = item.worker ? humanHealthFromPresence(item.presence, item.worker) : "Needs attention";
  const impact = item.presence?.presence_state === "active" || item.presence?.current_room ? "Medium" : displayImpactForIncident(item);
  const affectedMission = affectedMissionForIncident(raw, missions);
  const affectedOutcome = affectedOutcomeForIncident(raw, outcomes);
  const dependency = affectedOutcome ? `Outcome impacted: ${outcomeTitle(affectedOutcome)}` : affectedMission ? `Mission Impact: ${missionTitle(affectedMission)}` : item.presence?.current_room ? `Used in #${item.presence.current_room}` : item.worker ? runtimeRoomDependency(item.worker, rooms, proposals) : text(raw.room || raw.room_id || raw.target, "No active room dependency detected");
  const suggested = item.presence?.suggested_action || (item.worker ? suggestedRuntimeAction(item.worker, dependency) : "Inspect replay before retrying.");
  return (
    <article className={`incident-card incident-card-${priority === "Needs action now" ? "critical" : priority === "Watch list" ? "watch" : "muted"}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-mono text-lg text-slate-50">{item.runtime}</h2>
          <div className={`mt-1 text-sm ${displaySeverityTone(severity) === "danger" ? "text-danger" : displaySeverityTone(severity) === "warn" ? "text-amberop" : "text-cyanop"}`}>Severity: {severity}</div>
        </div>
        {replayId && <button className="btn" onClick={() => onReplay(replayId)}>Trace</button>}
      </div>
      <p className="mt-4 text-sm text-slate-200">{item.summary}</p>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <Field label="impact" value={impact} />
        <Field label="priority" value={priority} />
        <Field label="presence" value={presenceLabel(item.presence?.presence_state)} />
        <Field label="affected work" value={dependency} />
        <Field label="raw health" value={item.worker ? workerHealth(item.worker) : text(raw.status || raw.outcome, "dead letter")} />
        <Field label="first seen" value={shortDate(raw.created_at || raw.last_failure)} />
        <Field label="last seen" value={shortDate(raw.updated_at || raw.created_at || raw.last_seen)} />
      </div>
      <div className="mt-4 border-t border-line pt-3 text-sm">
        <span className="text-muted">Suggested action: </span>
        <span className="text-amberop">{suggested}</span>
      </div>
      <details className="raw-details mt-3">
        <summary>Raw incident data</summary>
        <pre className="json-block mt-2">{prettyJson(item.raw)}</pre>
      </details>
    </article>
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
            <button key={workerId(worker)} className="command-row" onClick={() => { onRuntime(workerId(worker)); onClose(); }}>Focus Worker: {workerId(worker)}</button>
          ))}
          {proposalMatches.map((proposal) => (
            <button key={proposalId(proposal)} className="command-row" onClick={() => { onProposal(proposalId(proposal)); onClose(); }}>Search Governance · {proposalId(proposal)} · {text(proposal.title, "untitled")}</button>
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
    <div className="mx-5 mt-5 rounded-xl border border-amberop/40 bg-amberop/10 p-6">
      <h2 className="text-lg font-semibold text-slate-50">SynKraken is not running</h2>
      <p className="mt-2 text-sm text-slate-300">{message}</p>
      <p className="mt-3 text-sm text-muted">Run <code>synkraken install</code> if recovery continues to fail.</p>
      <button className="btn mt-4" onClick={onRefresh}>Try recovery again</button>
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
        Ctrl+K · Home · Projects · Conversations · Knowledge · Workforce · Advanced
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

function ExperienceEmptyState({ title, body, action }: { title: string; body: string; action: string }) {
  return (
    <section className="experience-empty-state">
      <div>
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
      <button className="btn-cyan" disabled title="The daemon does not expose this direct create action yet.">
        {action}
      </button>
    </section>
  );
}
