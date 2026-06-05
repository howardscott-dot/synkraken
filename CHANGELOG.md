# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- SynKraken Console v2.0 Project-Centric Company OS: reframed SynKraken as a
  Company Operating System powered by an AI Workforce. Primary navigation is
  now Home, Projects, Conversations, Knowledge, Workforce, and Advanced.
  Projects become the daily operating centre with Overview, Conversations,
  Knowledge, Deliverables, Team, and Decisions tabs. Deliverables become a
  first-class project surface; Decisions is the human-facing governance layer;
  and Advanced now contains governance, assignments, outcomes, missions,
  traces, canvas, incidents, runtime diagnostics, proposal internals, dead
  letters, and memory internals. Existing governance, memory, assignment,
  mission, outcome, proposal, trace, incident, and workforce capabilities are
  preserved behind the new project-centric model.
- SynKraken Console v1.6 Living Workforce UX: reframed the Console around
  conversation first, work second, governance third, and diagnostics last.
  Primary navigation is now Home, Conversations, Work, Knowledge, Workforce,
  Governance, and Search. Home is a deterministic chief-of-staff briefing;
  Conversations gives the transcript the majority of the screen with members,
  knowledge, assignments, delivery results, proposals, handoffs, and
  diagnostics in drawers; Work uses educational empty states; Knowledge
  replaces Memory language; Workforce uses worker cards; Governance becomes an
  inbox; Activity is timeline-first; and Search provides one Spotlight-style
  result surface. This is a product experience redesign only and does not
  change daemon behavior, storage, entities, or APIs.
- SynKraken Console v1.5 Apple Operator Redesign: reorganized the native
  Console around operator intent with Home as the default briefing, Rooms as a
  chat-first workforce communication space, Work as the combined Missions /
  Outcomes / Assignments area, Workforce Memory with Teach Workforce copy,
  Governance for approvals/decisions/handoffs, and Canvas reframed as an
  advanced spatial view. The visual system now uses a restrained Apple-style
  dark shell, system typography, soft surfaces, Apple blue primary actions,
  amber attention, red only for critical/destructive states, and raw technical
  details behind inspectors/details where practical. This is a UI architecture
  sprint only; daemon behavior, storage, APIs, and entities are unchanged.
- SynKraken v1.4 Shared Workforce Memory: added visible, governed memory
  records with title/body/scope/source/importance/status fields; operator
  notes; proposed/approved/rejected/archived governance; active context
  retrieval; bounded approved-memory dispatch injection; Memory Centre;
  scoped memory sections; Memory canvas node; and minimal CLI parity.
- SynKraken Console v1.3 Operational Briefing: added a top-level Briefing
  screen directly beneath Canvas plus a Briefing canvas node in the Operations
  preset. The Briefing is a deterministic read model over existing daemon
  records: workforce categories, mission health, outcome health, assignment
  health, recent meaningful activity, operator-review counts, and up to five
  recommended next actions. This does not add workflow automation, autonomous
  planning, project management, AI summarisation, daemon behavior, storage,
  entities, or APIs.
- SynKraken Console v1.2 Operator UX Sweep: Console now applies Calm
  Operations doctrine to reduce cognitive load without changing daemon
  behavior. Rooms use a fixed-height three-column messaging layout with
  independently scrolling room list, transcript, member list, and side context;
  the multiline composer stays visible, supports Ctrl+Enter/Cmd+Enter, and is
  paste-safe. Workforce rows now classify workers as Available, Monitor, Avoid
  for now, or Unavailable with issue, impact, and recommended action copy while
  raw health/trust remains accessible. Delivery results render compact
  target/reply/empty/failure summaries with raw details collapsed by default.
- SynKraken v1.1 Workforce Assignment & Handoffs: Assignment is now a
  first-class accountability object for work currently owned by one worker,
  with many contributors, mission/outcome/room links, explicit status changes,
  and auditable handoffs. Added SQLite assignment and assignment event tables,
  assignment contributors, assignment-linked handoffs, assignment read/write
  APIs, assignment-aware activity filtering, worker assignment counts,
  mission/outcome/room assignment context, Assignment Centre, assignment
  detail cockpit, handoff timeline, Assignment canvas nodes, and command
  palette actions for create, assign, contribute, block, review, complete,
  view handoffs, and focus assignment. This deliberately avoids tasks,
  tickets, scheduling, kanban, gantt charts, automatic reassignment, workflow
  automation, and autonomous execution.
- SynKraken Console v0.95 Workforce Operations: Console Rooms now supports the
  core day-to-day operating loop through existing daemon APIs: create/open/
  delete rooms, create room presets, add/remove workers, add all workers,
  refresh rooms, record room notes, send `@everyone`, send room-scoped
  `@worker-id` messages, search and summarize room history, and render
  delivery summaries with replied, empty reply, timeout, failed, blocked, and
  suspicious-output states. Added a Workforce Operations panel, chat-style room
  transcript, command palette room operations, and operational room-node
  controls. Room rename and bulk remove-all-members remain explicit daemon/API
  gaps.
- SynKraken v1.0 Outcome Governance: Outcome is now the primary success object
  linked to missions. Added deterministic SQLite outcome read models,
  outcome-to-worker/trace/incident/proposal links, outcome summary/activity
  APIs, mission progress derived from completed outcomes, outcome-aware
  activity filtering, Outcome Centre, outcome detail cockpit, Outcome canvas
  nodes, and current/affected outcome context in Workforce, Rooms, and
  Incidents. This remains read-only and deliberately avoids tasks, tickets,
  kanban, schedules, gantt charts, and AI-generated progress summaries.
- SynKraken Console v0.9 Mission Control: Mission is now a first-class
  governance container for meaningful AI workforce outcomes. Added SQLite
  mission read models, mission link tables for workers, rooms, traces,
  incidents, proposals, and relationships, mission summary/activity APIs,
  mission-aware activity filtering, Mission Centre, mission detail cockpit,
  Mission canvas nodes in Operations/Research/Incident Response presets, and
  mission context in Rooms, Workforce, and Incidents. This is read-model-first
  and deliberately avoids scheduling, boards, tickets, projects, or
  workload-specific entities.
- SynKraken Console v0.7 Workforce Presence & Activity: daemon read endpoints
  now expose deterministic workforce presence and recent activity, while the
  Console shows active, idle, watching, unavailable, and needs-attention
  workers, an Activity Feed node, presence-aware runtime nodes, room member
  presence, incident impact framing, and command-palette focus commands.
- SynKraken Console UX Softening and Operator Guidance v0.6: Console now
  separates daemon raw health from operator-facing display severity, adds
  Operator Summary panels to Canvas, Workforce, and Incident Centre, softens
  nonblocking runtime failures from red critical language to amber
  `Needs attention`/`Degraded` language, groups incidents by operator priority,
  and documents the Calm Truth principle: expose real failures without
  exaggerating urgency.
- Documentation and GitHub readiness sprint: README rewritten as the project
  landing page for the open-source AI Workforce Operating System positioning,
  with new product vision, core concepts, governance model, spatial canvas
  model, Console doctrine, operator guide, rationale, GitHub description, and
  screenshot inventory docs.
- SynKraken Console v0.5: real daemon-backed Operations Canvas relationships
  through `GET /v1/canvas/relationships`. Relationship lines and inspector
  jumps now use relationship records derived from persisted proposals, proposal
  links, rooms, dead letters, runtime reputation, and latest incident anchors,
  each with evidence attached. Client-side production relationship inference
  was removed from canvas rendering.
- SynKraken Console v0.4: Operations Canvas now has a selected-node Canvas
  Inspector, object focus/search, expanded add-node controls, clear saved layout
  control, and command-palette entries for runtime, room, proposal detail, trace,
  incident, dead-letter, workforce, and proposal queue nodes. The work stays in
  React/TypeScript over existing daemon APIs; Rust remains the Tauri shell and
  packaging boundary.
- SynKraken Console v0.3: Operations Canvas becomes the desktop Console home,
  beginning the shift from page-based dashboard navigation to a spatial AI
  workforce operating system. The canvas uses real daemon APIs, movable node
  panels, 24px dot grid, localStorage layout persistence, deterministic Coding,
  Operations, Research, and Incident Response workspace presets, simple
  relationship lines, and node types for workforce summary, runtimes, rooms,
  proposal queue/detail, incidents, traces, and dead letters. Existing Console
  v0.2 screens remain accessible as detail/backstop views.
- SynKraken Console v0.1: a Tauri v2 desktop client in `apps/console` using
  React, TypeScript, and Tailwind. It connects to the local daemon over HTTP,
  shows workforce health, proposals, proposal detail, trace inspection, latest
  incident context, dead letters, and a `Ctrl+K` command palette without
  duplicating daemon state or replacing the CLI, TUI, or Web Command Deck.
- Approval & Execution Governance v0.1: first-class proposals with append-only
  proposal events, deterministic hardcoded governance rules, approval/rejection/
  cancellation/simulated-execution lifecycle APIs, CLI/TUI/Web controls, replay
  and trace integration, and simple runtime reputation counters. Workers may
  propose sensitive actions; operators approve; SynKraken records execution as
  simulated in v0.1.
- Runtime Reputation + Workforce Health v0.1: SynKraken now persists
  deterministic per-runtime reputation derived from delivery history, including
  successful replies, empty replies, timeouts, failures, wrong identity,
  suspicious output, average duration, trust score, health status, and
  lightweight incident summaries. Added workforce health APIs, CLI commands,
  TUI `/workforce` and `/health workforce` output, stress report reputation
  sections, and health-aware goal/team selection bias without disabling
  workers.
- Stable Honest TUI v0.1: `/workforce` exposes all enabled daemon-reported
  workers with latest delivery status, quality, cost tier, usage risk, and
  recent weak-output counts; broadcast result panels now show target/replied/
  empty/failed/timeout/degraded counts and still list every target; empty room
  replies persist and render as `[empty reply]`; suspicious delivery quality is
  visible in replies, transcripts, events, and latest reply rows; `/stress
  latest` summarizes the newest CLI stress report when available.
- CLI stress reports now document `wrong_identity` classifications for direct
  or broadcast replies that return another adapter's identity marker.
- Dynamic agents in the TUI v0.1: the command deck no longer hard-codes the
  goose/hermes/openclaw runtime names. Agent colors are assigned from a palette
  by hashing the adapter id, enabled agents are listed and sorted by presence
  status, mention aliases and autocomplete are derived from live agents, and
  delivery rows show a classified status (acknowledged, empty_reply, failed,
  timed_out) with empty bodies rendered as `[empty reply]`.
- Crush adapter v0.1: support for running Crush as an active SynKraken worker, including prompt delivery via `crush run --quiet`, isolation boundary, working directory control, discovery integration, runtime diagnostics, and TUI color pair.
- Google Antigravity adapter v0.1: support for running Google Antigravity as an active SynKraken worker, including prompt delivery, command verification, discovery integration, and runtime diagnostics.
- Documentation Lock Batch v0.1: category and architecture lock docs for the
  open-source control plane positioning, control-plane doctrine, cost/runtime
  ownership, workforce model, identity/role boundaries, and OSS → Packs →
  Vertical products architecture.
- Friendly daemon lifecycle commands: `synkraken start|stop|restart|status`
  with optional `daemon` target, user-service detection, install guidance, and
  combined service/health reporting in `synkraken status`.
- Product and architecture foundation docs for the v0.2 command deck direction.
- `synkraken web`, a local Web Command Deck served on `127.0.0.1:9461`
  with rooms, live room transcripts, agent presence, room send, and broadcast.
- Web Command Deck follow-up: room creation, direct agent messaging, and live
  typing presence from daemon events.
- Tasks v0.1: durable SQLite-backed tasks with optional room, agent, and source
  message links; task comments; task APIs; and a visible Tasks panel in the Web
  Command Deck.
- Tasks Hardening v0.15: SQLite foreign-key enforcement, task ownership
  metadata, append-only task events, task history API, and lightweight audit
  details in the Web Command Deck.
- Agent Model Doctrine v0.1 documenting durable agent identity, lifecycle,
  authority, roles, capabilities, and the sequence toward presence, memory,
  decisions, handoffs, workspace packs, and external product integrations.
- Agent Presence v0.1: durable agent status, last-seen metadata, current
  room/task fields, append-only agent events, richer agent APIs, TUI
  `/presence` and `/agent` inspection, Web Command Deck status cards, and smoke
  coverage for message, broadcast, discussion, timeout, and startup
  transitions. Presence is operational state only, not chain-of-thought,
  memory, decisions, scheduling, or cloud sync.
- Room Memory v0.1: durable per-room purpose, objective, rules, constraints,
  current focus, and notes with append-only memory events; daemon APIs; TUI
  `/memory` commands; a Web Command Deck Room Memory form; concise prompt
  injection for room messages, room broadcasts, and room discussions; and smoke
  coverage. Room Memory is persistent room context only, not agent memory, RAG,
  embeddings, autonomous planning, decisions, or cloud sync.
- Team Task Mode v0.1: human-commanded room orchestration through
  `POST /v1/team-tasks`, TUI `/team`, and a Web Command Deck Ask team action.
  SynKraken runs bounded clarify, nominate, owner selection, execute, review,
  and final-report phases; stores every phase visibly in the room transcript;
  creates and completes a durable task; and continues when one non-owner agent
  fails. Team Mode is not autonomous background work, scheduling, cloud sync, or
  hidden work outside the room transcript.
- Team Governance v0.1: durable `team_runs` and `team_events`, `AUTO` and
  `REVIEW_REQUIRED` approval modes, `/team-runs`, `/team-run`, `/approve`, and
  `/reject` TUI commands, Web Command Deck recent team run cards, and smoke
  coverage for approval, rejection, failed runs, and audit trails.
- Team Mode timeout resilience: critical phase timeouts now preserve partial
  room transcripts, mark the durable task and team run `blocked`, record
  `timeout`, `failed_phase`, and `run_blocked` events, and expose the failure
  summary through `/team-run` and the Web Command Deck instead of relying on
  dead letters as the primary UX.
- Shared Memory Skill v0.1: peer-reviewed workspace knowledge in
  `shared_memory`, shared audit events in `memory_events`, daemon memory APIs,
  TUI `/memory ...` commands, token-budgeted prompt injection for room
  messages, discussions, and team tasks, and smoke coverage. Shared Memory is
  inspectable and bounded; it is not hidden memory, vector search, RAG,
  personal profiling, cloud sync, or autonomous background memory mining.
- Goal Mode v0.1: bounded room goal execution with durable `goal_runs` and
  `goal_events`, TUI `/goal`, `/goals`, `/goal-run`, and `/cancel-goal`
  commands, Web Command Deck Goal Runs controls, goal run APIs, linked tasks,
  criteria definition, owner/reviewer assignment, Token Police and Guardrail
  Agent control roles, compact revision rounds, threshold scoring, and smoke
  coverage. Goal Mode is not infinite autonomy, hidden work, background
  scheduling, permissionless execution, unbounded token use, or hardcoded
  project context.
- Decision Records v0.1: durable `decisions` and `decision_events` tables,
  proposal/approval/rejection APIs, TUI `/decisions`, `/decision latest`,
  `/decision <id>`, `/approve <id>`, and `/reject <id>` commands, a minimal Web
  Command Deck decisions panel, and smoke coverage. Decision Records capture
  what was decided, who proposed it, who approved or rejected it, why, and what
  messages or runtimes it relates to; they are not voting, handoffs, a policy
  engine, or flight recorder.
- Handoffs v0.1: durable `handoffs` and `handoff_events` tables, create/list/
  latest/inspect/accept/reject/complete APIs, TUI `/handoffs` and `/handoff`
  commands, a read-only Web Command Deck handoffs panel, and smoke coverage.
  Handoffs record what work was handed off, who handed it off, who received it,
  what context, risks, and next steps were attached, and whether the receiving
  worker accepted, rejected, or completed it.
- Flight Recorder v0.1: replay API and latest-incident API that reconstruct AI
  work from existing messages, deliveries, dead letters, decisions, handoffs,
  tasks, and goal events; TUI `/replay <id>` and `/incident latest`; a minimal
  read-only Web Command Deck panel; and smoke coverage. Flight Recorder is a
  read model for inspection, not a policy engine, approval chain, analytics
  dashboard, or new workflow runtime.
- Configuration Doctrine: shipped defaults, docs, tests, prompts, and examples
  stay generic; installation-specific identity and project context belong in
  local config, workspace config, room memory, shared memory, skills, runtime
  context, or user prompts. Added `scripts/context_audit.py`.
- TUI transcript navigation: chat and room history now support Up/Down,
  PgUp/PgDn, Home/End scrollback, history-position indicators, preserved
  review position while new messages arrive, `/tail`, transcript search with
  `/term`, `n`, and `N`, `/transcript`, and `/save-transcript` exports under
  `exports/`.
- Basic local TUI slash commands: `/help`, `/status`, `/health`, `/agents`,
  `/rooms`, `/tasks`, and `/clear`; unknown slash commands now stay local
  instead of creating dead letters.
- Room-scoped `@everyone` routing in the TUI and Web Command Deck, with
  `@everyone --global …` as the explicit fleet-wide escape hatch from a room.
- Explicit room reply-context preservation during fan-out, plus regression
  coverage proving successful member replies persist into canonical room history.
- `/room enter <name>` now opens the live room transcript instead of only setting
  routing context, so in-room sends remain visible as a conversation while you chat.
- TUI mention parsing now treats only leading `@mentions` as routing targets, so
  quoted mentions inside a message body such as `"@goose"` are preserved as text.
- Intentional multi-target TUI sends now run in the background like single-target
  sends instead of blocking the interface while each target replies.
- Direct sends issued while viewing a room no longer replace the visible room
  transcript.
- Direct `@agent` sends from inside a room now preserve directed delivery while
  also persisting the outbound message and reply into that room transcript;
  `@agent --global …` keeps the old separate-conversation behavior.
- In-chat per-agent activity indicators now appear for active deliveries in
  the TUI and Web Command Deck, including broadcast fan-out rows, queued/sent/
  thinking/replied/failed/timeout states, and inline failed delivery visibility.
- Discussion Mode v0.1: `POST /v1/discussions`, TUI `/discuss`, and Web
  Command Deck `/discuss ...` composer support for bounded agent discussions
  with visible turn markers, final recommendation turns, room/conversation
  persistence, and clean failure recording.
- Added `scripts/live_integration_test.py`, a stdlib-only live daemon test that
  writes timestamped audit reports, exercises CLI health/status, direct sends,
  broadcasts, room persistence, optional discussion mode, task lifecycle, daemon
  restart, and clean fake-agent failure handling.

## [0.1.0] — 2026-05-17

### Added — initial public release

**Daemon and routing**

- Local HTTP daemon (`synkraken-daemon`) listening on `127.0.0.1:9460` by default.
- Stdlib-only HTTP server (`http.server.ThreadingHTTPServer`); no runtime dependencies.
- SQLite persistence for messages, deliveries, dead letters, rooms, and room members.
- Routing engine resolving `target = "<adapter>"`, `"broadcast"`, or `"room:<name>"`.
- Retry-with-backoff per delivery; failed deliveries land in a dead-letter table.
- Server-sent events stream at `/v1/events/stream` publishing
  `message.accepted`, `typing.started`, `typing.stopped`, `delivery.recorded`,
  and `dead-letter.recorded`.

**Adapters**

- `goose` — Block's Goose CLI via `goose run --text … --quiet --no-session`.
- `hermes` — Hermes agent via its Python CLI.
- `openclaw` — OpenClaw via `openclaw agent --agent <id> --message <body> --json`.
- `claude` — Anthropic Claude Code via `claude -p`. Supports OAuth or
  `ANTHROPIC_API_KEY`, with optional `--bare` and `--permission-mode` knobs.

**Rooms**

- Persistent multi-agent chat rooms (`room:<name>`).
- API CRUD: list, create, fetch, delete; add/remove members; fetch transcript.
- Each member's reply is automatically posted back into the room transcript,
  so the conversation reads as a flowing thread.

**Operator CLI and TUI**

- `synkraken health | agents | send | broadcast | recent | deliveries | dead-letters | history`.
- Curses TUI (`synkraken tui`) with:
  - SYNKRAKEN kraken sigil + wordmark with vertical ocean-fade colour
    (truecolor on terminals that support it, 256-color and 8-color fallbacks).
  - Boxed panels (dashboard, events, conversations, rooms, deadletters,
    adapters, help, chat, command-result) with rounded chrome.
  - Dashboard with three panels: BRIDGE STATUS / CHAT TARGETS,
    LATEST REPLIES (inbox), RECENT CONVERSATIONS.
  - Chat-bubble rendering for conversation and room transcripts.
  - `@goose hi`, `@hermes @claude debate this`, `@everyone …` natural mention syntax.
  - `#room hi` shorthand and Slack-style in-room mode after `/open <name>` or `/room enter`.
  - Asynchronous sends with an animated braille spinner — UI never freezes
    while a runtime takes 10+ seconds to reply.
  - Tab-completion for commands, mentions, room subcommands, targets.
  - SIGINT double-tap to quit, SSE-driven typing indicators.

**Portable bridge skill**

- `skills/synkraken-bridge/SKILL.md` is the documentation other agents read
  to learn how to participate. `synkraken config` discovers locally installed
  runtimes and copies the skill into each one's expected skill directory
  (folder format for Hermes / OpenClaw / Claude Code; single-file for Goose).

### Notes

- This is a v0.1.0 release. The HTTP API and the SQLite schema are stable for
  this minor; they may change before 1.0.
- All paths default to standard locations under `$HOME` and `$PATH`; nothing
  is hardcoded to a specific user.

[Unreleased]: https://github.com/example/synkraken/compare/v0.1.0...HEAD
[0.1.0]:      https://github.com/example/synkraken/releases/tag/v0.1.0
