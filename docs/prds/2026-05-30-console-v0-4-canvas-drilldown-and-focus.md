# Console v0.4 Canvas Drilldown And Focus PRD

## Objective

Make Operations Canvas more usable as the primary Console workspace by adding
operator drilldown, better object focus flows, node search, lightweight canvas
inspector details, and clearer local layout controls without changing daemon
ownership or adding Rust business logic.

Console v0.4 remains a React/TypeScript UI layer over existing daemon APIs.
Rust remains shell, packaging, native integration, future notifications, and
future system tray only.

## Problem

Console v0.3 introduced the spatial canvas foundation, but object inspection is
still split between small node bodies and legacy pages. Operators need a fast
way to select a node, inspect richer detail in context, jump to related
objects, and focus daemon objects from the command palette without losing the
canvas workspace.

## User Workflow

1. Operator opens Operations Canvas.
2. Operator searches or command-focuses a runtime, proposal, trace, room,
   incident, or dead-letter object.
3. Console focuses or creates the relevant node on the canvas.
4. Operator selects a node and sees a right-side Canvas Inspector with richer
   fields, related objects, actions, and links to legacy detail views.
5. Operator can add runtime, room, proposal detail, trace, incident, or
   dead-letter nodes from the canvas toolbar or command palette.
6. Operator can jump between related nodes from the inspector where daemon
   fields expose relationships.
7. Operator can clear the local saved layout when the workspace needs a clean
   start.

## Screens/Components Affected

- Operations Canvas
- Canvas toolbar
- Canvas node model and focus logic
- Canvas Inspector side panel
- Command palette
- Local layout persistence controls
- Existing Console v0.2/v0.3 legacy routes remain accessible

## APIs Used

- `GET /health`
- `GET /v1/agents`
- `GET /v1/workforce`
- `GET /v1/workforce/health`
- `GET /v1/rooms`
- `GET /v1/rooms/{name}`
- `GET /v1/rooms/{name}/messages`
- `GET /v1/proposals`
- `GET /v1/proposals/pending`
- `GET /v1/proposal/{id}`
- `POST /v1/proposal/approve`
- `POST /v1/proposal/reject`
- `POST /v1/proposal/execute`
- `GET /v1/trace/{id}`
- `GET /v1/replay/{id}`
- `GET /v1/incident/latest`
- `GET /v1/dead-letters?limit=N`

## Files Expected To Change

- `apps/console/src/App.tsx`
- `apps/console/src/styles.css`
- `apps/console/README.md`
- `README.md`
- `CHANGELOG.md`
- `docs/COMMAND_DECK_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/prds/2026-05-30-console-v0-4-canvas-drilldown-and-focus.md`
- `scripts/console_v04_canvas_drilldown_smoke_test.py`

## Acceptance Criteria

- Operations Canvas has a Canvas Inspector that appears for selected nodes.
- Inspector shows node type, status, daemon object id, richer object fields,
  related object buttons, and links to legacy views where useful.
- Canvas toolbar can add Runtime, Room, Proposal Detail, Trace, Incident, Dead
  Letter, Workforce, and Proposal Queue nodes.
- Canvas toolbar has a search/focus input that focuses an existing node or adds
  a reasonable node type based on live daemon data.
- Command palette can add Runtime, Room, Proposal Detail, Dead Letter nodes in
  addition to v0.3 commands.
- Focus Runtime, Focus Proposal, and Focus Trace create a node if missing and
  focus it on the canvas.
- Local layout controls include save, reset preset layout, and clear saved
  layout.
- No Stitch mock data is used as production data.
- No daemon endpoint is added unless a missing detail blocks the scope.
- No Rust business logic is added.

## Test Plan

- `npm run build` from `apps/console`
- `npm run tauri build` from `apps/console` if environment supports it
- `python3 scripts/console_v02_smoke_test.py`
- `python3 scripts/console_v03_spatial_canvas_smoke_test.py`
- `python3 scripts/console_v04_canvas_drilldown_smoke_test.py`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`

## Explicit Out Of Scope

- Daemon layout persistence
- Daemon graph relationship endpoints
- Full graph auto-layout
- Semantic zoom
- Multiplayer collaboration
- Detached OS windows
- Terminal, editor, or browser panels
- Auth/RBAC
- Native notification implementation
- System tray implementation
- Rust business logic
- AI-generated layouts
- New execution semantics beyond existing proposal governance APIs

## Completion Update

### Completed

- Added Canvas Inspector for selected nodes.
- Added inspector detail sections for workforce summary, runtime, room,
  proposal queue, proposal detail, incident, trace, and dead-letter nodes.
- Added related object jump buttons where current daemon data exposes usable ids.
- Added canvas focus/search input that infers runtime, room, proposal,
  dead-letter, incident, proposal queue, or trace targets from live data.
- Added toolbar add-node control for all v0.3 node types.
- Added command-palette entries for Add Runtime Node, Add Room Node, Add
  Proposal Detail Node, Add Dead Letter Node, Focus Room, and Clear Saved
  Layout.
- Improved focus/create behavior so missing nodes are created and centered.
- Added Clear Saved layout control for localStorage reset.
- Added `scripts/console_v04_canvas_drilldown_smoke_test.py`.
- Updated Console README, root README, changelog, Command Deck spec, and
  architecture docs.

### Deferred

- Daemon-provided relationship metadata remains deferred.
- Inspector data remains bounded to already-loaded daemon API responses.
- Rich graph auto-layout, semantic zoom, collaboration, native notifications,
  system tray, and daemon layout persistence remain out of scope.

### Tests Run

- `npm run build` from `apps/console`: passed.
- `python3 scripts/console_v02_smoke_test.py`: passed.
- `python3 scripts/console_v03_spatial_canvas_smoke_test.py`: passed.
- `python3 scripts/console_v04_canvas_drilldown_smoke_test.py`: passed.
- `python3 scripts/context_audit.py`: passed with the existing LICENSE
  copyright exception.
- `python3 -m compileall synkraken scripts`: passed.
- `npm run tauri build` from `apps/console`: partially completed; frontend
  build, Rust release compile, DEB bundle, and RPM bundle completed, then the
  overall command failed during AppImage packaging with `failed to run
  linuxdeploy`.

### Known Limitations

- Focus/search falls back to a Trace node for unknown ids because arbitrary ids
  may be replay or trace ids.
- Relationship counts in the inspector are based on client-inferred SVG line
  data, not daemon-owned graph records.
- Full proposal, room, trace, and incident workflows remain in legacy detail
  views; the inspector is a fast drilldown surface, not a replacement workflow.
