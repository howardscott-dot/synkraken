# Core Concepts

This is the canonical vocabulary for SynKraken.

## Operator

The human responsible for directing work, approving authority, reviewing
failures, and deciding which runtimes participate.

## Runtime

An external AI tool or model interface that SynKraken can discover or invoke,
such as Claude Code, Goose, Hermes, OpenClaw, Crush, or Google Antigravity.

## Worker

An enabled runtime represented as an operational participant in SynKraken.
Workers receive messages, participate in rooms, produce replies, propose
actions, and accumulate reputation.

## Presence

A deterministic read model that describes what a worker appears to be doing
from persisted daemon records. Presence is not scheduling, hidden reasoning, or
cross-machine liveness. It combines recent deliveries, messages, room
membership, proposals, handoffs, decisions, dead letters, reputation, and raw
health.

## Active Worker

A worker with recent useful activity, such as a successful delivery, message,
proposal, handoff, or room contribution.

## Idle Worker

A worker that is enabled and healthy enough to use, but has no recent activity.

## Needs Attention

An operator-facing state for a worker or incident that should be reviewed
before relying on it. Causes include empty replies, identity mismatch, timeout,
delivery failure, low trust, or degraded raw health. It is not automatically a
critical incident.

## Activity Feed

A compact chronological read model of meaningful recent activity, such as
messages, deliveries, proposals, approvals, handoffs, decisions, incidents, and
dead letters.

## Adapter

A small SynKraken integration module that invokes one runtime through its
native command or protocol and normalizes the result into daemon records.

## Room

A persistent named workspace with members, transcript, room memory, messages,
and room-scoped work.

## Mission

The primary organisational object in SynKraken. A mission is a governance
container around meaningful work and outcomes. It can link workers, rooms,
traces, incidents, proposals, relationships, outcomes, and risk. It is not a
task, project, ticket, schedule, kanban board, or workload-specific entity.

## Outcome

The primary success object in SynKraken. An outcome is a desired result linked
to a mission. Outcomes measure progress and value through deterministic status,
confidence, evidence, proposal, incident, worker, and trace links. Outcomes are
not tasks, tickets, schedules, kanban cards, or AI-generated progress claims.

## Assignment

Work currently owned by one worker. An assignment can link to a mission,
outcome, and room, and can list many contributor workers. It exposes ownership,
status, blockers, review, completion, activity, proposals, traces, and
handoffs. It is not a task manager item, ticket, schedule, board card, or
project plan.

## Goal

A bounded room workflow with success criteria, owner, reviewers, control
roles, rounds, threshold, score, status, and audit events.

## Task

A durable unit of work. Tasks may link to rooms, workers, source messages,
team runs, or goal runs.

## Decision

A durable record of what was decided, who proposed it, who approved or rejected
it, why, and which messages or runtimes it relates to.

## Handoff

A durable transfer of work from one worker to another, including context,
risks, open questions, recommended next step, status, and audit events. When
linked to an assignment, a handoff shows which worker owned work, who received
it, why, and what context moved.

## Proposal

A request by a worker or operator for execution authority. Proposals carry
type, risk, approval requirement, payload, status, actors, links, and events.

## Approval

An explicit operator or governance action that permits a proposal or governed
run to proceed. Approval is recorded as an audit event.

## Execution

The action taken after approval. In proposal governance v0.1, sensitive
execution is simulated and recorded; SynKraken does not grant autonomous shell,
git, file, restart, replay, retry, or delete authority to workers.

## Trace

An operational reconstruction for an id. A trace surfaces messages,
deliveries, dead letters, proposals, decisions, handoffs, tasks, goals, memory
markers, and related failures.

## Replay

A timeline-oriented read model that helps the operator replay what happened in
a conversation, task, goal, decision, handoff, proposal, or incident context.

## Flight Recorder

The inspection capability that reconstructs AI work from persisted records.
It is a read model, not a workflow engine.

## Incident

An operator-visible failure context, typically anchored on a failed delivery,
dead letter, failing runtime, or related trace.

## Dead Letter

A durable failed delivery record that could not complete successfully. Dead
letters preserve reason, target/runtime, payload context, and replay/recovery
path.

## Memory

Durable context available to SynKraken workflows. Room memory is room-scoped.
Shared memory is peer-reviewed, bounded, inspectable workspace knowledge.

Shared Workforce Memory is the v1.4 governed memory layer. It stores visible
operator notes, room summaries, decision memory, handoff memory, mission
context, outcome context, assignment context, and runtime observations. Only
approved memory is active by default; proposed, rejected, and archived records
remain inspectable for audit.

## Runtime Reputation

A deterministic read model over delivery and proposal history for a runtime.
It tracks success, failure, timeouts, empty replies, wrong identity markers,
suspicious output, proposal outcomes, duration, trust, and health.

## Trust Score

A compact numerical signal derived from observed runtime behavior. It is not
AI scoring or hidden ranking.

## Health Status

An operational category for a worker: `healthy`, `degraded`, `unstable`, or
`failing`.

## Governance Event

An append-only record of a state transition or authority action in proposals,
team runs, goal runs, decisions, handoffs, tasks, agents, or memory.

## Canvas Node

A spatial Console representation of a daemon object, such as a runtime, room,
mission, outcome, assignment, proposal, trace, incident, or dead letter.

## Relationship

A daemon-backed or evidence-backed link between two operational objects, such
as a proposal created by a runtime, a dead letter tied to a trace, or a room
containing proposals.

## Spatial Operations Canvas

The Console workspace where operators arrange connected AI workforce objects
as nodes and relationship lines.
