# Agent Model Doctrine

## Purpose

This document defines what an **agent** means inside SynKraken before the
project adds richer presence, memory, handoffs, decisions, permissions, or
Studio:Blueprint agent teams.

The doctrine is intentionally ahead of implementation. It exists so later work
extends one model instead of inventing several incompatible ones.

## 1. What is an agent?

Inside SynKraken, an agent is a **durable operational entity** that can
participate in work, even when it originally enters the system through config.

These related ideas must stay distinct:

| Concept | Meaning |
|---|---|
| Configured adapter | A config entry that tells SynKraken how to invoke a runtime |
| Durable agent entity | The persistent SynKraken record representing an operational agent |
| Runtime process | The currently running external CLI or agent process, if any |
| Message participant | A source or target that appears in message traffic |
| Task assignee | The agent currently responsible for a visible task |

A configured adapter may bootstrap an agent, but it is not the whole agent
model. A runtime process may disappear and later return while the durable agent
record remains meaningful. A message participant may be an operator label
rather than a durable agent. A task assignee should be a durable agent because
assignment needs inspectability and referential integrity.

**Doctrine decision:** SynKraken now treats agents as durable operational
entities, even when they originate from config.

## 2. Agent identity

Recommended agent fields:

| Field | Meaning | v0.15 / v0.2 reality |
|---|---|---|
| `agent_id` | Stable internal identifier | implemented today as `adapter_id` |
| `display_name` | Human-facing name | implemented today as `runtime_name` |
| `adapter_type` | Integration kind such as `goose` or `claude` | implemented |
| `runtime` | Runtime family or implementation details | implemented |
| `role` | Semantic working role | future |
| `capabilities` | Declared strengths for routing and display | future |
| `status` | Operational state | implemented |
| `created_at` | Durable creation time | future |
| `updated_at` | Last durable model update | future |
| `last_seen_at` | Last observed runtime activity | implemented |

Today, SynKraken stores enough agent data to support current operation and task
assignment integrity. The richer identity surface is the direction, not a claim
that all fields already exist.

## 3. Agent lifecycle

Recommended lifecycle states:

- `configured`
- `online`
- `idle`
- `working`
- `blocked`
- `offline`
- `disabled`

These states describe the model SynKraken should grow toward:

- `configured` — known from bootstrap/config
- `online` — reachable runtime is available
- `idle` — online but not actively working
- `working` — currently handling work
- `blocked` — unable to proceed
- `offline` — not currently reachable
- `disabled` — intentionally unavailable by operator choice
Agent Presence v0.1 implements the listed states except `registered` and
`removed`, which remain doctrine-level concepts rather than active status
values. Presence is durable operational state only. It must not be used as a
memory store, decision registry, autonomous workflow, scheduler, or hidden
chain-of-thought channel.

## 4. Agent relationships

```text
agent ─── messages
      ├── rooms
      ├── tasks
      ├── agent_events
      ├── task_events
      ├── room memory
      ├── team tasks
      ├── future decisions
      └── future handoffs
```

The agent model should make those relationships inspectable rather than hiding
them behind adapter configuration.

## 4.1 Agent presence events

Agent Presence v0.1 records append-only operational events:

- `status_changed`
- `task_assigned`
- `task_completed`
- `room_joined`
- `room_left`
- `message_sent`
- `message_received`
- `discussion_started`
- `discussion_completed`
- `timeout`

These events explain visible state transitions. They do not contain
chain-of-thought and do not grant agents authority to schedule or own work.

## 4.2 Room memory boundary

Room Memory v0.1 belongs to rooms, not agents. It stores room purpose,
objective, rules, constraints, current focus, and notes, plus append-only
change events. SynKraken may inject a concise room memory header into
room-scoped prompts so agents can work with the visible room context.

Room Memory is not agent memory, hidden chain-of-thought, RAG, embeddings,
semantic search, autonomous planning, decisions, scheduling, or cloud sync.

## 4.3 Team task boundary

Team Task Mode v0.1 lets a human explicitly ask a room to coordinate around one
question or task. Agents clarify, nominate an owner/reviewer, produce work, and
review it only inside the visible room transcript. SynKraken records a durable
task and visible events; it does not grant agents background authority.

Owner selection is deterministic: most nominations wins, then configured
role/capability matching when present, then room order. This is coordination
logic, not a hidden decision registry or autonomous planner.

## 5. Source of truth

Current reality:

- config-backed agents are the operational source today
- the SQLite `agents` table is the referential source for task assignment
- `AgentFabric` synchronizes configured adapters into the durable `agents` table

Doctrine decision for v0.1:

> **Config is the bootstrapping source. Durable agent records are the
> operational source once registered.**

This lets SynKraken remain local and config-friendly while giving future
presence, permissions, handoffs, and team features a durable entity to extend.

## 6. Agent authority model

Future permission modes:

- `read`
- `message`
- `propose`
- `execute`
- `administer`

These modes are directional guidance only. SynKraken does **not** yet have a
full permission system, and no current feature should pretend that it does.

## 7. Agent roles

Initial role examples:

- `builder`
- `reviewer`
- `researcher`
- `coordinator`
- `operator`
- `domain-specialist`

Roles should guide routing, display, and operator understanding. They are not a
security boundary.

## 8. Agent capabilities

Example capabilities:

- `code_editing`
- `shell_execution`
- `web_research`
- `repo_analysis`
- `document_review`
- `sb_methodology`
- `evidence_review`
- `roadmap_planning`

Capabilities should later support routing and operator decision-making. They
should not silently seize work from the human.

## 9. Product rules

Non-negotiable rules:

- Agents are inspectable.
- Agents do not silently own work.
- Human command remains primary.
- Tasks assigned to agents must remain visible.
- Agent actions should leave events.
- Local-first operation comes before cloud orchestration.
- Studio:Blueprint integration must use explicit permissions.

## 10. Implications for the next roadmap

The recommended sequence is:

1. Agent Model Doctrine v0.1
2. Agent Presence v0.1
3. Room Memory v0.1
4. Team Task Mode v0.1
5. Decisions v0.4
6. Handoffs v0.5
7. Workspace Packs v0.6
8. Studio:Blueprint Agent Teams v0.7

This sequence deliberately establishes identity before memory, decisions, and
team orchestration.
