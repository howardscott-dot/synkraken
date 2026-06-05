# Assignment Model

Assignment is the workforce accountability object for SynKraken v1.1.

An assignment is work currently owned by one worker. It can link to a mission,
outcome, and room, and it can list many contributor workers. It is not a task,
ticket, project item, schedule, kanban card, gantt item, or automation unit.

## Fields

The deterministic assignment record contains:

- `assignment_id`
- `title`
- `description`
- `status`
- `owner_worker`
- `contributor_workers`
- `mission_id`
- `outcome_id`
- `room_id`
- `created_at`
- `updated_at`

Valid statuses are:

- `assigned`
- `in_progress`
- `waiting`
- `blocked`
- `handoff`
- `review`
- `completed`
- `cancelled`

## Workforce Rules

- one owner
- many contributors
- owner is accountable
- contributors assist
- owner can hand off
- owner can escalate
- owner can request review

All changes are operator initiated or explicitly proposed. SynKraken does not
automatically reassign, hand off, escalate, schedule, or complete assignments.

## Handoffs

Assignment handoffs record:

- `from_worker`
- `to_worker`
- `assignment_id`
- `reason`
- `context_summary`
- `timestamp`

The handoff timeline answers who owned the work, who received it, why the work
moved, and what context moved with it.

## Read Models

The storage layer exposes:

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

These are deterministic SQLite read models. They do not infer ownership from
chat activity and do not call AI models.

## API

The daemon exposes:

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
- `POST /v1/assignments`
- `PATCH /v1/assignments/{id}`
- `POST /v1/assignments/{id}/contributors`
- `DELETE /v1/assignments/{id}/contributors/{worker_id}`
- `POST /v1/assignments/{id}/handoff`

## Console

Assignment Centre groups ownership by Assigned, In Progress, Waiting, Blocked,
Review, and Completed. Assignment detail shows description, owner,
contributors, activity, handoffs, related room, related outcome, related
mission, related proposals, and related traces.

Assignment detail also shows approved assignment-scoped workforce memory.
Operators can create assignment context memory through Memory Centre or scoped
note controls where available. Rejected and archived memory are audit records,
not active assignment context.

Rooms show current assignments, recent handoffs, and blocked assignments.
Workforce rows show assignment counts. Mission and Outcome detail surfaces show
linked assignments. Canvas includes Assignment nodes and evidence-backed
relationships.
