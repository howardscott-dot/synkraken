# Workforce Model

## Purpose

SynKraken treats multiple AI runtimes as an operator-visible workforce. The
workforce model is about coordination and governance, not anthropomorphic
identity or hidden autonomy.

## Core Objects

- agents: durable operational entities backed by configured runtimes
- rooms: persistent groups where work is visible and replayable
- roles: task-scoped responsibilities assigned for coordination
- tasks: durable work records linked to rooms, agents, and source messages
- runs: durable team or goal executions with audit events
- memory: bounded, inspectable room or shared context
- events: append-only evidence of state changes and decisions

## Bounded Workflows

Discussion Mode, Team Task Mode, and Goal Mode are explicit operator-started
workflows. They must remain bounded by turns, rounds, thresholds, context
budgets, visible transcripts, and failure states.

They are not background workforce autonomy.

## Control Roles

The shipped workforce role vocabulary is:

- `owner`
- `reviewer`
- `guardrail`
- `token_police`
- `coordinator`
- `specialist`

Roles describe responsibilities inside a run. They are not personal identity,
provider identity, or a security boundary.

## Coordination Rule

SynKraken may select, assign, and display roles to coordinate work, but it must
record enough context for operators to inspect who did what, why a run stopped,
and what remains blocked or done.
