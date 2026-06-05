# v1.1 Workforce Assignment And Handoffs PRD

## Problem

SynKraken can create missions, outcomes, rooms, broadcasts, and worker replies,
but room chat alone does not make a workforce. Operators can see activity, yet
ownership is not explicit enough. A worker may reply, but the operator cannot
quickly tell who owns the work, who is contributing, who is blocked, who is
waiting, which handoffs happened, or whether the work reached review or
completion.

This produces multiple intelligent agents in a chat room rather than an AI
workforce.

## User Workflow

1. The operator creates an Assignment from Console.
2. The operator assigns exactly one owner worker.
3. The operator assigns zero or more contributor workers.
4. The Assignment may link to a mission, outcome, and room.
5. The operator changes assignment state as work progresses: assigned,
   in-progress, waiting, blocked, review, completed, cancelled.
6. The operator records an explicit handoff when ownership moves from one
   worker to another.
7. The operator observes assignment ownership in Assignment Centre, room
   context, workforce rows, mission detail, outcome detail, and canvas nodes.
8. The operator sees handoff history as a visual timeline without reading the
   entire transcript.

## Architecture

Assignment is a durable daemon-owned workforce accountability record. It is
not a task, ticket, project item, schedule, kanban card, or automation unit.

Rules:

- one owner
- many contributors
- owner is accountable
- contributors assist
- handoff is explicit and auditable
- escalation, review, blocking, and completion are operator-initiated or
  explicitly proposed
- no automatic reassignment
- no autonomous execution

SQLite remains authoritative. Console uses daemon HTTP APIs. No adapters,
runtime calls, scheduling engines, or LLM integrations are added.

The existing handoff table remains the durable handoff ledger and gains an
assignment link. Assignment handoffs are read through assignment-scoped and
global handoff views.

## Read Models

Storage exposes deterministic local read models:

- `create_assignment()`
- `update_assignment_status()`
- `set_assignment_owner()`
- `add_assignment_contributor()`
- `remove_assignment_contributor()`
- `create_assignment_handoff()`
- `list_assignments()`
- `get_assignment()`
- `assignment_summary()`
- `assignment_activity()`
- `assignment_handoffs()`
- `assignment_proposals()`
- `assignment_traces()`
- `worker_assignments()`
- `mission_assignments()`
- `outcome_assignments()`
- `room_assignments()`
- `recent_assignment_handoffs()`

Read models derive worker ownership and contribution from assignment records.
They do not infer ownership from chat activity.

## UI Changes

Navigation:

- Add Assignments between Outcomes and Activity.

Assignment Centre:

- Show "My Workforce Assignments".
- Group assignments by Assigned, In Progress, Waiting, Blocked, Review, and
  Completed.
- Each assignment card shows title, owner, contributors, mission, outcome,
  status, and last activity.

Assignment Detail:

- Description
- Owner
- Contributors
- Timeline
- Activity
- Handoffs
- Related Room
- Related Outcome
- Related Mission
- Related Proposals
- Related Traces

Rooms:

- Show current assignments owned by workers in the room.
- Show recent handoffs.
- Show blocked assignments.

Workforce:

- Show current assignment count.
- Show owned assignments.
- Show contributor assignments.
- Show waiting, blocked, and review assignment counts.

Missions:

- Add Assignments grouped by In Progress, Waiting, Blocked, Review, and
  Completed.

Outcomes:

- Show assignments contributing to the outcome.

Canvas:

- Add Assignment node.
- Relationships: Mission -> Outcome -> Assignment -> Worker.
- Display ownership visually.
- No canvas editing in v1.1.

Command Palette:

- Create Assignment
- Assign Worker
- Add Contributor
- Mark Waiting
- Mark Blocked
- Request Review
- Complete Assignment
- View Handoffs
- Focus Assignment

## APIs

Read endpoints:

- `GET /v1/assignments`
- `GET /v1/assignments/summary`
- `GET /v1/assignments/{id}`
- `GET /v1/assignments/{id}/activity`
- `GET /v1/assignments/{id}/handoffs`
- `GET /v1/assignments/{id}/proposals`
- `GET /v1/assignments/{id}/traces`
- `GET /v1/workforce/{worker_id}/assignments`
- `GET /v1/missions/{id}/assignments`
- `GET /v1/outcomes/{id}/assignments`
- `GET /v1/rooms/{name}/assignments`
- `GET /v1/handoffs/recent`

Write endpoints:

- `POST /v1/assignments`
- `PATCH /v1/assignments/{id}`
- `POST /v1/assignments/{id}/contributors`
- `DELETE /v1/assignments/{id}/contributors/{worker_id}`
- `POST /v1/assignments/{id}/handoff`

All write endpoints append assignment events. Handoff writes also append
handoff events and update assignment owner/status.

## Acceptance Criteria

- Operator can create Assignment from Console.
- Operator can assign owner from Console.
- Operator can assign contributors from Console.
- Operator can view Assignment detail from Console.
- Operator can view Handoffs from Console.
- Operator can view ownership, blockers, review state, and completion from
  Console.
- Rooms show current assignments, recent handoffs, and blocked assignments.
- Workforce rows show assignment counts and ownership/contribution state.
- Mission detail shows grouped assignments.
- Outcome detail shows contributing assignments.
- Canvas includes Assignment nodes and relationship lines where daemon records
  support them.
- Handoff timeline shows ownership movement in readable sequence.
- No automatic reassignment, handoff, escalation, scheduling, planning, or
  autonomous execution is introduced.

## Testing Plan

- `python3 scripts/workforce_assignment_smoke_test.py`
- `python3 scripts/workforce_handoff_smoke_test.py`
- `python3 scripts/console_assignment_centre_smoke_test.py`
- `python3 scripts/console_handoff_timeline_smoke_test.py`
- `npm run build` from `apps/console`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`
- `git diff --check`

## Out Of Scope

- autonomy
- automatic reassignment
- automatic handoff
- automatic escalation
- scheduling
- planning
- project management
- kanban boards
- gantt charts
- new agent adapters
- new LLM integrations
- autonomous execution
- workflow automation engines
- canvas editing
- RBAC or auth
