# Workforce Model

## Purpose

SynKraken treats multiple AI runtimes as an operator-visible workforce inside
an open-source AI Workforce Operating System. The workforce model is about
coordination, governance, reliability, and recovery, not anthropomorphic
identity or hidden autonomy.

## Core Objects

- agents: durable operational entities backed by configured runtimes
- runtime reputation: deterministic operational quality history for each
  runtime, derived from deliveries and weak-output classifications
- runtime registry: discovered local runtime inventory with command,
  capability, cost tier, adapter type, and supported mode metadata
- rooms: persistent groups where work is visible and replayable
- roles: task-scoped responsibilities assigned for coordination
- tasks: durable work records linked to rooms, agents, and source messages
- runs: durable team or goal executions with audit events
- memory: bounded, inspectable room or shared context
- decisions: durable choices with proposer, approval or rejection actor,
  rationale, confidence when known, and links to related messages or runtimes
- proposals: durable execution-authority requests with proposer, risk,
  approval requirement, approval/rejection/execution actors, execution payload,
  and links to rooms, tasks, goals, decisions, handoffs, or messages
- handoffs: durable transfers with sender, receiver, context, risks, next step,
  confidence when known, status, and links to rooms, tasks, goals, messages, or
  decisions
- events: append-only evidence of state changes and decisions
- flight records: read-only reconstructions of work assembled from existing
  messages, deliveries, failures, decisions, handoffs, task events, and goal
  events
- canvas nodes and relationships: spatial Console representations of
  daemon-owned workforce objects and evidence-backed links

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

## Operator Surface Rule

No operator surface may assume a fixed workforce. The daemon's configured and
enabled agents are the workforce source of truth, and TUI/Web surfaces must
render arbitrary adapter ids with fallback presentation when no runtime-specific
styling exists.

Weak runtime output is still workforce state. Empty replies, suspicious output,
unexpected output, wrong identity markers, timeouts, and failed deliveries must
remain visible in delivery results, transcripts, and health-oriented views
rather than being filtered out because the reply is poor.

SynKraken does not assume all AI workers are equally reliable. The control
plane continuously evaluates workforce operational quality using deterministic
runtime reputation and health signals. Reputation is not AI scoring, model
judgment, embeddings, or probabilistic ranking; it is a compact read model over
observable delivery outcomes.

Runtime health statuses are operational hints:

- `healthy`: high trust and no repeated weak recent behavior
- `degraded`: usable but showing empty replies, lower trust, or weak output
- `unstable`: repeated recent failures, timeouts, or low trust
- `failing`: severe trust loss or repeated recent hard failures

Health can bias bounded team and goal selection, but it must not silently
disable workers, mutate config, or hide a runtime from operator surfaces.

## Decision Records

Decision Records v0.1 preserve explicit workforce choices. They record what
was decided, who proposed it, who approved or rejected it, why, confidence when
known, and which messages or runtimes the decision relates to.

Decision Records are audit and memory infrastructure. They are not voting,
handoffs, policy enforcement, autonomous planning, or background execution.

## Proposals And Execution Governance

Approval & Execution Governance v0.1 adds proposals as the authority boundary
between workers and execution. Workers may propose actions, but they do not
gain freedom to execute sensitive actions.

Proposal records preserve:

- what action was proposed
- who proposed it
- deterministic risk classification
- whether approval is required
- why approval is required
- who approved, rejected, cancelled, or executed it
- linked rooms, tasks, goals, decisions, handoffs, and messages
- append-only proposal events

The governance flow is:

```text
proposed -> approved -> executed
proposed -> rejected
proposed -> cancelled
```

Execution is operator-controlled. In v0.1 SynKraken records simulated execution
only; it does not run real shell commands, git pushes, daemon restarts, file
writes, deletes, replay actions, or retry actions from proposals.

Proposal behavior contributes simple deterministic counters to runtime
reputation, such as proposals created, rejected, cancelled, and executed. This
is not AI quality scoring and does not silently disable workers.

## Handoffs

Handoffs v0.1 preserve explicit workforce transfers. They record what work was
handed off, who handed it off, who received it, what context, risks, open
questions, and next steps were attached, confidence when known, and whether the
receiving worker accepted, rejected, or completed it.

Handoffs are coordination and recovery infrastructure. They are not approval
chains, voting, policy enforcement, autonomous planning, scheduling, or
background execution.

## Flight Recorder

Flight Recorder v0.1 lets an operator reconstruct what happened during AI
work. It answers what happened, which runtimes were involved, what messages
were sent, what failed, what decisions and handoffs occurred, and what outcome
SynKraken can infer from the persisted record.

Flight records are read models over existing data. They are not a policy
engine, approval chain, cost dashboard, reputation system, auto-detection
system, or new orchestration layer.

## Runtime Onboarding

`synkraken discover` and `synkraken config --rediscover` onboard workers by
detecting local runtimes and asking the operator what to merge. Existing
adapter definitions are preserved by default. Unsupported runtimes can be
tracked in the registry, but they are not treated as active agents until an
adapter exists and the operator enables them. Once a leaf adapter is registered
and configured (e.g. Goose, Hermes, OpenClaw, Claude Code, Crush,
Google Antigravity), the runtime becomes a supported, active worker.

## Canonical Vocabulary

Canonical product vocabulary is maintained in
[`CORE_CONCEPTS.md`](CORE_CONCEPTS.md). Workforce documentation should reuse
those terms rather than introducing parallel names for workers, rooms,
proposals, traces, incidents, relationships, or canvas nodes.
