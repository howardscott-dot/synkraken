# Roadmap

## v0.1 — Local bridge

Shipped foundation:

- local daemon
- direct messages and broadcast
- persistent rooms
- SQLite history
- dead letters and live SSE events
- adapters for Goose, Hermes, OpenClaw, and Claude Code
- operator CLI and TUI
- portable bridge skill

## v0.2 — Command Deck foundation

Primary goal: turn the useful local bridge into the documented foundation of a
larger local command deck without destabilizing what already works.

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

### Deliberately deferred

- workflow automation and recurring tasks
- autonomous background team work
- broader memory systems beyond room context
- vector DBs, embeddings, RAG, and semantic search
- decision registry
- Studio:Blueprint integration
- remote multi-user deployment
- heavyweight frontend stack

## Next sequence

1. Agent Model Doctrine v0.1
2. Agent Presence v0.1
3. Room Memory v0.1
4. Team Task Mode v0.1
5. Team Governance v0.1
6. Decisions v0.4
7. Handoffs v0.5
8. Workspace Packs v0.6
9. Studio:Blueprint Agent Teams v0.7

## Decision gates

Before building new memory systems, tasks, decisions, or handoffs:

- agree the durable schema
- define how each object relates to messages and rooms
- decide whether operators or agents may create/edit them
- keep the first implementation small enough to remain understandable

## Later

- Studio:Blueprint integration
- optional automation layers
- richer project/workspace organization
- import/export and archival workflows

## Roadmap rule

New features should strengthen the command deck model rather than turn
SynKraken into an opaque autonomous swarm. Human control, local ownership, and
inspectability remain product requirements.
