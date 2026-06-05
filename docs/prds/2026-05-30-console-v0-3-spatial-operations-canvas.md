# Console v0.3 Spatial Operations Canvas PRD

## Objective

Introduce Operations Canvas as the default SynKraken Console landing view and first foundation for a spatial AI workforce operating system. The canvas represents live daemon-owned objects as movable node panels while preserving all Console v0.2 page-based screens as accessible detail/backstop views.

Console v0.3 remains a Tauri desktop client over daemon HTTP APIs. Rust remains limited to shell, packaging, native integration, future notifications, and future system tray support. Business logic remains in the daemon and APIs; UI logic remains in React/TypeScript.

## Problem

Console v0.2 improved operational visibility but still organizes SynKraken like a conventional dashboard with separate pages. SynKraken's durable objects are interconnected operational entities: runtimes, rooms, proposals, traces, incidents, and dead letters. Operators need a spatial control-plane surface where relationships between these objects are visible without replacing the underlying daemon model or inventing client-only telemetry.

## User Workflow

1. Operator opens Console and lands on Operations Canvas.
2. Operator selects a workspace preset: Coding, Operations, Research, or Incident Response.
3. Console arranges deterministic node panels for the selected workspace using live daemon API data.
4. Operator pans, zooms, moves nodes, selects nodes, focuses nodes, fits the canvas, resets layout, and saves layout locally.
5. Operator inspects Workforce Summary, Runtime, Room, Proposal Queue, Proposal Detail, Incident, Trace, and Dead Letter nodes.
6. Operator follows visible relationship lines where daemon data supports links, such as proposal-to-runtime, room-to-proposal, incident-to-dead-letter, runtime-to-incident, and trace-to-dead-letter.
7. Operator uses `Ctrl+K` to open Operations Canvas, switch workspaces, add/focus nodes, fit canvas, reset layout, or focus runtime/proposal/trace objects.
8. Operator can still open Console v0.2 Workforce, Rooms, Proposals, Trace, and Incidents screens from the left navigation.

## Screens/Components Affected

- Global shell and left navigation
- Command palette
- New Operations Canvas view
- Canvas toolbar and workspace switcher
- Canvas node model and node rendering components
- Relationship line renderer
- Local layout persistence
- Existing Workforce, Rooms, Flight Recorder/Trace, Proposal Governance, Proposal Detail, and Incident Centre routes

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
- `apps/console/src/lib/api.ts`
- `apps/console/src/styles.css`
- `apps/console/README.md`
- `README.md`
- `CHANGELOG.md`
- `docs/COMMAND_DECK_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/prds/2026-05-30-console-v0-3-spatial-operations-canvas.md`
- `scripts/console_v03_spatial_canvas_smoke_test.py`

## Acceptance Criteria

- Operations Canvas is the default Console view and the left nav includes Canvas, Workforce, Rooms, Proposals, Trace, and Incidents.
- Existing Console v0.2 screens remain routable and functionally present.
- Canvas supports pan, zoom, node movement, node selection, node focus, fit to view, reset layout, save layout locally, and restore layout after reload.
- Layout is persisted in localStorage and includes node id, node type, x, y, width, height, collapsed state if implemented, and selected workspace.
- Workspace presets are defined for Coding, Operations, Research, and Incident Response with deterministic node layouts matching v0.3 scope.
- Node types implemented for v0.3: Workforce Summary, Runtime, Room, Proposal Queue, Proposal Detail, Incident, Trace, and Dead Letter.
- Every node has a 32px header, node type label, title, status chip, metadata row, body content, and action area when relevant.
- Node states include normal, selected, degraded, failing, pending approval, empty/no data, loading, and error where applicable.
- Relationship lines render as simple SVG lines over the canvas and use cyan, amber, or red based on inferred relationship health.
- Relationship data is inferred only from existing daemon API fields; missing links are omitted instead of mocked.
- Command palette supports Operations Canvas commands, workspace switches, add node commands, fit/reset layout, and focus runtime/proposal/trace commands.
- Proposal actions in canvas nodes use only existing approval, rejection, and simulated execution APIs.
- Trace and replay nodes consume existing trace/replay APIs and truncate large timelines inside nodes.
- Console uses real daemon APIs only and does not hardcode Stitch mock data as production data.
- Rust/Tauri code is not used for business logic or UI state management changes.

## Test Plan

- `npm run build` from `apps/console`
- `npm run tauri build` from `apps/console` if environment supports it
- `python3 scripts/console_v02_smoke_test.py`
- `python3 scripts/console_v03_spatial_canvas_smoke_test.py`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`

## Explicit Out Of Scope

- Full infinite semantic zoom
- Physics or drifting node animations
- Auto-layout engine
- Multiplayer or collaboration
- Detached OS windows
- Code editor panels
- Terminal panels
- Browser panels
- Monaco
- `node-pty`
- Authentication
- RBAC
- Daemon layout persistence
- AI-generated layouts
- New daemon workflow semantics
- Direct SQLite reads from Console
- Business logic moved into Rust
- Real execution beyond existing simulated governance
- Memory governance canvas node unless trivial
- Goal visual workflow unless already easy from existing data
- Stitch mock data as production data

## Completion Update

### Completed

- Added Operations Canvas as the default Console landing view.
- Added left navigation entry for Canvas while preserving Workforce, Rooms,
  Proposals, Trace, and Incidents views.
- Added React/TypeScript canvas node model for Workforce Summary, Runtime,
  Room, Proposal Queue, Proposal Detail, Incident, Trace, and Dead Letter nodes.
- Added deterministic workspace presets for Coding, Operations, Research, and
  Incident Response.
- Added pan, zoom, node movement, node selection, node focus, fit to view,
  reset layout, explicit save layout, and reload restore.
- Persisted selected workspace, node id, node type, x, y, width, height,
  collapsed field when present, and transform state in localStorage.
- Added simple SVG relationship lines for supported inferred relationships.
- Extended `Ctrl+K` command palette with Operations Canvas, workspace, add node,
  fit/reset, focus runtime, focus proposal, and focus trace commands.
- Kept proposal actions on existing approve, reject, and simulated execute APIs.
- Added `scripts/console_v03_spatial_canvas_smoke_test.py`.
- Updated Console README, root README, changelog, Command Deck spec, and
  architecture docs.

### Deferred

- Semantic zoom, physics animations, auto-layout, collaboration, detached OS
  windows, terminal/editor/browser panels, auth/RBAC, daemon layout persistence,
  AI-generated layouts, and new daemon graph APIs remain out of scope.
- Trace nodes render truncated summaries; full investigation remains in the
  existing Trace / Flight Recorder view.
- Room message composition remains in the Rooms view; the canvas Room node links
  there rather than duplicating the full room workflow.

### Tests Run

- `npm run build` from `apps/console`: passed.
- `python3 scripts/console_v02_smoke_test.py`: passed.
- `python3 scripts/console_v03_spatial_canvas_smoke_test.py`: passed.
- `python3 scripts/context_audit.py`: passed with the existing LICENSE
  copyright exception.
- `python3 -m compileall synkraken scripts`: passed.
- `npm run tauri build` from `apps/console`: partially completed; frontend
  build, Rust release compile, DEB bundle, and RPM bundle completed, then the
  overall command failed during AppImage packaging with `failed to run
  linuxdeploy`.

### Known Limitations

- Canvas relationship inference is intentionally conservative and omits links
  when existing daemon fields do not expose a clear relationship.
- Layout persistence is localStorage-only and not shared across machines,
  browsers, or daemon instances.
- Incident state is inferred from runtime health, latest incident context, and
  dead letters already returned by existing APIs.
- No daemon endpoints were added for canvas graph layout, node persistence, or
  relationship materialization.
- Rust/Tauri business logic was not added; native packaging remains shell-only.
