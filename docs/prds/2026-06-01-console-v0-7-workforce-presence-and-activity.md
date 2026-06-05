# Console v0.7: Workforce Presence & Activity

## Objective

Make SynKraken Console feel like a living AI workforce operating system rather
than an infrastructure dashboard. The operator should understand who is
available, who is active, who is idle, who needs attention, what happened
recently, and what to inspect next within 10 seconds.

## Problem

Console already exposes workforce health, reputation, rooms, incidents,
proposals, traces, and canvas nodes. Those records are useful but still read as
raw operational tables. Health and reputation do not directly answer:

- which workers are doing something now
- which workers are idle but available
- what each worker last did
- which room/proposal/trace a worker is connected to
- whether an issue matters to current work

## User/operator workflow

1. Operator opens Console.
2. The top summary shows workforce usability and presence counts.
3. Operator sees active workers and recent activity without opening raw traces.
4. Operator spots workers needing attention and sees a suggested action.
5. Operator opens Workforce for per-runtime presence, last activity, room
   context, idle time, raw health, trust, and suggested next action.
6. Operator opens Rooms and sees member presence beside room activity.
7. Operator opens Incident Centre and sees whether a problem affects active
   work or belongs on the watch list.
8. Operator uses the command palette to focus active workers, attention
   workers, rooms, or the Activity Feed node.

## Screens/components affected

- Console global data loading and app shell
- Operations Canvas presets and runtime nodes
- Workforce Command Centre
- Rooms member panel
- Incident Centre
- Command Palette
- Console API client types
- Daemon HTTP API read endpoints

## APIs used or changed

Added:

- `GET /v1/workforce/presence`
- `GET /v1/activity/recent?limit=50`

No existing daemon behavior is changed. The endpoints are deterministic read
models derived from existing persisted records: agents, runtime reputation,
messages, deliveries, dead letters, rooms, proposals, handoffs, decisions,
tasks, goals, and agent events where available.

## Files expected to change

- `synkraken/storage.py`
- `synkraken/fabric.py`
- `synkraken/api.py`
- `apps/console/src/lib/api.ts`
- `apps/console/src/App.tsx`
- `apps/console/src/styles.css`
- `scripts/workforce_presence_smoke_test.py`
- `scripts/console_workforce_presence_smoke_test.py`
- `CHANGELOG.md`
- `apps/console/README.md`
- `docs/UI_CONSOLE_DOCTRINE.md`
- `docs/OPERATOR_GUIDE.md`
- `docs/CORE_CONCEPTS.md`
- `docs/PRODUCT_DOCTRINE.md`

## Acceptance criteria

- `/v1/workforce/presence` returns a summary and per-worker presence rows.
- Worker rows include `presence_state`, latest activity, idle duration, current
  room/task/goal when derivable, attention reason, and suggested action.
- Presence states include `active`, `idle`, `watching`, `needs_attention`,
  `unavailable`, and `unknown`.
- `/v1/activity/recent` returns deterministic recent activity records.
- Console shows an Operator Activity Summary on Canvas and Workforce, and on
  Rooms where practical.
- Workforce screen renders presence-oriented rows.
- Runtime canvas nodes show presence, last activity, idle duration, room
  context, attention reason, and suggested action.
- Canvas presets include an Activity Feed node.
- Rooms show presence for room members and a calm empty state.
- Incident Centre uses presence/impact language.
- Red remains reserved for daemon offline, blocked, or critical active work.

## Test plan

- `python3 -m compileall synkraken scripts`
- `python3 scripts/workforce_presence_smoke_test.py`
- `python3 scripts/console_workforce_presence_smoke_test.py`
- `python3 scripts/console_operator_friendly_status_smoke_test.py`
- `python3 scripts/console_polling_stability_smoke_test.py`
- `python3 scripts/context_audit.py`
- `npm run build` from `apps/console`

## Explicit out of scope

- autonomous execution
- scheduling or background planning
- task queues
- calendar/time planning
- cross-machine distributed presence
- WebSocket/SSE changes
- desktop notifications
- user accounts or RBAC
- new adapters or adapter capabilities
- canvas redesign or auto-layout
- AI-generated summaries
- storage schema changes unless absolutely required

## Completion update

Completed work:

- Added deterministic workforce presence read model with active, idle,
  watching, needs_attention, unavailable, and unknown states.
- Added deterministic recent activity read model.
- Added `GET /v1/workforce/presence` and `GET /v1/activity/recent?limit=N`.
- Added Console API bindings for presence workers and activity records.
- Added Operator Activity Summary usage on Canvas, Workforce, and Rooms.
- Reworked Workforce Command Centre around presence, last activity, current
  room, idle duration, attention reason, suggested action, trust, and raw
  health.
- Updated runtime canvas nodes to show presence and operator action.
- Added Activity Feed canvas node and included it in Coding, Operations, and
  Incident Response presets.
- Added room member presence and calm empty-room guidance.
- Updated Incident Centre framing to use presence/active-room impact.
- Added presence command-palette actions.
- Updated docs and changelog with Presence, Activity Feed, Active worker, Idle
  worker, and Needs attention concepts.

Deferred work:

- No SSE/WebSocket live presence stream; Console still polls.
- No cross-machine distributed presence.
- No scheduling, queueing, or autonomous assignment.
- Activity summaries remain concise deterministic records rather than rich
  narrative summaries.
- Presence derives current goal/task only where existing records expose it
  simply.

Tests run:

- `python3 -m compileall synkraken scripts`
- `python3 scripts/workforce_presence_smoke_test.py`
- `python3 scripts/console_workforce_presence_smoke_test.py`
- `python3 scripts/console_operator_friendly_status_smoke_test.py`
- `python3 scripts/console_polling_stability_smoke_test.py`
- `python3 scripts/context_audit.py`
- `npm run build` from `apps/console`

Known limitations:

- Presence is a local deterministic read model over persisted records, not a
  liveness protocol.
- Registry-only runtimes are treated as unavailable because they are not active
  workers.
- Incident impact uses available presence, room, proposal, and dead-letter
  evidence; it does not infer hidden dependencies.
