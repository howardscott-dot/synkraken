# Operator Guide

Install SynKraken with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/howardscott-dot/synkraken/main/scripts/install.sh | bash
```

The installer clones SynKraken to `~/.synkraken/src`, creates a private venv
at `~/.synkraken/venv`, adds command shims to `~/.local/bin`, and launches
setup so you can choose local workers or SSH workers.

## Start The Daemon

```bash
cd ~/.synkraken/src
synkraken-daemon --config ./config.local.json
```

With the user service installed:

```bash
./scripts/install-user-service.sh
synkraken start daemon
synkraken status
```

## Discover The Workforce

```bash
synkraken discover
synkraken discover --json --verbose
synkraken agents
synkraken workforce
synkraken health workforce
```

Use `synkraken config --rediscover` when local runtimes change.

## Open Console

```bash
cd apps/console
npm install
npm run tauri dev
```

Or from the repo root:

```bash
npm run console:dev
```

## Start At Home

Open Console Home to read the Company Briefing before inspecting individual
workers or objects. Home is deterministic and uses existing daemon records; it
does not summarize with AI, plan work, or schedule work.

Use Home to answer:

- what happened
- what needs attention
- what is active
- what is blocked
- what changed recently
- what requires operator review
- what to do next
- where to talk to the workforce

Recommended Next Actions are capped at five and come from explicit rules over
proposal approvals, blocked assignments, missing mission ownership, waiting
assignments, blocked outcomes, at-risk missions, and incidents.

Console v2.0 uses a project-centric Company OS model:

- Projects first.
- Conversations inside projects.
- Knowledge and deliverables visible.
- Decisions human-facing.
- Advanced for inspection.

Use Projects as the primary place to organise company work. Use Conversations
inside a project to talk to the workforce. Use Knowledge to store project
context. Use Deliverables to review outputs. Use Decisions to approve or
reject work. Use Advanced only when you need internals.

## Use Projects

Open Console Projects to create and operate project workspaces.

A project gathers:

- conversations
- knowledge
- deliverables
- team activity
- decisions

Project tabs:

- Overview: purpose, status, recent activity, next actions, open
  deliverables, and workers involved.
- Conversations: the default working surface for talking to workers.
- Knowledge: project context such as positioning, requirements, architecture,
  research, and lessons learned.
- Deliverables: PRDs, research, proposals, architecture, code reviews,
  articles, specifications, and reports.
- Team: workers involved, current focus, recent contribution, and status.
- Decisions: pending decisions, approved decisions, rejected decisions, and
  recent handoffs.

Create a project before assigning substantial work. Project creation also
creates or reuses a matching conversation room where daemon APIs allow it.

## Inspect Health

Use the Console Workforce Command Centre or:

```bash
synkraken health
synkraken workforce
synkraken runtime health <runtime-id>
```

Health statuses are operational hints: `healthy`, `degraded`, `unstable`, and
`failing`.

In Console, raw health is mapped into calmer operator-facing severity:
Operational, Needs attention, Degraded, Blocked, or Critical. This does not
change daemon health. It helps distinguish noisy or unused runtime issues from
work that needs action now. Treat red as daemon offline or active blocked work;
amber usually means inspect, restart, or remove a runtime only if current work
depends on it.

Console Workforce also shows operator worker categories:

- Available: use normally.
- Monitor: usable, but watch replies or retry behavior.
- Avoid for now: do not rely on this worker for active work; remove it from
  active rooms if it is noisy.
- Unavailable: runtime cannot be used until it is available again.

Open the worker drawer for raw health, trust, reputation, trace links, and
technical details.

## Inspect Presence And Activity

Open Console Home or Workforce. The operator summary answers whether the
workforce is usable, how many workers are active or idle, who needs attention,
and what to inspect next. Canvas is available as advanced spatial inspection,
not the default starting point.

Presence states:

- Active: the worker recently produced useful output or touched work.
- Idle: the worker is available but has no recent activity.
- Watching: the worker is associated with a room or monitoring context.
- Needs attention: the worker has weak output, reputation, timeout, identity,
  or delivery signals.
- Unavailable: the runtime is disabled, registry-only, offline, or not ready.
- Unknown: SynKraken does not have enough records yet.

Open Search for one Spotlight-style surface across workers, conversations,
missions, outcomes, assignments, knowledge, incidents, traces, and governance
records. Activity remains available contextually as a timeline when you need
to inspect what happened recently.

The top summary bar shows active workers now, recent events, and how many
seconds ago the last activity occurred. Presence and Activity do not change
daemon health, schedule work, execute actions, or assign workers
automatically.

## Advanced Work Internals

Open Advanced for missions, outcomes, and assignments. These are implementation
records behind Projects and should not be required for daily operation.

## Review Missions

In Work, use the Missions tab to answer "which missions are progressing?" A
mission is a governance container around meaningful work. It is not a task,
project, ticket, board, or schedule.

Mission Centre shows:

- Active, blocked, review, and completed mission counts.
- A mission table with status, priority, workers, recent activity, open
  proposals, incidents, and last updated time.
- A mission detail cockpit with overview, workers involved, recent activity,
  linked proposals, linked incidents, related traces, outcome, and risk.

Use mission context to understand which workers, rooms, incidents, proposals,
and traces are connected to an outcome. Do not treat missions as a scheduling
system; SynKraken records and governs work rather than planning calendars.

Mission progress comes from outcomes. For example, `2 / 5 outcomes completed`
means 40 percent progress. It is not calculated from message volume or worker
busyness.

## Review Outcomes

In Work, use the Outcomes tab to answer "which outcomes are progressing?" and
"which outcome needs my approval?" Outcomes are the primary success object.
Workers are infrastructure; outcomes are value.

Outcome Centre shows:

- Completed, in-progress, review, and blocked outcome counts.
- An outcome table with mission, status, confidence, workers, recent activity,
  open proposals, incidents, and last updated time.
- An outcome detail cockpit with overview, mission context, workers
  contributing, recent activity, evidence, linked proposals, linked incidents,
  decision history, confidence, and status.

Use outcome context to decide whether work achieved the desired result. Do not
turn outcomes into tickets, tasks, schedules, or boards.

## Operate Assignments And Handoffs

In Work, use the Assignments tab to answer "who owns the work?", "who is
helping?", "what is blocked?", "what is waiting?", "what needs review?", and
"what is complete?" without reading an entire room transcript.

An assignment is work currently owned by one worker. It can link to a mission,
outcome, and room, and it can have many contributors. It is not a task,
ticket, schedule, kanban card, or project plan.

Assignment Centre shows:

- grouped assignment ownership by Assigned, In Progress, Waiting, Blocked,
  Review, and Completed
- owner, contributors, mission, outcome, status, and last activity on each
  assignment
- assignment detail with description, owner, contributors, activity, handoffs,
  related room, related mission, related outcome, proposals, and traces
- explicit operator controls to create an assignment, assign the owner, add or
  remove contributors, mark waiting, mark blocked, request review, complete,
  and hand off ownership

Handoffs are explicit records. SynKraken does not automatically reassign work,
automatically escalate blockers, or run workflow automation. Use handoffs when
ownership moves from one worker to another and the context should stay visible.

## Use Conversations

List rooms:

```bash
synkraken rooms
```

In the TUI:

```text
/rooms
/room preset ops ops
/open #ops
#ops status check
@everyone --global status check
```

Room messages preserve transcript context. Room memory gives the room durable
purpose, focus, constraints, and notes.

Console Conversations is the primary workforce surface. Use it to open a
conversation, record a plain note, send `@everyone`, send `@worker-id`, and
continue a thread. Member management, knowledge, assignments, delivery
results, proposals, handoffs, and diagnostics are available behind drawers.

Plain text in the Console room composer records a room note. `@everyone ...`
sends to room members. `@worker-id ...` sends to one worker with room context
so the exchange appears in the room timeline. `@everyone --global ...` sends a
global broadcast while still recording the operator message in the selected
room.

The conversation screen is fixed-height. The transcript owns the majority of
the screen, the room list is secondary, and drawers keep management controls
out of the way. Use Ctrl+Enter or Cmd+Enter from the multiline composer to
send. Large pasted text remains inside the composer instead of pushing
controls down the page.

Conversation drawers show delivery summaries and rows with target, status,
duration, attempts, and reply preview. Empty replies are shown as `[empty reply] -
worker responded without text.` Failures and timeouts are visible without raw
JSON by default.

Conversation drawers also show most active workers, active/idle/attention
member counts, last message, last broadcast, last room event, activity rate,
mission association, current outcome, current assignments, recent handoffs,
and blocked assignments. These are derived from persisted room messages and
daemon read models; Console does not invent summaries.

## Use Knowledge

Open Console Knowledge to inspect what the workforce should know. Knowledge is
visible Shared Workforce Memory grouped as Company, Projects, People,
Technical, Lessons Learned, and Pending Review. Use Teach Workforce for
explicit operator guidance that workers should inherit.

```bash
synkraken memory list
synkraken memory pending
synkraken memory note --title "Studio Blueprint positioning" --body "Studio Blueprint helps consultancies turn methodology into a repeatable operating system." --scope-type global --importance high
synkraken memory approve <memory-id>
synkraken memory reject <memory-id>
synkraken memory archive <memory-id>
```

Approved memory is available through `/v1/memory/context` and can be injected
into dispatches. Rejected and archived memory stay visible for audit but are
not active context.

## Review Governance

Open Console Governance to answer "what needs approval?" Governance groups
pending approvals, recent decisions, recent handoffs, and executed proposals.
Approve and reject actions remain explicit operator actions through daemon
governance endpoints.

Room rename and bulk remove-all-members are daemon/API gaps and are shown as
unavailable actions in Console.

## Review Proposals

```bash
synkraken proposals
synkraken proposal <proposal-id>
```

In Console, open Proposal Governance. Review risk, approval requirement,
proposer, linked records, and proposal events before approving, rejecting, or
executing. In v0.1, sensitive proposal execution is simulated and recorded.

## Inspect Trace And Replay

```bash
synkraken trace <id>
synkraken replay <id>
synkraken incident latest
```

Use traces to inspect messages, deliveries, dead letters, proposals,
decisions, handoffs, tasks, goals, memory markers, and related failures.

## Recover Dead Letters

```bash
synkraken dead-letters
synkraken retry dead-letter <id>
synkraken retry delivery <id>
```

Review the trace before retrying. Retry and replay should be operator actions,
not hidden background behavior.

## Review Incidents

Use the Console Incident Centre or:

```bash
synkraken incident latest
synkraken trace <incident-or-message-id>
```

Incidents are anchored in observable failures such as dead letters, failed
deliveries, or failing runtimes.

Incident priority uses presence where available. A failing idle worker usually
belongs on the Watch list. A failing worker in an active room, goal, proposal,
or recent trace may require action now.

When an incident is linked to a mission, Console shows the affected mission so
the operator can understand outcome impact quickly.

When an incident is linked to an outcome, Console shows the affected outcome
first.

## Use The Canvas

Open Console and start on Canvas. Use presets for Coding, Operations, Research,
or Incident Response. Add or focus runtime, room, mission, outcome, proposal,
trace, incident, dead-letter, or Activity Feed nodes. Runtime nodes show
presence, last activity, idle time, current room, current mission, current
outcome, attention reason, and suggested action. Use the inspector to jump
through relationships and open detail screens for full workflows. Runtime nodes
use subtle live indicators for active, idle, and attention states; the
indicators are visual context only and do not imply autonomous behavior.

Mission nodes appear in Operations, Research, and Incident Response presets
when mission records are available. They connect to workers, rooms, proposals,
and incidents through daemon relationship records.

Outcome nodes appear in the same presets when outcome records are available.
They connect to missions, workers, proposals, incidents, and traces through
daemon relationship records.

Canvas layout is local UI state. It does not change daemon records.

## Use The Command Palette

Press `Ctrl+K` in Console to open screens, switch canvas workspaces, add or
focus nodes, search runtime/proposal/trace context, show active workers, show
workers needing attention, focus rooms or workers, focus the Activity Feed, and
return to the canvas.

## Validate A Checkout

```bash
python3 scripts/context_audit.py
python3 -m compileall synkraken scripts
```

For deeper checks, run the relevant smoke tests in `scripts/` and the live
integration test against a running daemon.
