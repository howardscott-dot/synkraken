# PRD: SynKraken v1.4 Shared Workforce Memory

## Problem

Workers can lose conversational and operational context. Operators repeat
decisions, room context, handoff context, runtime-specific guidance, and
positioning notes because SynKraken lacked an explicit governed shared memory
layer.

## Objective

Add visible Shared Workforce Memory that stores human-approved memory items
and makes approved context available to all workers through deterministic
retrieval and bounded prompt injection.

## Scope

- local SQLite memory records
- explicit memory statuses: proposed, approved, rejected, archived
- operator-created approved notes
- proposed memory governance
- active context endpoint
- bounded approved-memory injection
- Console Memory Centre
- scoped memory sections for room, mission, outcome, assignment, and runtime
- Memory canvas node
- minimal CLI parity

## Non-Goals

- generic vector database
- opaque RAG
- hidden autonomous memory
- cloud memory
- user accounts or RBAC
- automatic trusted memory promotion
- AI memory rewriting

## Acceptance Criteria

- Operator can create global and room-scoped memory notes.
- Operator can approve, reject, and archive proposed memory.
- Approved memory appears in active context retrieval.
- Rejected and archived memory do not appear in active context retrieval.
- Scoped memory appears in room, mission, outcome, assignment, and runtime surfaces.
- Dispatch exposes relevant approved memory to workers in a bounded way.
- The operator can inspect what SynKraken remembers and why.
