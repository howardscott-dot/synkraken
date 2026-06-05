# v1.0 Outcome Governance PRD

## Purpose

Introduce Outcome as the primary success object in SynKraken.

Workers perform activity. Missions organise work. Outcomes measure progress and
value. The operator should be able to answer:

- What are workers doing?
- What missions exist?
- What outcomes are progressing?
- What outcomes are blocked?
- Which outcome needs my approval?

## Product Direction

SynKraken is an AI Workforce Operating System. It governs workers, activity,
decisions, approvals, incidents, traces, memory, missions, outcomes, and
evidence.

Outcome Governance must not become project management software. It must not add
tasks, tickets, kanban boards, schedules, due dates, gantt charts, sprints, or
estimates.

## Outcome Definition

An outcome is a desired result linked to a mission.

Examples:

- Research Completed
- Architecture Reviewed
- Recommendation Produced
- Decision Approved
- Mission Model Implemented
- Outcome Model Implemented
- Operator Testing Completed
- Release Approved

## Scope

Backend:

- Add deterministic SQLite outcome tables.
- Link outcomes to missions, workers, traces, incidents, proposals, and
  relationships.
- Add outcome read models.
- Derive mission progress from linked outcomes.
- Add outcome-aware activity tagging and filtering.
- Add outcome context to workforce presence and rooms.
- Add outcome canvas relationships.

API:

- `GET /v1/outcomes`
- `GET /v1/outcomes/summary`
- `GET /v1/outcomes/{id}`
- `GET /v1/missions/{id}/outcomes`
- `GET /v1/outcomes/{id}/activity`
- `GET /v1/outcomes/{id}/workers`
- `GET /v1/outcomes/{id}/proposals`
- `GET /v1/outcomes/{id}/incidents`

Console:

- Add Outcomes navigation below Missions.
- Add Outcome Centre with summary and outcome table.
- Add Outcome detail cockpit.
- Add Outcomes section and progress calculation to Mission detail.
- Add Outcome canvas node type.
- Add outcome filter to Activity.
- Show Current Outcome in Workforce.
- Show Current Outcome in Rooms.
- Show Affected Outcome in Incidents.

Docs:

- Add Outcome Model documentation.
- Update README, product doctrine, core concepts, operator guide, console
  doctrine, mission model, and changelog.

## Acceptance Criteria

- Outcome storage read model smoke test passes.
- Outcome API smoke test passes.
- Console source includes Outcome Centre, Outcome detail, Outcome node, and
  outcome filter wiring.
- Mission progress derives from completed outcomes over total outcomes.
- Activity records can be filtered by outcome.
- Canvas relationship records include Mission to Outcome and Outcome to Worker,
  Proposal, Incident, and Trace links.
- Build, compileall, context audit, and diff check pass.

## Non-Goals

- No write API endpoints.
- No scheduling.
- No project plans.
- No kanban.
- No tickets.
- No gantt charts.
- No AI-generated progress summaries.

## Verification

- `python3 scripts/console_v10_outcome_governance_smoke_test.py`
- `npm run build` from `apps/console`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`
- `git diff --check`
