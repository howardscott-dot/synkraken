# Console v0.2 Operator Command Centre PRD

## Objective

Transform SynKraken Console v0.1 from a developer-facing viewer into an operator command centre for workforce visibility, room operations, proposal governance, incident management, and flight recorder investigation.

Console v0.2 remains a local Tauri desktop client for the daemon. It must use daemon HTTP APIs only, must not read SQLite directly, and must not add a second backend or autonomous execution authority.

## Problem

Console v0.1 exposes useful daemon records but presents several operator-critical areas as cards or raw JSON. Operators need dense, first-read understanding of workforce state, room activity, proposal risk, incidents, dead letters, and replay timelines without treating raw records as the primary interface.

## User Workflow

1. Operator opens Console and sees daemon status plus fleet-level health counts in a persistent global bar.
2. Operator reviews Workforce Command Centre, sorts runtimes by health, trust, latency, or incidents, and opens a runtime drawer for delivery, proposal, incident, and trace context.
3. Operator opens Rooms, selects `#ops`, `#coding`, `#research`, or `#security`, inspects members, notes, deliveries, proposals, activity, and sends a room broadcast or member update through existing room APIs.
4. Operator opens Flight Recorder, loads a replay id, reads a timeline grouped by message, reply, handoff, proposal, approval, execution, incident, and failure, then filters by type, runtime, or failure state.
5. Operator opens Proposal Governance, works through the pending queue, inspects proposal detail, and approves, rejects, or executes via existing governance endpoints.
6. Operator opens Incident Centre, sees active incident summaries, failing runtimes, dead letters, and recommended recovery actions, with raw data available as drill-down detail only.
7. Operator uses `Ctrl+K` to navigate to major screens and search runtime, proposal, or trace context.

## Screens Affected

- Global shell and status bar
- Workforce Command Centre
- Rooms
- Flight Recorder
- Proposal Governance
- Proposal Detail
- Incident Centre
- Command Palette

## APIs Used

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

## Files Expected To Change

- `apps/console/src/App.tsx`
- `apps/console/src/lib/api.ts`
- `apps/console/src/lib/format.ts`
- `apps/console/src/styles.css`
- `apps/console/README.md`
- `docs/COMMAND_DECK_SPEC.md`
- `README.md`
- `scripts/console_v02_smoke_test.py`
- `docs/prds/2026-05-29-console-v0-2-operator-command-centre.md`

## Acceptance Criteria

- Workforce card view is replaced by a sortable operations table with Runtime, Health, Trust, Status, Last Seen, Cost Tier, Average Latency, Recent Failures, and Recent Empty Replies.
- Runtime selection opens a detail drawer showing reputation summary, incident summary, delivery history, proposal history, and linked trace ids when available from daemon records.
- Rooms is a first-class screen with room list, selected room detail, members, room notes, recent activity, latest deliveries, proposal activity, add runtime, remove runtime, room broadcast, and history inspection.
- Room text rendering recognizes `@everyone`, `@runtime-id`, and `#room` tokens visually.
- Flight Recorder uses `GET /v1/replay/{id}` as the primary replay API and renders an operator timeline with summary counts and filters for type, runtime, and failure state.
- Proposal Governance renders pending proposals as a queue with risk, approval requirement, proposer, room, goal, and timestamp, with approve, reject, and execute actions.
- Proposal Detail shows full proposal, governance evaluation, linked traces, linked decisions, and linked handoffs when present.
- Incident Centre replaces primary raw JSON with active incidents, failing runtimes, dead letters, recovery actions, and raw drill-down.
- Global status bar shows daemon status, active agents, healthy, degraded, failing, pending proposals, incidents, and dead letters.
- Command Palette supports navigation to Workforce, Rooms, Proposals, Flight Recorder, Incidents, plus Search Runtime, Search Proposal, and Search Trace.
- Console polls every 3-5 seconds without blocking UI interaction.
- UI remains dark, dense, cyan-accented, and operator-oriented, with raw JSON secondary.
- Implementation avoids auth, RBAC, multi-user accounts, MCP integration, autonomous actions, shell execution, settings redesign, mobile UI, and cloud deployment.

## Test Plan

- `npm run build`
- `npm run tauri build`
- `python3 -m compileall synkraken scripts`
- `python3 scripts/context_audit.py`
- `python3 scripts/console_v02_smoke_test.py`

## Explicit Out Of Scope

- Authentication
- RBAC
- Multi-user accounts
- MCP integration
- Agent execution
- Autonomous actions
- Real shell execution
- Settings redesign
- Mobile UI
- Cloud deployment
- New daemon-owned workflow semantics
- Direct SQLite reads from Console
- SSE implementation for Console v0.2; polling is the required live-refresh mechanism

## Completion Update

### Completed

- Replaced the workforce card view with a sortable runtime operations table.
- Added runtime detail drawer with reputation, incidents, delivery counters, proposal counters, raw data, and linked trace buttons where ids are present.
- Added first-class Rooms screen for `#ops`, `#coding`, `#research`, `#security`, room member inspection, add/remove member actions, notes, activity, room broadcast, room-linked proposal activity, and `@` / `#` token highlighting.
- Added Flight Recorder screen using `GET /v1/replay/{id}` with summary counts, timeline rendering, type/runtime/failure filters, and secondary raw replay data.
- Upgraded Proposal Governance to a pending queue plus all-proposals table with risk, approval requirement, proposer, room, goal, timestamp, detail, approve, reject, and execute actions.
- Upgraded Proposal Detail with full proposal summary, governance evaluation, linked trace/decision/handoff buttons, events timeline, and secondary raw data.
- Replaced incident raw JSON primary view with Incident Centre cards for failing runtimes, dead letters, recommended recovery actions, and raw drill-down.
- Added persistent global status bar with daemon status, active agents, health counts, pending proposals, incidents, and dead letters.
- Extended `Ctrl+K` command palette for major navigation plus runtime, proposal, and trace search.
- Added polling refresh at 4 seconds for global data and 5 seconds for room detail.
- Added `scripts/console_v02_smoke_test.py`.
- Updated Console README, root README, and Command Deck spec.
- Updated context audit exclusions for generated Console frontend/build directories.
- Fixed Tauri bundle icon configuration and added missing generated Console icon variants needed by bundling.

### Deferred

- SSE-driven live updates remain deferred; Console v0.2 uses polling as scoped.
- Full memory governance, goal mode, team task mode, decision management, handoff management, native notifications, settings, auth, and cloud features remain out of scope.
- Screenshots were not generated in this implementation pass.

### Tests Run

- `npm run build` from `apps/console`: passed.
- `python3 scripts/console_v02_smoke_test.py`: passed.
- `python3 -m compileall synkraken scripts`: passed.
- `python3 scripts/context_audit.py`: passed.
- `npm run tauri build` from `apps/console`: passed after allowing AppImage packaging to download the AppImage type2 runtime; produced DEB, RPM, and AppImage bundles.

### Limitations

- Console derives delivery history and linked trace visibility from fields already returned by existing daemon responses; it does not add new daemon endpoints for per-runtime delivery drill-down.
- Room "latest deliveries" are represented through recent room transcript and room-linked proposal context because the daemon does not expose a room-scoped delivery list endpoint.
- Incident "active" state is inferred from runtime health, incident summaries, and dead letters returned by existing APIs.
- `icon.icns` was not generated because no ICNS tool was available in this Linux environment; Linux and Windows icon assets are present and Tauri Linux bundling passes.
