# PRD: Console v1.5 Apple Operator Redesign

## Current UX Failures

The Console exposes useful daemon state but starts from implementation objects
instead of operator intent. The current experience feels like a database,
telemetry dashboard, and raw control panel because navigation is object-heavy,
tables dominate, panels have equal weight, copy exposes daemon terms, and
Canvas is the default even though it is an advanced spatial mode.

Operators should not need to know whether a record is a mission, outcome,
assignment, proposal, handoff, or trace before understanding what to do next.

## Design Principles

- Purpose first: answer the operator's next question before showing objects.
- Product and content are the hero: rooms, work, memory, approvals, and
  incidents lead; metadata follows.
- Less, but better: fewer borders, fewer equal-weight panels, quieter detail.
- Typography-led hierarchy with generous spacing.
- Native macOS feel using system fonts, dark surfaces, soft greys, and Apple
  blue for primary action.
- Amber only for genuine attention; red only for destructive/offline states.
- Raw technical detail remains available behind details, inspectors, drawers,
  or collapsed sections.
- Truth over polish still applies: failures stay visible, but calmly.

## Information Architecture

Old object-first IA:

- Canvas
- Briefing
- Missions
- Outcomes
- Assignments
- Activity
- Memory
- Workforce
- Rooms
- Trace
- Proposals
- Incidents

New operator-first IA:

- Home
- Rooms
- Work
- Memory
- Activity
- Workforce
- Governance
- Incidents
- Canvas
- Settings

## New App Structure

Home becomes the default. It combines operational briefing, recommended
actions, active work, recent rooms, pending approvals, and workers needing
attention.

Rooms becomes the primary operational workspace. It keeps a Slack/Apple
Messages-style three-column layout: rooms, conversation, room details. The
composer remains fixed and paste-safe.

Work combines Missions, Outcomes, and Assignments under a segmented control so
operators can review progressing work without thinking in backend entities
first.

Memory is renamed Workforce Memory. The primary action becomes Teach
Workforce. Memory is grouped by human meaning before filters.

Governance combines proposals, approvals, decisions, and handoffs into one
approval surface focused on "What needs approval?"

Canvas remains available as Advanced Canvas rather than the default.

Settings is a lightweight Console shell target for daemon/runtime/app
configuration context. It must not add new backend configuration APIs in this
sprint.

## Screens Affected

- App shell and navigation
- Home
- Rooms
- Work
- Workforce Memory
- Activity
- Workforce
- Governance
- Incidents
- Canvas
- Settings placeholder
- Global command palette copy
- Visual system in Console CSS

## Out Of Scope

- daemon behavior changes
- storage changes
- new backend entities
- new daemon APIs
- removal of existing capabilities
- AI summaries or autonomous planning
- full preferences editor
- RBAC, accounts, cloud sync, or external integrations

## Acceptance Criteria

- Console opens on Home.
- Navigation follows Home, Rooms, Work, Memory, Activity, Workforce,
  Governance, Incidents, Canvas, Settings.
- Home answers attention, workforce status, active work, rooms, approvals, and
  workers needing attention without raw tables.
- Rooms remains chat-first with independently scrolling room list,
  conversation, and details; composer stays fixed.
- Work combines Missions, Outcomes, and Assignments with segmented controls.
- Memory uses Workforce Memory and Teach Workforce language.
- Workforce reads as a worker directory with Available, Monitor, Avoid for now,
  and Unavailable categories.
- Governance exposes pending approvals and recent governance records together.
- Canvas is advanced/non-default.
- Styling uses Apple-style dark tokens, system fonts, blue primary actions,
  restrained amber/red, soft surfaces, larger radii, and fewer hard outlines.
- Raw JSON and technical records are not default presentation.

## Validation Plan

- `npm run build` from `apps/console`
- `python3 scripts/console_v15_apple_operator_redesign_smoke_test.py`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`
- `git diff --check`
