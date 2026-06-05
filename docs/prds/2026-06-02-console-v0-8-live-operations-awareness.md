# Console v0.8 Live Operations Awareness

## Objective

Operators must be able to understand what is happening right now without
opening traces, incidents, rooms, or proposals.

## Doctrine

This release is deterministic, local-first, operator-led, and
governance-first. It does not add autonomy, scheduling, execution, planning
agents, or AI-generated summaries.

## Scope

- Add daemon-backed `GET /v1/activity/live`.
- Add Console Activity screen.
- Add Workforce live context columns.
- Add Rooms live context.
- Add subtle Canvas presence indicators.
- Add top-level Activity summary.
- Add smoke coverage, README updates, operator guide updates, UI doctrine
  updates, and screenshot inventory updates.

## Rationale

SynKraken already records enough durable evidence to describe current
operations: messages, deliveries, proposal events, handoffs, decisions, room
transcripts, and dead letters. A read model over those records gives operators
live awareness without creating a second source of truth or adding autonomous
behavior.

## Screenshots

The canonical screenshot inventory includes `docs/screenshots/activity.png`.
The asset is marked missing until captured from a generic demo-safe daemon
state. Capture guidance remains in `scripts/capture_console_screenshots.md`.
