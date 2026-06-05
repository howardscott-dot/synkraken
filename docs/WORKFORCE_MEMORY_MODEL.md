# Workforce Memory Model

Shared Workforce Memory is the visible, governed memory layer for SynKraken
v1.4.

It stores durable context that workers may receive across rooms, assignments,
outcomes, missions, runtimes, and the global workspace. It is local-first,
deterministic, auditable, operator-governed, and shared across agents.

## Doctrine

Visible Memory: shared memory must be inspectable, governable, and traceable.
SynKraken must not create hidden long-term memory, opaque RAG state, cloud
memory, or automatic trusted memory promotion.

Memory can be proposed. Only approved memory is returned by the active context
endpoint and injected into worker prompts by default. Rejected memory remains
for audit. Archived memory is excluded from active retrieval.

## Fields

- `memory_id`
- `memory_type`
- `title`
- `body`
- `scope_type`
- `scope_id`
- `source_type`
- `source_id`
- `created_by`
- `status`
- `importance`
- `created_at`
- `updated_at`
- `expires_at`

## Types

- `operator_note`
- `room_summary`
- `decision_memory`
- `handoff_memory`
- `mission_context`
- `outcome_context`
- `assignment_context`
- `runtime_observation`

## Status

- `proposed`
- `approved`
- `rejected`
- `archived`

## Importance

- `low`
- `medium`
- `high`
- `critical`

## Scope

- `global`
- `room`
- `mission`
- `outcome`
- `assignment`
- `runtime`

## API

- `GET /v1/memory`
- `GET /v1/memory/pending`
- `GET /v1/memory/{id}`
- `GET /v1/memory/context?scope_type=&scope_id=`
- `POST /v1/memory/propose`
- `POST /v1/memory/approve`
- `POST /v1/memory/reject`
- `POST /v1/memory/archive`
- `POST /v1/memory/operator-note`

## Injection

Worker dispatch uses approved memory only. Context is bounded to eight memory
items by default and ranked in this order:

1. assignment
2. outcome
3. mission
4. room
5. runtime
6. global

Injected lines include `memory_id`, type, title, and body. Dispatch responses
include injected memory ids for delivery visibility where available.

## Console

Console exposes this system as Knowledge. Memory is the implementation term.
Project Knowledge, global Knowledge, and contextual Knowledge surfaces show
approved, pending, rejected, and archived memory in operator language. Mission,
Outcome, Assignment, Room, and Runtime detail surfaces may still show approved
memory for that scope in Advanced. Canvas includes a read-only Memory node for
inspection.
