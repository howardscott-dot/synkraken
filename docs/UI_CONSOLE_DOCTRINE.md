# UI Console Doctrine

SynKraken Console is the native desktop operations surface for the SynKraken
daemon. It is a Tauri shell with React/TypeScript UI over daemon HTTP APIs.
It does not own SQLite state, duplicate governance logic, or become a second
backend.

## UI Principles

- truth over polish
- weak outputs visible
- no fake telemetry
- no hidden failures
- operator-first density
- Operator First Interface: speak in goals, decisions, and next actions before
  exposing system objects
- Calm Operations: reduce cognitive load rather than amplifying it
- premium native dark style with restraint, whitespace, and system typography
- raw records available as drill-down, not the primary experience
- proposal controls use existing governance endpoints only
- Calm Truth: expose real failures without exaggerating urgency
- a workforce operating system should show what workers are doing, not only
  whether they passed health checks
- Living Workforce UX: the Console should feel like entering a workplace, not
  opening an administrative dashboard
- Project-Centric Company OS: the Console should organise daily work around
  projects, conversations, knowledge, deliverables, team, and decisions

## Display Severity

Console may map daemon-owned raw health into operator-facing display severity
without changing backend state:

- `healthy` -> Operational
- `degraded` -> Needs attention
- `unstable` -> Degraded
- `failing` -> Needs attention by default

Blocked and Critical are reserved for active work impact: daemon offline,
blocked current workflow, execution failure, active incident affecting current
work, or a dead letter that blocks retry/replay. Raw health must remain visible
in details, tool surfaces, or raw data.

## App Shell

The shell provides persistent navigation, daemon status, workforce summary
signals, and command access. It should make the operator's current context
obvious without hiding failures.

Console navigation starts from company operating intent:

- Home: deterministic workforce briefing answering what happened, what needs
  the operator, and what to do next.
- Projects: the centre of daily operation.
- Conversations: where the operator talks to the workforce.
- Knowledge: what the workforce knows.
- Workforce: whether workers can be used and what they are good for.
- Advanced: technical inspection for internals.

Advanced contains Governance, Assignments, Outcomes, Missions, Traces, Canvas,
Incidents, Runtime Diagnostics, Proposal Internals, Dead Letters, and Memory
Internals. Canvas is advanced inspection only and never a primary workflow.

The ordering principle is:

- Conversation first.
- Work second.
- Governance third.
- Diagnostics last.

In v2.0 the daily operating target is: create a project, talk to workers,
store knowledge, review deliverables, and make decisions without opening
Advanced.

Console must prefer operations before observability for the core AI workforce
loop. If an operator can inspect rooms but cannot create rooms, add workers,
message workers, see replies, and inspect delivery failures from Console, the
Console is incomplete.

The top-level live summary should answer:

- how many workers are active now
- how many recent events are visible
- how long ago the last activity happened

These values must come from daemon records. Do not use model-generated
summaries, inferred future work, scheduler state, or client-invented telemetry.

## Activity

The Activity screen answers "what happened?" It is a timeline-first
deterministic feed over durable daemon records such as messages, deliveries,
proposal events, handoffs, decisions, and dead letters.

Each event should read as a sentence before exposing fields. Filters and raw
records are secondary disclosures. Activity is awareness only. It must not add
autonomy, scheduling, execution, planning agents, or AI-generated summaries.

## Knowledge

Knowledge is the operator-facing name for visible Shared Workforce Memory. It
should feel closer to Apple Notes, Obsidian, or Craft than a database browser.
It should group records into Company, Projects, People, Technical, Lessons
Learned, and Pending Review.

Filters for type, scope, importance, and status are secondary controls, not
the default mental model. Approval, rejection, and archive actions must call
daemon memory governance endpoints.

Room, Mission, Outcome, Assignment, and Runtime detail surfaces may show
approved memory for the current scope. Canvas may include a read-only Memory
node. Console must not invent hidden memory, summarize memory with an AI model,
or promote memory automatically.

## Operational Briefing

Operational Briefing is the top-level work-state read model. It should help
the operator understand the state of the work in under 30 seconds: what is
active, what is blocked, what changed, what requires attention, and what to
review next.

Briefing is deterministic. It derives from existing daemon records for
workforce presence, missions, outcomes, assignments, proposals, incidents,
dead letters, and recent activity. It must not call an AI model, generate
summaries, create plans, schedule work, infer project-management state, or
execute workflow automation.

In Console v1.5, Home absorbs the briefing role. It should feel like opening a
premium native work app: a clear title, plain-English workforce status,
recommended actions, active work, rooms, pending approvals, workers to monitor,
and recent replies. It should not start with raw tables or equal-weight
technical panels.

In Console v1.6, Home becomes a chief-of-staff briefing. It must use
conversational tone without AI-generated summaries and must be derived entirely
from daemon state. It should answer what happened, what needs the operator,
and what to do next in under five seconds.

In Console v2.0, Home becomes Company Briefing. It should foreground active
projects, submitted proposals as decisions, workers waiting on approval, review
counts, and the next project action.

## Projects

Projects are the primary operator-facing workspace. A project may aggregate
missions, outcomes, assignments, knowledge, conversations, decisions,
deliverables, workers, handoffs, traces, and incidents, but the operator
should not need to understand those implementation records.

Project detail tabs are:

- Overview
- Conversations
- Knowledge
- Deliverables
- Team
- Decisions

Overview shows purpose, current status, recent activity, recommended next
actions, open deliverables, and workers involved. It must avoid governance and
implementation jargon.

Conversations is the default working surface. Knowledge hides memory
implementation details. Deliverables are visible outputs such as PRDs,
research, proposals, architecture, code reviews, articles, specifications, and
reports. Team shows current focus, recent contribution, and status without raw
health/trust metrics. Decisions is the human-facing version of governance.

In v2.1, a project should feel like a living workspace, not a summary page.
The Overview starts with a project narrative: name, purpose, current focus,
latest meaningful activity, and recommended next action. Deliverables are hero
objects. The project activity feed translates durable events into operator
language. Conversations, knowledge editing, deliverable review, team
contribution, and decisions must be usable inside the project without sending
the operator to Conversations, Knowledge, Workforce, or Advanced for normal
work.

In v2.2, each project gains a Project Co-Pilot at the top of Overview. This is
not an AI assistant and must not call a model. It is a deterministic project
assistant over existing conversations, deliverables, proposals, decisions,
workforce activity, knowledge, assignments, and handoffs. It should show
plain-language project health, up to five recommended next actions, and a
single project Inbox so the operator can understand what happened, what needs
attention, and what to do next without visiting multiple tabs.

Briefing should include:

- Workforce Snapshot: Available, Monitor, Avoid, Unavailable.
- Mission Snapshot: active, completed, and at-risk missions.
- Outcome Snapshot: open, completed, and blocked outcomes.
- Assignment Snapshot: assigned, in progress, waiting, and blocked work.
- Recent Activity: most meaningful durable events.
- Needs Operator Review: proposal approvals, blocked assignments, and critical
  incidents.
- Recommended Next Actions: at most five deterministic actions prioritized
  from approval pressure, blockers, owner gaps, stale waiting assignments,
  blocked outcomes, at-risk missions, and incidents.

Mission health labels are Healthy, Watching, and At Risk. Outcome health
labels are On Track, Watching, and Blocked. Assignment health labels are
Assigned, In Progress, Waiting, and Blocked. These labels are display
classification only; they do not mutate daemon state.

## Mission Centre

Mission Centre shows missions as first-class governance objects alongside
workers, rooms, incidents, proposals, and traces. The screen should answer
"which missions are progressing?" without becoming a project management
system.

The top summary should show active, blocked, review, and completed missions.
The primary table should show Mission, Status, Priority, Workers, Recent
Activity, Open Proposals, Incidents, and Last Updated. Selecting a mission
opens a governance cockpit with overview, workers, recent activity, linked
proposals, linked incidents, related traces, outcome, and risk.

Mission Centre must not introduce scheduling, boards, due dates, gantt charts,
sprints, tickets, estimates, or workload-specific entities. Mission data comes
from daemon read models and links; Console does not infer progress.

Mission progress is derived from linked outcomes, not from worker activity or
message volume.

## Outcome Centre

Outcome Centre is the primary value surface. It shows whether desired results
are completed, progressing, in review, blocked, or cancelled.

The top summary should show Completed, In Progress, Review, and Blocked
outcomes. The primary table should show Outcome, Mission, Status, Confidence,
Workers, Recent Activity, Open Proposals, Incidents, and Last Updated.
Selecting an outcome opens a governance cockpit with overview, mission context,
workers contributing, recent activity, evidence, linked proposals, linked
incidents, decision history, confidence, and status.

Outcome Centre must keep workers in the background as infrastructure.
Outcomes are value. Do not add scheduling, tasks, boards, tickets, estimates,
or AI-generated progress summaries.

## Assignment Centre

Assignment Centre makes workforce accountability visible without becoming
project management software. It should answer who owns work, who contributes,
what is waiting, what is blocked, what needs review, and what is complete.

The screen should group assignments by Assigned, In Progress, Waiting,
Blocked, Review, and Completed. Assignment cards should show Title, Owner,
Contributors, Mission, Outcome, Status, and Last Activity. Selecting an
assignment opens a detail cockpit with description, owner, contributors,
timeline, activity, handoffs, related room, related outcome, related mission,
related proposals, and related traces.

The Console may create assignments, assign an owner, add/remove contributors,
mark waiting, mark blocked, request review, complete, and hand off ownership
through daemon APIs. These are explicit operator actions. Console must not
automatically reassign, escalate, complete, or schedule assignment work.

Handoff Timeline is an accountability visualization. It should show the owner
chain, reason, context summary, and timestamp in a compact readable form.

## Spatial Canvas

The canvas is advanced mode, not the default workspace. It presents workforce
objects as movable nodes and daemon-backed relationships where available. It
is for spatial inspection, not marketing visuals.

Runtime nodes may show subtle active, idle, and attention indicators. Keep them
quiet; a simple pulse for active state is enough. Indicators must reflect
daemon-derived presence and should never imply background autonomy.

Briefing, Mission, Outcome, and Assignment nodes may appear in Operations,
Research, and Incident Response presets when daemon records exist. Mission
relationships should connect to outcomes, workers, rooms, incidents,
proposals, and assignments only where the daemon returns evidence-backed
relationship records. Outcome relationships should connect to missions,
assignments, workers, proposals, incidents, and traces. Assignment
relationships should connect ownership and contributor workers without
enabling canvas editing. The Briefing node summarizes active missions, blocked
assignments, pending proposals, and recommended actions.

## Workforce

The workforce screen is a worker directory first and a telemetry table second.
It helps the operator decide whether a worker can be used, what it is good
for, what is wrong, and what to do next.

The primary surface should use display severity and plain-English issue/action
copy. Raw health, trust, latency, durations, and reputation remain available
as detail fields rather than dominant labels.

Console may translate raw health, presence, and reputation into operator
worker categories without changing daemon state:

- Available: safe for normal work.
- Monitor: usable, but watch replies or retry behavior.
- Avoid for now: not reliable for active work; remove from active rooms if it
  is noisy or blocking.
- Unavailable: cannot be used until the runtime is available.

Each worker row should answer whether the worker can be used, what is wrong,
the impact, and the recommended action. Raw health, trust, latency, and
reputation details remain available in compact details or the worker drawer.

The primary workforce experience should be presence-aware. Workers should be
classified in human-operational terms:

- Active: recently produced useful output, message, proposal, handoff, or
  delivery.
- Idle: available and healthy enough, but not doing recent work.
- Watching: associated with a room or monitoring context without recent output.
- Needs attention: weak health, repeated empty replies, identity mismatch,
  timeout, delivery failure, or low reputation.
- Unavailable: disabled, registry-only, offline, or command unavailable.
- Unknown: insufficient evidence.

Presence does not replace raw health. It is a deterministic Console/API read
model that answers what a worker is doing and whether the operator should care
right now.

Workforce tables should show Current Activity, Current Assignment Count, Last
Meaningful Action, and Seconds Since Activity. Worker detail should expose
owned assignments, contributor assignments, waiting assignments, blocked
assignments, and assignments in review. These labels should be derived from
persisted presence/activity records, not client-side speculation.

## Conversations

Conversations expose persistent operational spaces: messages, room notes,
worker replies, and dispatches.

Conversations should feel closer to Messages, ChatGPT, or Claude than Slack
admin tools. The transcript should occupy the majority of the screen. Room
list is secondary. Members, knowledge, assignments, delivery results,
proposals, handoffs, and diagnostics belong behind drawers.

Delivery results should be human-readable by default: replied, empty reply,
timeout, failed, blocked, and suspicious output. Rows should show target,
status, duration, attempts, and preview. Raw delivery details may be
expandable, but raw JSON is not the default room experience.

Conversations should target roughly 80 percent conversation and 20 percent
management. The composer should be multiline, paste-safe, and support
Ctrl+Enter or Cmd+Enter to send.

If the daemon has no API for an action, Console should say so clearly instead
of faking it. Room rename and bulk remove-all-members are unavailable until the
daemon exposes those capabilities.

Room member lists should show member presence and latest activity where the
daemon can derive it. Empty rooms should use calm guidance rather than failure
language.

Room live context should show most active workers, last room event, and
activity rate from persisted room messages. This gives operational awareness
without summarizing or assigning work.

When a conversation is linked to an active, blocked, or review mission,
Conversations may show the mission association as context. It should be a
governance link, not an assignment or schedule.

When an outcome is linked to the current conversation context, Conversations
may show Current Outcome beside Current Mission.

Conversations should also show current assignments owned by room workers,
recent handoffs, and blocked assignments when daemon records provide that
context. This tells the operator who owns work without reading the whole
transcript.

## Proposal Governance

Proposal screens show pending and historical proposals, risk, approval
requirements, proposer, linked records, and approve/reject/execute controls.
Execution remains under the daemon governance model.

## Flight Recorder / Trace Explorer

Trace and replay screens explain what happened. They should make messages,
deliveries, dead letters, decisions, handoffs, proposals, goals, memory
markers, and failures inspectable.

## Incident Centre

The Incident Centre surfaces failing runtimes, dead letters, latest incident
context, recovery hints, and trace/replay links. Incidents should be visible
operational facts, not hidden behind raw JSON.

Incident presentation should group records by operator priority:

- Needs action now
- Watch list
- Historical / low impact

Most runtime failures belong in Watch list unless they block active work. Dead
letters and historic failures should be visible but muted unless they affect
current rooms, proposals, goals, retries, or replays.

Presence can move an issue between groups: a failing idle runtime is usually
Watch list, while a failing runtime in an active room or recent proposal/goal
belongs in Needs action now.

When an incident is linked to a mission, Incident Centre should show Mission
Impact so the operator can see affected outcomes quickly.

When an incident is linked to an outcome, Incident Centre should show the
affected outcome first because outcomes are the value object.

## Command Palette

The command palette is for fast navigation and object focus: open major
screens, focus runtime/proposal/trace/room objects, switch canvas workspaces,
and run local UI commands.

## Inspector

The Canvas Inspector shows selected-node detail and relationship jumps. It is
a drilldown surface over daemon data, not a client-owned model.

## Status Bar

The status bar should distinguish daemon health from endpoint or node-specific
errors. Only `/health` controls daemon online/offline status. Background
polling should not blank the UI or hide previous data.

The global status bar should describe usability in human terms, such as
`Usable with issues`, and reserve red for daemon offline or active blocked
work.
