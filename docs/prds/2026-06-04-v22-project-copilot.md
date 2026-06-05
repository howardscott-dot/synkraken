# SynKraken v2.2 Project Co-Pilot

## Product Decision

Projects become helpful operating assistants.

They are not AI assistants, autonomous planners, or new entities. They are
deterministic project assistants that use existing SynKraken records to tell
the operator what happened, what needs attention, and what to do next.

## Problem

Projects now feel like workspaces, but the operator still has to inspect
several tabs to understand current project state. Deliverables, decisions,
activity, knowledge, assignments, and handoffs are visible, but not yet
combined into one useful project read.

## Objective

When the operator opens a project, they should immediately understand:

- what happened
- what needs him
- what he should do next

without opening multiple tabs.

## Scope

In scope:

- Project Co-Pilot section at the top of Overview
- deterministic project health
- priority-ordered recommended next actions
- action cards with title, why, suggested action, and open action
- project Inbox aggregating activity, deliverables, decisions, knowledge, and
  handoffs
- deliverable cards with open action clarity
- team cards with contribution, last activity, and suggested use
- Home project-centric recommendations
- source-level smoke test

Out of scope:

- new backend entities
- new navigation
- new dashboards
- AI generation or LLM calls
- governance redesign
- workforce redesign

## Health Model

Project health is deterministic and display-only.

States:

- Healthy
- Watching
- Needs Review
- Blocked
- Quiet

Rules:

- Blocked: high-risk pending decision, blocked assignment, or blocked outcome.
- Needs Review: pending proposal or deliverable awaiting review.
- Watching: no meaningful project activity for three or more days.
- Quiet: little project activity or produced work has been recorded yet.
- Healthy: recent project activity exists and no blocker or review item is
  waiting.

The UI must not expose scores or internal calculations.

## Recommendation Rules

Recommended next actions are deterministic and capped at five.

Sources:

- pending proposals
- blocked assignments
- deliverables awaiting review
- handoffs not acknowledged
- outcomes with no active assignment
- missing project knowledge
- stale project activity

Each action shows:

- title
- why it matters
- suggested action
- open action

## Inbox Design

Project Inbox is a single project event stream, newest first.

It aggregates:

- human-readable project activity
- deliverables created or needing review
- knowledge updates
- handoffs
- proposal/decision-related deliverables

The operator should not have to visit Deliverables, Decisions, Activity, or
Governance just to understand current project state.

## Home Integration

Home uses project recommendations first.

The primary recommended action should prefer the highest-priority project
recommendation. Project cards show project health, current focus, and the next
project action.

## Acceptance Criteria

- Project Co-Pilot appears at the top of Overview.
- Project health is deterministic and plain-language.
- Recommended next actions are priority ordered and capped at five.
- Project Inbox aggregates human-readable project events.
- Deliverables show status, owner, last updated, and open action.
- Team shows contribution context, last activity, and suggested use.
- Home foregrounds project recommendations.
- No AI generation or new entity is required.

## Validation Plan

- `npm run build`
- `python3 scripts/console_v22_project_copilot_smoke_test.py`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`
- `git diff --check`
