# Architecture

## Current system

SynKraken is a local message fabric with two operator surfaces:

```text
                         ┌────────────────────┐
                         │   TUI / Web GUI    │
                         └─────────┬──────────┘
                                   │ HTTP + SSE
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│ synkraken daemon                                              │
│ - HTTP API                                                    │
│ - AgentFabric dispatch                                        │
│ - retry / dead-letter handling                                │
│ - EventBus → SSE                                              │
│ - SQLite persistence                                          │
└───────────────┬──────────────────────────────────────────────┘
                │ subprocess per delivery
                ▼
      Claude Code / Goose / OpenClaw / Hermes / future agents
```

The daemon remains the source of truth. Client surfaces should render and
invoke backend concepts; they should not create parallel data models.

## Architectural decisions

| Decision | Rationale |
|---|---|
| One shared backend | avoids drift between TUI and Web GUI |
| Local HTTP + SSE | enough structure for multiple clients without heavy infra |
| SQLite persistence | durable, inspectable, zero-ops local storage |
| Leaf adapters | new runtimes should not destabilize the fabric |
| Separate web server | isolates browser concerns while preserving daemon APIs |

## Existing backend components

| Component | Responsibility |
|---|---|
| `api.py` | HTTP endpoints and SSE stream |
| `fabric.py` | message dispatch, retry loop, room reply recording, events |
| `router.py` | direct, broadcast, and room target resolution |
| `storage.py` | SQLite schema and queries |
| `models.py` | durable transport objects |
| `adapters/*` | leaf integrations for external runtimes |

## Existing first-class entities

### Agents

Durable operational entities bootstrapped from config-backed adapters. Current
records carry adapter identity, runtime type, durable presence, last-seen
metadata, current visible task/room links, and event history. Presence is
operational state only: it does not store chain-of-thought, memory, decisions,
or autonomous plans.

### Messages

Durable user or agent utterances with ids, source, target, conversation id,
reply linkage, priority, metadata, and hop count.

### Rooms

Persistent named groups of agents. A room target fans out to current members;
successful member replies are stored back into the same transcript.

### Room memory

Persistent, inspectable context attached to a room: purpose, objective, rules,
constraints, current focus, and notes. Room Memory is operational room context,
not agent memory, RAG, embeddings, semantic search, autonomous planning,
decisions, or cloud sync.

### Deliveries and dead letters

Operational records attached to messages. These preserve the distinction
between "what was asked" and "what happened when it was sent."

### Agent events

Append-only operational events attached to agents. These record visible
presence changes such as status transitions, room membership, message
send/receive, discussion start/completion, task assignment/completion, and
timeouts.

### Discussions

Bounded, daemon-orchestrated multi-agent exchanges started by a human. A
discussion is not an autonomous loop: SynKraken chooses the next speaker,
enforces `max_turns`, writes visible turn markers, and asks the final turn for
a recommendation.

### Team tasks

Human-commanded room orchestration that turns one room prompt into a bounded
team workflow. Team Task Mode runs only when explicitly invoked, writes every
phase to the room transcript, creates a durable task, and does not schedule or
continue work in the background.

### Team runs

Durable governance records for Team Task Mode. A team run stores room, source
prompt, participants, owner, reviewers, status, final report, approval mode,
approval actor, and timestamps. `team_events` records the audit trail for each
phase and approval decision.

## Entity relationships

```text
room ─────┬──── room_members ──── agent ─── agent_events
          │
          ├──── room_memory ───── memory_events
          │
          └──── messages ─────── deliveries
                              └─ dead_letters
          │
          └──── tasks ─────────── task_comments
                    ├──────────── optional assigned agent
                    └──────────── optional source message

team_run ─────────── team_events
    ├─────────────── optional task
    └─────────────── room

conversation_id groups related messages across direct, broadcast, or room flow
```

## Planned first-class entities

### Memory

Room Memory v0.1 is implemented as explicit, reviewable, room-scoped context.
Broader memory systems remain deferred.

### Tasks

Durable trackable units of work with optional room ownership, optional assigned
agent, optional source message, status, priority, ownership metadata, durable
comments, and durable event history. Tasks are now a first-class entity; they do
not imply automation.

### Decisions

Recorded choices with rationale, participants, and links back to the messages
or tasks that produced them.

Broader memory systems and decisions remain architectural commitments for later
slices.

## Agent doctrine

SynKraken treats config as the bootstrap source for agents, but durable agent
records as the operational source once registered. `AgentFabric` currently
synchronizes configured adapters into the durable `agents` table so later work
can build presence, handoffs, and permissions on one stable entity model.

## Client architecture

### TUI

The TUI calls the daemon directly on `127.0.0.1:9460`.

### Web Command Deck

The web command deck runs on `127.0.0.1:9461` and serves:

- static HTML/CSS/JS
- a same-origin proxy to the daemon's existing HTTP API
- a same-origin SSE proxy to the daemon event stream

This keeps browser concerns out of the daemon, avoids CORS changes, and lets
the web UI reuse exactly the same backend contract as the TUI.

The browser-facing proxy is a transport convenience, not a second domain API.
The daemon contract remains authoritative.

## Data flow

### Direct or broadcast message

1. client posts `/v1/messages`
2. daemon normalizes and stores a `FabricMessage`
3. router resolves the target set
4. adapters execute subprocess deliveries
5. each target agent moves to `working`
6. successful replies move agents to `idle`; timeouts/failures move them to
   `blocked`
7. deliveries, failures, reply messages, and agent events are persisted
8. events are published over SSE

### Room message

1. client posts target `room:<name>`
2. router resolves current room members
3. daemon loads concise room memory, if present, and injects it into each
   delivery prompt
4. each member receives the message
5. successful replies are added back into the room transcript as messages
6. each target agent records the room as current visible context while handling
   the delivery

### Discussion

1. client posts `/v1/discussions` with agents, topic, optional room, and bounded
   turn count
2. daemon stores the topic in the room transcript or a normal conversation
3. for each turn, daemon stores a visible marker such as `goose turn 1`
4. for room-scoped discussions, daemon injects concise room memory into each
   delivery prompt
5. daemon sends the current agent the original topic plus the previous reply
   when applicable
6. successful replies are stored as visible messages in the same room or
   conversation
7. the final turn asks for a recommendation
8. any failed or timed-out turn records a delivery/dead letter and a visible
   failure message, then stops the discussion cleanly
9. participating agents record discussion start/completion presence events

### Room memory auditability

Room memory lives in `room_memory`; changes append to `memory_events` with
actor, field, old value, new value, and timestamp. Prompt injection uses a
short text block capped below 500 characters and is reported in dispatch and
discussion results as `memory_context`.

### Task

1. client creates a task through the daemon API
2. task is stored in SQLite with optional links to a room, agent, and source message
3. later PATCH requests update human-controlled status, priority, assignment,
   or metadata
4. comments append durable task context without triggering workflow automation

### Team task

1. client posts `/v1/team-tasks` with room, question, and bounded turns
2. daemon stores the team prompt in the room transcript and creates an open task
3. clarify phase sends the prompt to all available room agents
4. nominate phase asks available agents for owner, reviewer, and optional support
5. daemon chooses the owner deterministically: most owner nominations, then
   configured role/capability match, then room member order
6. task moves to `in_progress` and is assigned to the owner
7. owner receives the original task plus a visible summary of team discussion
8. reviewers receive the owner output and return critique, risks, missing
   pieces, and suggested improvements
9. owner produces a final report with recommended solution, who did what,
   reviewer feedback, next action, and confidence/risks
10. task moves to `done`; task events record team start, nomination,
    assignment, review, and completion where available

If one participant fails, Team Task Mode continues with the available agents.
If the owner fails, SynKraken tries the next nominated or available owner. If no
owner can produce output, the task is blocked and the room transcript records a
clear failure.

### Team governance

1. every team task creates a `team_runs` record and appends `team_events`
2. `AUTO` mode marks the team run completed and task done after the final report
3. `REVIEW_REQUIRED` mode stores the final report, writes an approval prompt
   into the room transcript, and leaves the task in progress
4. `/approve <id>` records `approved`, marks the run approved, and marks the
   linked task done
5. `/reject <id>` records `rejected`, marks the run rejected, and marks the
   linked task blocked

Approval and rejection are explicit operator actions. They do not trigger
background execution or hidden agent work.

### Task auditability

Tasks carry `created_by` and `updated_by`, and every significant change appends
to `task_events`. This keeps operator-visible work inspectable without adding
workflow automation.

### Agent presence auditability

Agents carry durable operational state:

- `configured`, `online`, `idle`, `working`, `blocked`, `offline`, `disabled`
- `last_seen_at`
- `runtime`
- `current_task_id`
- `current_room`
- `last_message_at`

The `agent_events` table is append-only audit history for this operational
state. It is not a memory store, not a decision registry, and not a scheduling
primitive.

## Architectural constraints

- local-first by default
- stdlib-only runtime unless a dependency is clearly justified
- one authoritative backend model
- SQLite foreign keys enabled on every connection for local referential integrity
- adapters stay small and independent
- preserve operator visibility into state transitions
- do not permit silent agent-to-agent loops outside persisted transcripts
- Team Task Mode is human-commanded orchestration, not autonomous background
  work
- keep future integrations, including Studio:Blueprint, outside the core until
  their contract is clear

## Extension rules

When adding a new first-class object:

1. define its durable shape first
2. decide how it links to messages, rooms, and agents
3. expose it through the daemon API
4. only then add it to TUI and Web surfaces

When adding a new runtime:

1. keep it behind an adapter
2. reuse shared normalization where practical
3. update discovery and docs only when the runtime is stable enough to support

## Non-goals for the v0.2 foundation

- replacing the TUI
- adding autonomous scheduling
- building memory or decisions before their model is designed
- introducing a heavyweight frontend or backend framework
- making Studio:Blueprint a prerequisite for local use
