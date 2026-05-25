# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
