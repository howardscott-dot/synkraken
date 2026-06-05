# Spatial Canvas Model

SynKraken is moving from screens to spaces.

The Spatial Operations Canvas exists because AI workforce objects are connected
operationally. A failing runtime may produce a dead letter. A dead letter may
anchor an incident. A proposal may link to a room, trace, decision, handoff, or
runtime. A room may contain the context needed to understand all of it.

## Canvas Philosophy

The canvas is an operator workspace, not a decorative dashboard. It should
make operational relationships easier to inspect without inventing telemetry
or moving business logic into the client.

Truth comes from the daemon. Layout is local UI state.

## Node Types

Current node types:

- Workforce Summary
- Runtime
- Room
- Mission
- Outcome
- Proposal Queue
- Proposal Detail
- Incident
- Trace
- Dead Letter

Future nodes may cover memory, decisions, handoffs, tasks, goals, and recovery
queues when the daemon exposes the right detail contracts.

## Relationship Lines

Relationship lines represent links returned by daemon relationship records
where available. Missing relationships are omitted. The client should not fake
graph edges to make the canvas look busy.

Relationship evidence should identify the persisted record or read model that
supports the link.

## Workspace Presets

Presets give operators a useful starting layout:

- Coding
- Operations
- Research
- Incident Response

Presets are deterministic local layouts. They do not alter daemon state.

## Persistence Model

Canvas layout is local UI state persisted in browser localStorage. It includes
node positions, selected workspace, and transform state. Polling must not
overwrite local layout. Daemon-owned business state stays in SQLite.

## Operator Workflows

The canvas supports:

- inspect workforce health
- arrange key runtime and room nodes
- inspect mission governance context
- inspect outcome progress and blocked value
- focus a proposal, trace, room, runtime, incident, or dead letter
- jump through relationships
- open detail screens for full workflows
- keep incident context visible while reviewing proposals or traces

## Difference From An IDE

The canvas is not a code editor. It is not trying to replace IDE agent panels.
It shows workforce operations: who is working, what failed, what requires
approval, and how objects relate.

## Difference From A Dashboard

A dashboard reports metrics in fixed panels. A canvas lets the operator place
objects spatially and build a working map of the current operational problem.

## Future Direction

Future canvas work should add richer relationship coverage, more durable
object detail, better focus and history, recovery-oriented nodes, and optional
layout assistance. Daemon-owned graph facts should remain separate from
client-owned layout.
