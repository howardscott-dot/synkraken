# Console v0.5 Real Canvas Relationships PRD

## Objective

Replace Console canvas relationship inference with daemon-backed, reproducible
relationship data derived from persisted SynKraken records. Inspector jumps
must use these daemon relationships where available, so canvas relationships are
real control-plane facts rather than client guesses.

## Problem

Console v0.3 and v0.4 draw useful relationship hints, but they infer links in
the React client from already-loaded records. That is acceptable as a visual
foundation but not enough for an operator surface that claims object
relationships. v0.5 needs a daemon API that materializes relationships from the
authoritative SQLite-backed records and lets the UI render and navigate those
relationships directly.

## User Workflow

1. Operator opens Operations Canvas.
2. Console loads daemon relationship data for current canvas object types.
3. Canvas renders only relationships returned by the daemon relationship API.
4. Operator selects a node and sees inspector related-object jumps backed by
   relationship records.
5. Operator clicks a relationship jump; Console focuses or creates the target
   node using the relationship target type and target id.
6. If daemon data has no relationship for an object, Console shows no
   relationship rather than inventing one.

## Screens/Components Affected

- Daemon HTTP API
- Storage read helpers if needed
- Console API client
- Operations Canvas relationship renderer
- Canvas Inspector related-object sections
- Console v0.5 smoke test
- Existing v0.2/v0.3/v0.4 views remain accessible

## APIs Used

Existing APIs remain in use:

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

New v0.5 API:

- `GET /v1/canvas/relationships`

The new endpoint returns relationship records derived from existing persisted
daemon records only. It must not create new durable workflow state.

## Files Expected To Change

- `synkraken/api.py`
- `synkraken/storage.py` if a storage helper is cleaner than API-local assembly
- `apps/console/src/lib/api.ts`
- `apps/console/src/App.tsx`
- `apps/console/README.md`
- `README.md`
- `CHANGELOG.md`
- `docs/COMMAND_DECK_SPEC.md`
- `docs/ARCHITECTURE.md`
- `docs/prds/2026-05-31-console-v0-5-real-canvas-relationships.md`
- `scripts/console_v05_real_relationships_smoke_test.py`

## Acceptance Criteria

- Daemon exposes `GET /v1/canvas/relationships`.
- Relationship records include id, source type, source id, target type, target
  id, relationship kind, status/tone, evidence, and created/observed timestamp
  where available.
- Relationship records are derived from persisted records such as proposals,
  proposal links, proposer ids, rooms, messages, deliveries, dead letters,
  trace/replay records, runtime reputation, and latest incident context.
- Console fetches relationship records through the API client.
- Canvas relationship lines are rendered from daemon relationship records only.
- Canvas Inspector related jumps are rendered from daemon relationship records
  only.
- Missing relationships are omitted.
- No Stitch mock data or hardcoded production relationship data is used.
- No Rust business logic is added.
- Existing Console v0.2/v0.3/v0.4 screens remain routable.

## Test Plan

- `npm run build` from `apps/console`
- `npm run tauri build` from `apps/console` if environment supports it
- `python3 scripts/console_v02_smoke_test.py`
- `python3 scripts/console_v03_spatial_canvas_smoke_test.py`
- `python3 scripts/console_v04_canvas_drilldown_smoke_test.py`
- `python3 scripts/console_v05_real_relationships_smoke_test.py`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`

## Explicit Out Of Scope

- Client-inferred production relationship lines
- Fake telemetry
- Stitch mock data
- New workflow semantics
- New proposal execution authority
- Daemon layout persistence
- Auth/RBAC
- Rust business logic
- Graph auto-layout
- Semantic zoom
- Multiplayer collaboration
- Detached windows, terminal panels, editor panels, or browser panels

## Completion Update

### Completed

- Added daemon endpoint `GET /v1/canvas/relationships`.
- Added storage read model `Storage.list_canvas_relationships()`.
- Relationship records include id, source type/id, target type/id, kind, tone,
  status, evidence, and observed timestamp.
- Relationship records are derived from persisted proposals, proposal room
  links, proposer ids, linked message ids, dead letters, runtime reputation,
  and latest incident anchors.
- Console API client now fetches canvas relationships from the daemon.
- Operations Canvas line rendering now uses daemon relationship records only.
- Canvas Inspector relationship jumps now use daemon relationship records only.
- Missing relationships are omitted.
- Added `scripts/console_v05_real_relationships_smoke_test.py`.
- Updated Console README, root README, changelog, Command Deck spec, and
  architecture docs.

### Deferred

- Graph auto-layout remains deferred.
- Relationship coverage is limited to relationships derivable from current
  persisted records.
- Daemon layout persistence remains deferred.

### Tests Run

- `npm run build` from `apps/console`: passed.
- `python3 scripts/console_v02_smoke_test.py`: passed.
- `python3 scripts/console_v03_spatial_canvas_smoke_test.py`: passed.
- `python3 scripts/console_v04_canvas_drilldown_smoke_test.py`: passed.
- `python3 scripts/console_v05_real_relationships_smoke_test.py`: passed.
- `python3 scripts/context_audit.py`: passed with the existing LICENSE
  copyright exception.
- `python3 -m compileall synkraken scripts`: passed.
- `npm run tauri build` from `apps/console`: partially completed; frontend
  build, Rust release compile, DEB bundle, and RPM bundle completed, then the
  overall command failed during AppImage packaging with `failed to run
  linuxdeploy`.

### Known Limitations

- Relationship records are a read model over existing data; they do not create
  new durable graph state.
- Trace relationships require a persisted message id or incident/proposal link.
- The canvas still uses manual node placement and localStorage layout
  persistence.
