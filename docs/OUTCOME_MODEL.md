# Outcome Model

Outcome is the primary success object for SynKraken v1.0 Outcome Governance.

Workers perform activity. Missions organise work. Outcomes measure whether the
work achieved the desired result. Operators should care more about whether an
outcome was achieved than whether a worker sent messages.

An outcome is a desired result linked to a mission. It is not a task, ticket,
schedule item, kanban card, gantt milestone, or project-management entity.

## Fields

The deterministic outcome record contains:

- `outcome_id`
- `mission_id`
- `title`
- `description`
- `status`
- `confidence`
- `owner`
- `created_at`
- `updated_at`
- `completed_at`

Optional derived counts:

- `evidence_count`
- `proposal_count`
- `incident_count`

Valid statuses are:

- `not_started`
- `in_progress`
- `review`
- `completed`
- `blocked`
- `cancelled`

Valid confidence values are:

- `low`
- `medium`
- `high`

## Links

Outcomes support durable links to:

- missions
- assignments
- workers
- traces
- incidents
- proposals
- relationships

These links make outcome progress inspectable without AI-generated summaries or
client-side inference.

## Read Models

The storage layer exposes:

- `list_outcomes()`
- `get_outcome()`
- `list_mission_outcomes()`
- `outcome_summary()`
- `outcome_activity()`
- `outcome_workers()`
- `outcome_proposals()`
- `outcome_incidents()`
- `outcome_assignments()`

Mission progress is derived from linked outcomes:

```text
completed outcomes / total outcomes
```

For example, `2 / 5 outcomes completed` means 40 percent mission progress.

## API

The daemon exposes read endpoints:

- `GET /v1/outcomes`
- `GET /v1/outcomes/summary`
- `GET /v1/outcomes/{id}`
- `GET /v1/missions/{id}/outcomes`
- `GET /v1/outcomes/{id}/activity`
- `GET /v1/outcomes/{id}/workers`
- `GET /v1/outcomes/{id}/proposals`
- `GET /v1/outcomes/{id}/incidents`
- `GET /v1/outcomes/{id}/assignments`

Activity supports outcome-aware filtering through `/v1/activity/live`:

- `outcome=<outcome_id>`

## Console

Outcome Centre shows outcome summary counts, an outcome table, and a selected
outcome cockpit with overview, mission context, workers contributing, recent
activity, assignments contributing to the outcome, evidence, linked proposals,
linked incidents, decision history, confidence, and status.

Outcome detail also shows approved outcome-scoped workforce memory. Outcome
memory is visible context for workers and operators; it does not replace
evidence, confidence, or deterministic outcome status.

Outcome nodes are available in Operations, Research, and Incident Response
canvas presets. Outcome relationships connect to missions, workers, proposals,
incidents, traces, and assignments only where daemon records support the link.

## Non-Goals

Outcome Governance does not add:

- tasks
- tickets
- schedules
- kanban boards
- gantt charts
- due dates
- estimates
- autonomous progress inference
- AI-generated status summaries
