# Workforce Model

## Purpose

SynKraken treats multiple AI runtimes as an operator-visible workforce. The
workforce model is about coordination and governance, not anthropomorphic
identity or hidden autonomy.

## Core Objects

- agents: durable operational entities backed by configured runtimes
- runtime registry: discovered local runtime inventory with command,
  capability, cost tier, adapter type, and supported mode metadata
- rooms: persistent groups where work is visible and replayable
- roles: task-scoped responsibilities assigned for coordination
- tasks: durable work records linked to rooms, agents, and source messages
- runs: durable team or goal executions with audit events
- memory: bounded, inspectable room or shared context
- decisions: durable choices with proposer, approval or rejection actor,
  rationale, confidence when known, and links to related messages or runtimes
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

## Decision Records

Decision Records v0.1 preserve explicit workforce choices. They record what
was decided, who proposed it, who approved or rejected it, why, confidence when
known, and which messages or runtimes the decision relates to.

Decision Records are audit and memory infrastructure. They are not voting,
handoffs, policy enforcement, autonomous planning, or background execution.

## Runtime Onboarding

`synkraken discover` and `synkraken config --rediscover` onboard workers by
detecting local runtimes and asking the operator what to merge. Existing
adapter definitions are preserved by default. Unsupported runtimes can be
tracked in the registry, but they are not treated as active agents until an
adapter exists and the operator enables them. Once a leaf adapter is registered
and configured (e.g. Goose, Hermes, OpenClaw, Claude Code, Crush,
Google Antigravity), the runtime becomes a supported, active worker.
