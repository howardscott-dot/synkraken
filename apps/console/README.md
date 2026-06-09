# SynKraken Console

## Retired Prototype

SynKraken Console is retired as an active product surface. The supported
surfaces are now the daemon API, CLI, TUI, Web Command Deck, and future
MCP-compliant tools.

This directory remains as historical prototype/design reference only. Do not
add new Console product features or make Console builds release-blocking
without explicitly reversing the retirement decision. See
[`../../docs/CONSOLE_RETIREMENT.md`](../../docs/CONSOLE_RETIREMENT.md).

## Historical Notes

SynKraken Console is the native Tauri desktop surface for SynKraken's
open-source AI Workforce Operating System. It connects to the local SynKraken
daemon, renders daemon-owned workforce state, and provides the Spatial
Operations Canvas plus calm operator screens for Home, Projects,
Conversations, Knowledge, Workforce, and Advanced.

Console does not own state, mutate SQLite directly, replace the CLI/TUI/Web
Command Deck, or add a second backend. Rust remains the Tauri shell,
packaging, native integration, and future native feature boundary. Business
logic stays in the daemon; UI logic stays in React/TypeScript.

## Purpose

Console exists for local operators who need a persistent desktop workspace for
AI workforce operations:

- inspect runtime health and trust
- understand worker presence and recent activity
- operate rooms
- review and approve proposals
- replay traces
- inspect incidents and dead letters
- arrange related objects on a spatial canvas
- jump between workers, rooms, proposals, traces, incidents, and failures

Console follows Calm Truth: it exposes real failures without exaggerating their
urgency. Raw daemon health remains available, but primary labels explain
operator impact with display severity such as Operational, Needs attention,
Degraded, Blocked, or Critical.

Console also follows Calm Operations: an operator console should reduce
cognitive load, not amplify it. The UI favors clear hierarchy, quiet
structure, primary actions that stand out, warnings with next steps, and
bounded panels that do not grow controls off screen.

Console v0.8 adds live operations awareness. Activity is a deterministic
daemon read model derived from messages, deliveries, proposal events, rooms,
and failure records. It answers what is happening right now without opening
traces, incidents, rooms, or proposals, and it does not add autonomy,
scheduling, execution, planning agents, or AI-generated summaries.

Console v0.95 adds Workforce Operations. Rooms now support the practical
operating loop: create/open room, add workers, add all workers, send room
notes, send `@everyone`, send `@worker-id`, continue a conversation, inspect
delivery summaries, see empty replies, failures, timeouts, and delete rooms
where daemon APIs exist. Rename and bulk remove-all are displayed as daemon
API gaps rather than faked.

Console v1.2 refines the operator UX without changing daemon behavior. Rooms
now use a fixed-height three-column messaging layout with independent room
list, transcript, member, and side-context scrolling. The composer stays
visible, supports Ctrl+Enter or Cmd+Enter, and keeps large pasted text inside
the textarea. Workforce rows use Available, Monitor, Avoid for now, and
Unavailable categories with issue, impact, and recommended action copy while
raw health remains accessible.

Console v1.3 adds Operational Briefing. Briefing is a deterministic read model
over existing daemon records that answers what is active, blocked, changed,
requires attention, and what the operator should review next. It shows
workforce, mission, outcome, assignment, activity, and review snapshots plus
up to five recommended next actions. It does not add a workflow engine,
autonomous planning, project-management semantics, or AI summarisation.

Console v1.5 reframes the interface around operator intent. Home is the
default screen and answers what needs attention, what the workforce is doing,
what work is active, what needs approval, and where to talk to workers. The
visual system uses restrained Apple-style dark surfaces, system typography,
generous whitespace, Apple blue for primary actions, amber for attention, and
red only for critical or destructive states. Raw technical fields remain
available behind details and inspectors rather than dominating the first view.

Console v1.6 shifts from operator-first navigation to Living Workforce UX.
The product model is conversation first, work second, governance third, and
diagnostics last. Home becomes a deterministic chief-of-staff briefing.
Conversations becomes the centre of the product experience. Memory is renamed
Knowledge. Workforce uses worker cards instead of telemetry tables.
Governance becomes an inbox. Activity is timeline-first. Search becomes a
Spotlight-style surface across SynKraken.

Console v2.0 reframes SynKraken as a Company Operating System powered by an
AI Workforce. Projects are now the centre of the product. A project workspace
groups Overview, Conversations, Knowledge, Deliverables, Team, and Decisions.
Missions, outcomes, assignments, proposals, traces, incidents, canvas,
dead letters, and memory internals move behind Advanced.

## Spatial Operations Canvas

Canvas is an advanced spatial inspection mode. It represents live daemon
objects as movable nodes:

- Workforce Summary
- Runtime
- Room
- Proposal Queue
- Proposal Detail
- Incident
- Trace
- Dead Letter
- Activity Feed

Relationship lines and inspector jumps come from daemon-backed relationship
records returned by `GET /v1/canvas/relationships`. Missing relationships are
omitted rather than faked.

Canvas layouts are local UI state stored in browser localStorage only. They
are not persisted to the daemon and do not affect durable business state.

## Rationale

Live operations awareness is intentionally read-only. The daemon already
records messages, deliveries, proposal events, room transcripts, and failure
records. Console v0.8 projects those records into a compact Activity screen,
room live context, workforce live columns, canvas indicators, and a summary
bar so operators can see current work without opening every object.

This preserves the SynKraken model: deterministic, local-first,
operator-led, and governance-first.

## Screens

- Home: Company Briefing with what happened, what needs the operator, and the
  next recommended project action
- Projects: project workspaces with Overview, Conversations, Knowledge,
  Deliverables, Team, and Decisions
- Conversations: chat-first workforce communication with room list,
  transcript, sticky multiline composer, and contextual drawers for members,
  knowledge, assignments, delivery results, proposals, handoffs, and
  diagnostics
- Knowledge: governed workforce knowledge, approved and pending context, and
  Teach Workforce
  operator notes
- Workforce: worker directory with Available, Monitor, Avoid for now, and
  Unavailable guidance; raw health and trust move to detail views
- Advanced: Governance, Assignments, Outcomes, Missions, Traces, Canvas,
  Incidents, Runtime Diagnostics, Proposal Internals, Dead Letters, and Memory
  Internals
- Command Palette: `Ctrl+K` navigation and object focus

## Run And Build

The Console is not an active runtime target. Normal SynKraken development does
not require installing Console dependencies, running Tauri, or building this
app. Historical commands may remain in old PRDs for audit context only.

## Daemon API

Console consumes:

- `GET /health`
- `GET /v1/agents`
- `GET /v1/workforce`
- `GET /v1/workforce/presence`
- `GET /v1/workforce/health`
- `GET /v1/activity/recent?limit=N`
- `GET /v1/activity/live?limit=N`
- `GET /v1/canvas/relationships`
- `GET /v1/rooms`
- `POST /v1/rooms`
- `POST /v1/rooms/preset`
- `DELETE /v1/rooms/{name}`
- `GET /v1/rooms/{name}`
- `GET /v1/rooms/{name}/messages`
- `GET /v1/rooms/{name}/messages?q=...`
- `GET /v1/rooms/{name}/memory`
- `POST /v1/rooms/{name}/messages`
- `POST /v1/rooms/{name}/summary`
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

Set `VITE_SYNKRAKEN_DAEMON_URL` to point the frontend at a different daemon
URL during development.

## Current Limitations

- no auth or multi-user accounts
- no packaged release automation
- no native notifications
- no settings persistence beyond canvas layout localStorage
- no direct goal or team management screens yet
- no room rename API
- no bulk remove-all-members API
- live updates use polling rather than SSE
- presence is local and deterministic; it is not cross-machine distributed
  presence or scheduling
- proposal execution remains daemon-governed and simulated for sensitive
  actions in v0.1
- relationship coverage is limited to links derivable from current persisted
  daemon records
- graph auto-layout and daemon layout persistence are not implemented

## Doctrine

See:

- [`../../docs/UI_CONSOLE_DOCTRINE.md`](../../docs/UI_CONSOLE_DOCTRINE.md)
- [`../../docs/SPATIAL_CANVAS_MODEL.md`](../../docs/SPATIAL_CANVAS_MODEL.md)
- [`../../docs/GOVERNANCE_MODEL.md`](../../docs/GOVERNANCE_MODEL.md)
