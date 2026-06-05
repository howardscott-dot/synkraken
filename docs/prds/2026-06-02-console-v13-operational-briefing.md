# SynKraken Console v1.3 Operational Briefing

## Objective

Create a top-level Operational Briefing that helps the operator understand the
state of the work in under 30 seconds: what is active, blocked, changed,
requires attention, and what should be reviewed next.

## Scope

- Add Briefing navigation directly beneath Canvas.
- Build deterministic snapshots for workforce, missions, outcomes,
  assignments, recent activity, and operator review.
- Add recommended next actions from local rules only, capped at five actions.
- Add mission, outcome, and assignment health labels derived from existing
  daemon records.
- Add a Briefing canvas node to the Operations preset.

## Non-Goals

- No workflow engine.
- No autonomous planning.
- No project-management semantics.
- No AI summarisation.
- No daemon, storage, entity, or API changes.

## Deterministic Rules

- Mission health is Healthy, Watching, or At Risk based on status, linked
  assignments, blocked assignments, incidents, and inactivity.
- Outcome health is On Track, Watching, or Blocked based on status,
  confidence, linked assignments, and incidents.
- Assignment health is Assigned, In Progress, Waiting, or Blocked based on the
  daemon assignment status.
- Recommended next actions prioritize proposal approvals, blocked assignments,
  ownership gaps, stale waiting assignments, blocked outcomes, at-risk
  missions, and incidents.
