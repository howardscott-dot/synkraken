# Console v0.9 Mission Control PRD

## Purpose

Introduce Mission as the primary organisational object in SynKraken so the
operator can answer:

- What is my workforce doing?
- Which missions are progressing?

Mission Control must strengthen SynKraken as an AI Workforce Operating System,
not turn Console into a project management tool.

## Product Direction

SynKraken is not a Studio Blueprint frontend, Jira, Trello, Asana, kanban
board, or task manager. Studio Blueprint is only one possible workload on top
of SynKraken.

SynKraken governs workers, activity, decisions, approvals, incidents, traces,
memory, and outcomes for consulting firms, software companies, ecommerce
businesses, agencies, research teams, and operations teams.

## Mission Definition

A mission is a governance container around meaningful work. Examples:

- Review competitor landscape
- Create investor deck
- Diagnose client maturity
- Design onboarding workflow
- Build release v0.9
- Research MCP governance patterns

Mission is not a task, project, ticket, schedule, or plan.

## Scope

Backend:

- Add deterministic mission storage tables and read models.
- Support links to workers, rooms, traces, incidents, proposals, and
  relationships.
- Add mission summary, mission activity, mission workers, mission proposals,
  and mission incidents read methods.
- Add mission-aware activity filtering.
- Add mission relationships to canvas relationship records.

API:

- `GET /v1/missions`
- `GET /v1/missions/{id}`
- `GET /v1/missions/summary`
- `GET /v1/missions/{id}/activity`
- `GET /v1/missions/{id}/workers`
- `GET /v1/missions/{id}/incidents`
- `GET /v1/missions/{id}/proposals`

Console:

- Add Missions navigation directly beneath Canvas.
- Add Mission Centre with Mission Summary and mission table.
- Add Mission Detail governance cockpit.
- Add Mission node type to Operations, Research, and Incident Response canvas
  presets.
- Add mission filtering to Activity.
- Show mission association in Rooms, Workforce, and Incidents when available.

Docs:

- Update README, doctrine, console doctrine, core concepts, operator guide,
  changelog.
- Add Mission Model documentation.

## Non-Goals

- No write endpoints.
- No scheduling.
- No gantt charts.
- No kanban boards.
- No project, ticket, epic, sprint, due date, or estimate model.
- No Studio Blueprint-specific entities.
- No AI-generated mission progress summaries.

## Acceptance Criteria

- Mission storage read models exist and are covered by smoke tests.
- Mission API route contracts exist.
- Console has a Missions nav item below Canvas.
- Mission Centre renders active, blocked, review, and completed mission counts.
- Mission table renders Mission, Status, Priority, Workers, Recent Activity,
  Open Proposals, Incidents, and Last Updated.
- Selecting a mission shows Mission Overview, Workers Involved, Recent
  Activity, Linked Proposals, Linked Incidents, Related Traces, Outcome, and
  Risk.
- Mission nodes can be added and are present in Operations, Research, and
  Incident Response presets.
- Activity can filter by one mission or all active missions.
- Rooms, Workforce, and Incidents display mission context when daemon records
  provide it.
- Build, compileall, context audit, and mission smoke tests pass.

## Implementation Notes

SQLite remains the source of truth. Mission tables are additive and local-first.
Console uses daemon APIs and does not read SQLite or infer production
relationships in the client.

The implementation deliberately avoids write endpoints in v0.9. Fixtures and
future workflows may create mission records through storage, but operator
creation and mutation flows are out of scope for this read-model-first release.

## Verification

- `python3 scripts/console_v09_mission_control_smoke_test.py`
- `npm run build` from `apps/console`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`
