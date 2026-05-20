# Packs Architecture

## Product Stack

SynKraken's product architecture is:

```text
OSS
↓
Packs
↓
Vertical products
```

## OSS Layer

The OSS layer is the durable control plane. It includes:

- local daemon
- SQLite persistence
- TUI and Web Command Deck
- runtime adapters
- rooms and messages
- durable agents
- roles and bounded runs
- room memory and shared memory
- tasks and audit events
- configuration doctrine

The OSS layer must stay runtime-neutral, local-first, generic, and useful
without proprietary packs.

## Packs Layer

Packs are optional bundles that add opinionated behavior on top of the OSS
control plane. A pack may include:

- role presets using the shipped role vocabulary
- workflow templates
- runtime adapter recommendations
- room setup patterns
- memory templates
- guardrail or token-budget defaults
- integration glue

Packs must not require private names, founder context, or industry assumptions
to exist in the OSS core.

## Vertical Products

Vertical products may package SynKraken for specific markets or operating
contexts after the OSS layer and packs layer are stable.

Verticals can make stronger assumptions than OSS, but those assumptions must
remain outside the generic repository defaults unless they are broadly valid
control-plane concepts.

## Compatibility Rule

A pack or vertical should extend the same durable SynKraken concepts rather
than creating parallel models. Rooms, agents, roles, tasks, memory, runs, and
events remain the shared substrate.
