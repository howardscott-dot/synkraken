# Command Deck Spec

## Purpose

The Command Deck is the local Web GUI surface for SynKraken's AI Workforce
Operating System. It complements the TUI and CLI and is the official browser
surface. The historical Tauri Console is retired as an active product surface;
useful Console ideas should be folded into this Web Command Deck, the TUI, or
daemon read models.

## Command Deck API Scope

The Web Command Deck consumes daemon APIs such as:

- `GET /health`
- `GET /v1/agents`
- `GET /v1/workforce`
- `GET /v1/workforce/health`
- `GET /v1/rooms`
- `GET /v1/rooms/{name}`
- `GET /v1/rooms/{name}/messages`
- `GET /v1/rooms/{name}/memory`
- `POST /v1/rooms/{name}/members`
- `DELETE /v1/rooms/{name}/members/{adapter_id}`
- `POST /v1/messages`
- `GET /v1/proposals`
- `GET /v1/proposals/pending`
- `GET /v1/proposal/{id}`
- `POST /v1/proposal/approve`
- `POST /v1/proposal/reject`
- `POST /v1/proposal/execute`
- `GET /v1/replay/{id}`
- `GET /v1/trace/{id}`
- `GET /v1/incident/latest`
- `GET /v1/dead-letters?limit=N`

The Web Command Deck must not read SQLite directly, mutate daemon-owned state outside
existing APIs, add auth, add cloud features, add autonomous execution, or
implement full memory, goal, team, decision, or handoff management.

## Retired Console Canvas Reference

The following canvas notes are historical reference from the retired Console
prototype. They are not active Command Deck scope unless deliberately rebuilt
on daemon read models.

## Operations Canvas scope

Operations Canvas represents daemon-owned objects as movable node panels on a
dark 24px dot-grid canvas. It uses React/TypeScript UI state only; Rust remains
the Tauri shell and packaging boundary. Layouts are saved in localStorage for
v0.3 and are not written to the daemon.

Canvas node types:

- Workforce Summary
- Runtime
- Room
- Proposal Queue
- Proposal Detail
- Incident
- Trace
- Dead Letter

Workspace presets:

- Coding: Workforce Summary, Room, Proposal Queue, Trace
- Operations: Workforce Summary, Runtime Nodes, Incident, Dead Letters
- Research: Room, Trace, Proposal Queue, Workforce Summary
- Incident Response: Incident, Dead Letters, Trace, affected Runtime Nodes,
  Proposal Queue

Canvas behavior:

- pan and zoom
- move nodes
- select and focus nodes
- fit to view
- reset layout
- save and restore layout locally
- render simple relationship lines where daemon data exposes a relationship

Relationship lines are visual hints only. They may link proposals to traces,
proposals to runtime proposers, incidents to dead letters, rooms to proposals,
runtimes to incidents, and traces to dead letters when existing API fields
support the inference. Missing relationship data must be omitted rather than
mocked.

Existing v0.2 screens remain accessible from the left navigation as detail and
backstop views: Workforce, Rooms, Proposals, Trace, and Incidents.

## Console v0.4 Canvas drilldown scope

Console v0.4 keeps the v0.3 canvas foundation and adds:

- Canvas Inspector for the selected node
- object focus/search input on the canvas toolbar
- toolbar add-node control for supported v0.3 node types
- command-palette add/focus commands for runtime, room, proposal, trace,
  incident, dead-letter, workforce, and proposal queue nodes
- local clear saved layout control
- related object jumps where current daemon records expose ids

The inspector may show richer fields and object links, but it must not become a
client-owned business model. It reads currently loaded daemon responses and
links back to existing legacy/detail screens where full workflows already
exist.

## Console v0.5 real relationship scope

Console v0.5 adds `GET /v1/canvas/relationships`, a daemon read model over
persisted SynKraken records. Relationship records include source type/id,
target type/id, relationship kind, status/tone, evidence, and observed
timestamp where available.

Relationship sources include:

- proposals and their proposer, room, and linked message ids
- proposal queue membership from persisted proposal status
- dead letters and their failed message/runtime ids
- runtime reputation incident state
- latest incident anchors

Canvas relationship lines and inspector jumps must use these daemon
relationship records. If the daemon returns no relationship for an object, the
canvas omits the relationship rather than inventing one in the client.

## Web Command Deck goals

Provide a browser-based local operator surface that:

- runs on `127.0.0.1:9461`
- reuses the existing daemon APIs
- shows rooms
- shows agent presence
- shows live room messages
- shows active per-agent delivery activity inline with messages
- supports sending to a room
- supports broadcasting to all agents
- supports bounded Discussion Mode commands in the composer
- exposes editable Room Memory for the selected room
- exposes inspectable Shared Memory and its injection budget
- supports explicit Team Task Mode for the selected room
- shows recent Team Runs with owner, reviewer, status, and approval controls
- supports explicit Goal Mode for the selected room
- shows Goal Runs with round, score, threshold, owner, reviewers, Token Police,
  Guardrail Agent, status, details, and cancellation for active runs
- shows recent Decision Records with title, status, proposer, approval or
  rejection actor, and summary
- shows recent Handoffs with status, from-agent, to-agent, summary, and
  recommended next step
- shows recent and pending Proposals with risk, approval requirement, proposer,
  approve/reject/execute controls, and trace access
- shows a minimal Flight Recorder / Incident panel for replaying existing work
  and inspecting the latest failure context

## v0.2 goals

Extend the initial command deck without changing the backend ownership model:

- create rooms with selected agent members
- send direct messages to individual agents
- surface live typing state from daemon events
- make current target selection explicit
- add Tasks v0.1 as the first durable work object beyond chat

## User model

The human operator is in control. The default interaction is:

1. choose a room
2. inspect recent transcript and live updates
3. send a message to that room or broadcast to all agents

## Information architecture

### Left rail: rooms

- list known rooms
- show member counts
- select a room to load its transcript
- create a room with selected members
- show and edit selected-room memory: purpose, objective, focus, rules,
  constraints, and notes

### Main panel: live messages

- current room heading
- room transcript
- live refresh after message-related events
- clear author and timestamp
- transient pending reply rows for active deliveries, one row per recipient
  agent for broadcasts and room sends
- neutral activity wording: `thinking…`, `working…`, `waiting…`, `failed`,
  or `timeout`; no chain-of-thought text
- successful pending rows collapse into the actual replies as transcript data
  arrives; failed and timed-out rows remain visible inline
- operator surfaces must render arbitrary enabled workers from daemon data; no
  UI surface may assume a fixed workforce size or fixed adapter id list
- weak adapter behavior is operator-visible: empty replies render as
  `[empty reply]`, delivery quality labels such as `suspicious_output` are not
  hidden, and broadcast result summaries list every target
- discussion progress appears as transcript messages, for example
  `goose turn 1`, `hermes turn 2`, and `hermes final recommendation`
- team task progress appears as transcript messages for clarify, nominate,
  owner selection, execute, review, and final report phases
- goal progress appears as transcript messages for criteria, assignment,
  control roles, context budget, owner work, token review, guardrail review,
  quality review, score, revision, and final report phases
- terminal transcript views must keep scrollback navigable with Up/Down,
  PgUp/PgDn, Home/End, preserve the operator's history position while new
  messages arrive, show when the operator is viewing history, support jumping
  live with End or `/tail`, support current-transcript search, and export the
  current transcript through `/save-transcript`

### Right rail: agents

- list registered agents bootstrapped from config
- show display name and adapter id
- show durable operational status from the daemon
- show last seen, current room, and current task
- show all enabled configured workers, including unknown future adapter ids with
  fallback styling
- select an agent as a direct-message target
- show live typing state when available
- do not show chain-of-thought, hidden memory, plans, or scheduling state

### Tasks panel

- show recent Team Runs
- show owner, reviewers, status, and approval state
- approve or reject runs waiting for review
- show recent Goal Runs
- start a goal for the selected room
- show current round, score, threshold, owner, reviewers, Token Police,
  Guardrail Agent, guardrail status, and run status
- inspect one Goal Run's recent events and final report summary
- cancel active Goal Runs
- list recent Decision Records and show status
- list recent Handoffs and show status, sender, receiver, summary, and next step
- list recent Proposals and show status, risk, approval requirement, proposer,
  title, and operator controls
- show latest incident context
- replay a conversation, task, goal run, decision, or handoff id as a plain
  timeline
- list durable tasks
- create a task
- optionally assign it to an agent
- optionally associate it with the current room
- change status and priority
- clearly distinguish open, in-progress, blocked, and done work
- create a task from a visible room message
- expand a lightweight detail section for ownership metadata and recent events

### Composer

- text area
- send-to-room action
- direct-message action when an agent is selected
- broadcast action
- explicit current target label
- `/discuss <agent1> <agent2> "topic"` command text, with optional
  `--turns N` and `--room name`
- `/team "question or task"` and `/team --turns N "question or task"`
- Ask team action for the selected room
- `/goal "goal text"` and `/goal --threshold 80 --rounds 3 "goal text"`
- Start goal action for the selected room

## Backend contract

The command deck must use the existing daemon model:

| Need | Existing endpoint |
|---|---|
| agents / presence | `GET /health`, `GET /v1/agents`, `GET /v1/agents/{id}`, `GET /v1/agents/{id}/events` |
| rooms | `GET /v1/rooms` |
| room memory | `GET /v1/rooms/{name}/memory`, `PUT /v1/rooms/{name}/memory`, `GET /v1/rooms/{name}/memory/events` |
| shared memory | `GET /v1/memory`, `GET /v1/memory/{id}`, `POST /v1/memory/propose`, `POST /v1/memory/{id}/review`, `POST /v1/memory/{id}/approve`, `POST /v1/memory/{id}/reject`, `POST /v1/memory/{id}/archive`, `GET /v1/memory/search?q=`, `GET /v1/memory/budget` |
| transcript | `GET /v1/rooms/{name}/messages` |
| send | `POST /v1/messages` |
| discussions | `POST /v1/discussions` |
| team tasks | `POST /v1/team-tasks` |
| team governance | `GET /v1/team-runs`, `GET /v1/team-runs/{id}`, `GET /v1/team-runs/{id}/events`, `POST /v1/team-runs/{id}/approve`, `POST /v1/team-runs/{id}/reject` |
| goal mode | `POST /v1/goal-runs`, `GET /v1/goal-runs`, `GET /v1/goal-runs/{id}`, `GET /v1/goal-runs/{id}/events`, `POST /v1/goal-runs/{id}/cancel` |
| decisions | `GET /v1/decisions`, `GET /v1/decision/{id}`, `GET /v1/decision/latest`, `POST /v1/decision/propose`, `POST /v1/decision/approve`, `POST /v1/decision/reject` |
| handoffs | `GET /v1/handoffs`, `GET /v1/handoff/{id}`, `GET /v1/handoff/latest`, `POST /v1/handoff`, `POST /v1/handoff/accept`, `POST /v1/handoff/reject`, `POST /v1/handoff/complete` |
| proposals | `GET /v1/proposals`, `GET /v1/proposal/{id}`, `GET /v1/proposals/pending`, `POST /v1/proposal/create`, `POST /v1/proposal/approve`, `POST /v1/proposal/reject`, `POST /v1/proposal/cancel`, `POST /v1/proposal/execute` |
| flight recorder | `GET /v1/replay/{id}`, `GET /v1/incident/latest` |
| live updates | `GET /v1/events/stream` |
| tasks | `GET /v1/tasks`, `POST /v1/tasks`, `PATCH /v1/tasks/{id}` |
| task comments | `POST /v1/tasks/{id}/comment` |
| task history | `GET /v1/tasks/{id}/events` |

The web process may proxy these endpoints for same-origin browser access, but
it should not invent alternate semantics.

## v0.1 interaction rules

- no room selected: disable room send, allow global broadcast
- room send uses target `room:<name>`
- room transcript is canonical: successful replies to `room:<name>` messages must be persisted back into the same room history
- with a room selected, `@everyone …` and the Broadcast action use target `room:<name>`
- without a room selected, `@everyone …` uses target `broadcast`
- `@everyone --global …` is the explicit global form from any context
- inside a selected room, direct `@agent …` sends keep directed delivery but are persisted into the current room transcript
- `@agent --global …` is the explicit direct/global form from inside a room
- event stream should trigger transcript refreshes after relevant message or
  delivery events
- event stream delivery lifecycle events are used for ephemeral activity state:
  `delivery.queued`, `delivery.sent`, `typing.started`, `delivery.recorded`,
  and `dead-letter.recorded`
- active delivery rows must distinguish `queued`, `sent`, `thinking`,
  `replied`, `failed`, and `timeout`
- Discussion Mode is daemon-orchestrated through `POST /v1/discussions`; the
  web UI must not create client-only discussion loops
- a selected room scopes `/discuss ...` into that room unless `--room` names a
  different room
- discussions without a room create a normal conversation
- every discussion topic, turn marker, agent reply, final recommendation, and
  failure is persisted in the visible room transcript or conversation
- room-scoped sends and discussions receive concise Room Memory context from
  the daemon; the web UI edits the memory but does not perform prompt assembly
- room-scoped sends, discussions, and team tasks may receive approved Shared
  Memory from the daemon, labelled `[SynKraken approved memory]`, never
  rejected/archived/proposed entries, and only within configured item and
  character budgets
- max turns are bounded; the default operator command uses four total agent
  messages, and the final turn requests a recommendation
- Team Task Mode is daemon-orchestrated through `POST /v1/team-tasks`
- Team Task Mode requires a selected room; without one, clients must surface:
  `Team mode needs a room. Create or select a room first.`
- Team Task Mode writes prompt, clarifications, nominations, owner selection,
  owner output, reviews, and final report into the visible room transcript
- Team Task Mode creates a durable task, assigns the selected owner, and records
  lifecycle events where available
- Team Task Mode must continue when one non-owner agent fails and must record a
  visible failure if no owner can produce output
- Team Task Mode must not collapse timeouts into dead letters only. Critical
  timeout failures must keep completed transcript messages visible, mark the
  durable task and `team_run` blocked, and record `timeout`, `failed_phase`, and
  `run_blocked` events with run id, phase, agent, elapsed time, and partial
  transcript context.
- Team Governance records every run in `team_runs` and its audit trail in
  `team_events`
- Goal Mode is daemon-orchestrated through `POST /v1/goal-runs`
- Goal Mode requires a selected room; without one, clients must surface:
  `Goal mode needs a room. Create or select a room first.`
- Goal Mode defines criteria, assigns owner/reviewers/control roles, executes
  bounded rounds, checks token budget, checks guardrails, scores reviewer
  output, and stops at threshold or max rounds
- Goal Mode context must be compact between rounds and display:
  `Goal context budget`, current round, estimated context chars, and limit
- Goal Mode creates a linked task. `achieved` and `partially_achieved` map to
  done with partial status documented; `blocked`, `failed`, and `cancelled` map
  to blocked.
- Goal Mode records every run in `goal_runs` and its audit trail in
  `goal_events`
- Goal Mode is not infinite autonomy, hidden work, background scheduling,
  permissionless execution, unbounded token use, or hardcoded project context
- Decision Records are daemon-owned durable records through `decisions` and
  `decision_events`
- Decision Records show what was decided, who proposed it, who approved or
  rejected it, why, and what messages or runtimes it relates to
- Decision Records are not voting, handoffs, policy enforcement, or workflow
  automation
- Handoffs are daemon-owned durable records through `handoffs` and
  `handoff_events`
- Handoffs show what work was handed off, who handed it off, who received it,
  what context, risks, and next steps were attached, and whether the receiving
  worker accepted, rejected, or completed it
- Handoffs are not approval chains, voting, policy enforcement, scheduling, or
  autonomous workflow automation
- Proposals are daemon-owned durable execution-authority records through
  `proposals` and `proposal_events`
- Proposal execution is operator-controlled; workers may propose, humans
  approve, and SynKraken records simulated execution in v0.1
- Proposal controls must not run real shell, git, restart, write, delete,
  replay, or retry actions from the browser
- Flight Recorder is daemon-owned read-model assembly through `GET
  /v1/replay/{id}` and `GET /v1/incident/latest`
- Flight Recorder reconstructs messages, deliveries, dead letters, decisions,
  handoffs, task events, goal events, runtime participation, failures, and
  outcome from existing persisted state
- Flight Recorder is not a policy engine, approval chain, cost dashboard,
  reputation system, visual analytics surface, or workflow automation
- `/team-run <id>` and `GET /v1/team-runs/{id}` inspect failed or blocked runs,
  including failure summary and partial transcript. `/continue-team-run <id>` is
  future work.
- TUI `/transcript` opens a transcript-oriented command surface with the
  current room history, recent team runs, active filters, and actions to view,
  export, or review the most recent team run.
- `AUTO` mode completes after the final report
- `REVIEW_REQUIRED` mode stops at `awaiting_approval`, shows approve/reject
  controls, and waits for explicit operator action before marking the linked
  task done or blocked
- the UI should remain usable if the event stream disconnects; periodic or
  manual reload behavior may recover state

## v0.2 interaction rules

- room creation should use existing room APIs, not client-only state
- selecting a room and selecting a direct agent are mutually exclusive compose
  targets
- live typing state is ephemeral UI state derived from SSE, not persisted data
- agent presence in this release means durable operational state: configured,
  online, idle, working, blocked, offline, or disabled, plus last-seen, current
  room, and current task
- presence is not memory, decisions, autonomous workflow state, scheduling, or
  cloud sync
- task details should expose auditability lightly, not become a full workflow UI
- Room Memory is persistent room context, not agent memory, hidden
  chain-of-thought, RAG, embeddings, semantic search, autonomous planning,
  decisions, or cloud sync
- Shared Memory is peer-reviewed workspace knowledge, not hidden autonomous
  memory, vector search, RAG, personal profiling, cloud sync, unlimited context
  stuffing, or background memory mining
- Team Mode is human-commanded orchestration, not autonomous background work,
  scheduling, hidden agent work, or cloud sync
- richer agent lifecycle states belong to Agent Presence work after the agent
  model doctrine is established

## Visual direction

- dark local-console aesthetic
- reuse SynKraken's ocean palette and agent color language where practical
- prioritize legibility over decoration

## Out of scope for v0.1

- room creation or membership editing
- direct one-to-one messages
- conversation search
- decision workflows beyond a minimal recent-decision list
- authentication
- remote hosting
- external product integrations

## Still out of scope for v0.2

- room deletion and membership editing
- search
- task automation, recurring tasks, decision workflows, RAG, embeddings, or
  autonomous memory workflows
- authentication and remote deployment
- installation-specific branding, organisation context, personal workflows, or
  proprietary project context in shipped defaults

## Success criteria

Command Deck v0.1 is successful when an operator can:

1. start the existing daemon
2. run `synkraken web`
3. open the local web UI
4. see rooms and configured agents
5. open a room transcript
6. send into that room
7. broadcast to all agents
8. watch updates appear without leaving the page
9. see one pending activity row per recipient while agents are working
10. start a bounded two-agent discussion and watch persisted turn progress
