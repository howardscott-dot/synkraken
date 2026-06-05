# SynKraken Console v1.2 Operator UX Sweep

## Objective

Make the Console calmer, cleaner, and easier for a human operator to use
without changing daemon behavior, storage, entities, or APIs.

## Scope

- Reduce visual noise and overuse of cyan.
- Make actions read as actions with primary, secondary, disabled, and dangerous
  treatments.
- Replace raw workforce alarm language with operator categories: Available,
  Monitor, Avoid for now, and Unavailable.
- Convert Rooms into a fixed-height messaging workspace with independent
  scrolling for room list, transcript, member list, and side context.
- Keep the room composer visible and paste-safe.
- Render delivery summaries and compact rows by default, with raw details
  collapsed.
- Preserve raw health, trust, and delivery evidence in compact details.

## Non-Goals

- No daemon behavior changes.
- No storage changes.
- No new entities.
- No new APIs.
- No removal of existing room, workforce, canvas, incident, assignment,
  mission, outcome, proposal, or trace functionality.

## Acceptance Checks

- Rooms use a three-column fixed-height layout.
- Transcript and member list scroll independently.
- Composer stays visible and supports Ctrl+Enter or Cmd+Enter.
- Delivery results summarize targets, replies, empty replies, and failures.
- Workforce rows explain usability, issue, impact, and recommended action.
- Red remains reserved for daemon offline, critical/blocking failure, and
  dangerous actions.
- Source smoke test, console build, context audit, compileall, and diff check
  pass.
