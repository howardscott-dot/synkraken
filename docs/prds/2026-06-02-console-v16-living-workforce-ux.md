# SynKraken Console v1.6 Living Workforce UX

## Objective

Make SynKraken feel like managing a living AI workforce rather than operating
an administrative monitoring console.

## Product Principle

Conversation first. Work second. Governance third. Diagnostics last.

The Console should open into a workplace populated by conversations, workers,
knowledge, work, and decisions. It should not lead with read models, raw
tables, telemetry, or canvas inspection.

## Information Architecture

Primary navigation:

- Home
- Conversations
- Work
- Knowledge
- Workforce
- Governance
- Search

Contextual or advanced surfaces:

- Activity
- Incidents
- Canvas
- Settings
- Flight Recorder
- Proposal detail

Canvas remains advanced inspection only and is not a primary workflow.

## Screen Changes

Home becomes a deterministic chief-of-staff briefing answering:

- What happened?
- What needs me?
- What should I do next?

Conversations replaces Rooms in the primary model. The transcript owns the
screen. Room list is secondary. Members, knowledge, assignments, delivery
results, proposals, handoffs, and diagnostics move behind drawers.

Work uses educational empty states. Empty missions, outcomes, and assignments
explain what to create next instead of rendering giant empty grids.

Knowledge replaces Memory as the operator-facing concept. Knowledge groups are
Company, Projects, People, Technical, Lessons Learned, and Pending Review.
Filters and archived records are secondary.

Workforce becomes worker cards. Each worker card answers whether the worker can
be used, what they are doing, what to watch, and what action is recommended.
Raw health and trust are collapsed.

Governance becomes an inbox with Awaiting Review, Recent Decisions, Recent
Handoffs, and Executed Actions.

Activity becomes a timeline-first surface. Tables and filters are secondary.

Search introduces one Spotlight-style result surface over workers,
conversations, missions, outcomes, assignments, knowledge, incidents, traces,
and governance records.

## Out Of Scope

- Daemon behavior changes
- Storage changes
- New backend APIs
- AI-written summaries
- Automatic planning or scheduling
- Canvas workflow expansion

## Acceptance Criteria

A first-time operator can understand in under five seconds:

- what happened
- what matters
- what to do next
- where to talk to the workforce
- where work lives
- what the workforce knows
- what needs judgement
- where to search across SynKraken

## Validation

- Console production build
- v1.6 source-level smoke test
- context audit
- Python compile
- diff whitespace check
