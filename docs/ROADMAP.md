# Roadmap

## Position Lock

SynKraken is an open-source control plane for AI workforces.

It is local-first, runtime-neutral, and responsible for visibility,
governance, coordination, recovery, memory, and observability around AI
runtimes the user owns. It is not another coding agent, an orchestration LLM,
a chatbot, a CrewAI clone, or a hidden autonomous swarm.

The product architecture is:

```text
OSS
↓
Packs
↓
Vertical products
```

Before further feature expansion, new roadmap items must fit this control
plane model.

## v0.1 — Local control plane foundation

Shipped foundation:

- local daemon
- direct messages and broadcast
- persistent rooms
- SQLite history
- dead letters and live SSE events
- adapters for Goose, Hermes, OpenClaw, Claude Code, Crush, and Google Antigravity
- runtime discovery and workforce onboarding v0.1 with config merge,
  registry-only unsupported runtimes, and JSON discovery output
- operator CLI and TUI
- portable runtime-communication skill

## v0.2 — Command Deck foundation

Primary goal: turn the useful local runtime fabric into the documented
foundation of a larger local control plane without destabilizing what already
works.

### In scope

- product vision and architecture documentation
- Web Command Deck v0.1 over the existing daemon APIs
- preservation of the current daemon and TUI
- explicit product model for rooms, messages, agents, memory, tasks, decisions
- continued local-first, low-dependency posture

### Command Deck v0.1

- rooms panel
- live messages
- send box
- agent presence
- broadcast
- room messaging

### Command Deck v0.2

- room creation
- direct agent messaging
- live typing indicators / presence cues
- clearer target selection in the web surface
- Tasks v0.1: durable tasks with room, agent, and source-message linkage
- Tasks Hardening v0.15: ownership metadata, event history, and enforced
  referential integrity
- Agent Model Doctrine v0.1
- Agent Presence v0.1: durable operational agent state and inspectable events
  without memory, decisions, scheduling, autonomous workflows, or cloud sync
- Room Memory v0.1: persistent, inspectable room context with purpose,
  objective, rules, constraints, focus, notes, event history, simple TUI/Web
  editing, and concise room-scoped prompt injection
- Team Task Mode v0.1: explicit room-only team orchestration with durable task
  creation, deterministic owner selection, visible review/final-report phases,
  and no background autonomy
- Team Governance v0.1: durable team runs, team events, approval-required mode,
  and explicit approve/reject controls for bounded room team work
- Shared Memory Skill v0.1: peer-reviewed, inspectable, bounded workspace
  knowledge without embeddings, vector DBs, RAG, cloud sync, hidden memory, or
  autonomous background mining
- Goal Mode v0.1: bounded room goal execution with success criteria, owner and
  reviewer assignment, Token Police and Guardrail Agent control roles,
  threshold scoring, compact revision rounds, durable `goal_runs` and
  `goal_events`, Web/TUI/API controls, and no background autonomy
- Decision Records v0.1: durable proposed, approved, rejected, or superseded
  decisions with proposer, approval or rejection actor, reason, confidence,
  related runtime ids, related message ids, API routes, TUI commands, a minimal
  Web Command Deck list, and append-only decision events

### Deliberately deferred

- workflow automation and recurring tasks
- autonomous background team work
- unbounded Goal Mode retries or hidden background goal execution
- autonomous, semantic, or personal memory systems beyond peer-reviewed Shared
  Memory
- vector DBs, embeddings, RAG, and semantic search
- voting, handoffs, policy engine, flight recorder, and decision workflows
- external product integrations
- remote multi-user deployment
- heavyweight frontend stack

## Next sequence

1. Agent Model Doctrine v0.1
2. Agent Presence v0.1
3. Room Memory v0.1
4. Team Task Mode v0.1
5. Team Governance v0.1
6. Shared Memory Skill v0.1: peer-reviewed, inspectable, bounded workspace
   knowledge without embeddings, vector DBs, RAG, cloud sync, hidden memory, or
   autonomous background mining
7. Goal Mode v0.1: bounded team execution loops for selected rooms, with
   threshold scoring, token budget review, guardrail review, and visible
   transcripts
8. Decision Records v0.1: record what was decided, who proposed it, who
   approved or rejected it, why, and what messages or runtimes it relates to
9. Runtime Discovery hardening: adapter additions for discovered registry-only
   runtimes, richer local server probes, and non-secret health diagnostics
10. Handoffs v0.5
11. Workspace Packs v0.6
12. External product integrations v0.7

Packs sit above the OSS control plane and below vertical products. They may add
workflow templates, role presets, memory templates, runtime recommendations,
and integration glue, but they must reuse the shared model for rooms, agents,
roles, tasks, memory, runs, and events.

## Decision gates

Before building new memory systems, tasks, decisions, or handoffs:

- agree the durable schema
- define how each object relates to messages and rooms
- decide whether operators or agents may create/edit them
- keep the first implementation small enough to remain understandable
- verify the feature strengthens the control plane rather than turning
  SynKraken into a worker runtime or hidden planner

## Later

- external product integrations
- optional automation layers
- richer project/workspace organization
- import/export and archival workflows

## Roadmap rule

New features should strengthen the command deck model rather than turn
SynKraken into an opaque autonomous swarm. Human control, local ownership, and
inspectability remain product requirements.

Shared Memory follows the same rule: it may help future room messages,
discussions, and team tasks, but only as visible, peer-reviewed, budgeted
context.

Goal Mode follows the same rule: it may iterate on a room goal, but only within
configured round, agent, context, and review limits. It must not become hidden
autonomy, permissionless execution, or unlimited context stuffing.

Shipped defaults must stay generic. Project-specific context belongs in
installation config, workspace config, room memory, shared memory, skills,
runtime context, or user prompts.
