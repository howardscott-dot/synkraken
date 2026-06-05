# Mission Model

Mission is the primary organisational object for SynKraken v0.9 Mission
Control.

A mission represents a meaningful piece of AI workforce work under governance.
It is not a task, project, ticket, schedule, board, sprint, or workload-specific
business entity. It is a durable container that connects the people and records
needed to inspect work, risk, decisions, failures, and outcomes.

## Fields

The deterministic mission record contains:

- `mission_id`
- `title`
- `description`
- `status`
- `priority`
- `created_at`
- `updated_at`
- `owner`
- `goal`
- `outcome`
- `risk_level`

Valid statuses are:

- `proposed`
- `active`
- `blocked`
- `review`
- `completed`
- `cancelled`

Valid priorities are:

- `low`
- `medium`
- `high`
- `critical`

## Links

Missions support durable links to:

- outcomes
- assignments
- workers
- rooms
- traces
- incidents
- proposals
- relationships

Mission links are read-model inputs for Mission Centre, activity filters, room
context, workforce context, incidents, and canvas relationships.

## Read Models

The storage layer exposes:

- `list_missions()`
- `get_mission()`
- `mission_summary()`
- `mission_activity()`
- `mission_workers()`
- `mission_proposals()`
- `mission_incidents()`
- `list_mission_outcomes()`
- `mission_assignments()`

These are deterministic local SQLite read models. They do not schedule work,
infer progress, or call an AI model.

## Progress

Mission progress is calculated from linked outcomes:

```text
completed outcomes / total outcomes
```

For example, `2 / 5 outcomes completed` is 40 percent progress. Mission
progress is not inferred from message volume, worker activity, or AI-generated
summaries.

## API

The daemon exposes read endpoints:

- `GET /v1/missions`
- `GET /v1/missions/{id}`
- `GET /v1/missions/summary`
- `GET /v1/missions/{id}/activity`
- `GET /v1/missions/{id}/workers`
- `GET /v1/missions/{id}/incidents`
- `GET /v1/missions/{id}/proposals`
- `GET /v1/missions/{id}/outcomes`
- `GET /v1/missions/{id}/assignments`

Activity also supports mission-aware filtering through `/v1/activity/live`
query parameters:

- `mission=<mission_id>`
- `active_missions=true`

## Console

Mission Centre is a governance cockpit. It shows mission summary counts,
mission progress from outcomes, mission table rows, selected mission overview,
outcomes, assignments grouped by work state, workers involved, recent
activity, linked proposals, linked incidents, related traces, outcome, and
risk.

Mission detail also shows approved mission-scoped workforce memory. Mission
memory is governed shared context, not autonomous progress inference or
project-management state.

Mission nodes are available in Operations, Research, and Incident Response
canvas presets. Mission relationships connect to workers, rooms, incidents, and
proposals, outcomes, and assignments only when daemon relationship records
support the link.

## Non-Goals

Mission Control does not add:

- scheduling
- kanban boards
- gantt charts
- epics
- sprints
- due dates
- estimates
- workload-specific entities
- AI-generated progress summaries
