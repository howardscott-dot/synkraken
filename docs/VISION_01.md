# Vision 01

## Position

SynKraken is an **open-source control plane for AI workforces**.

It exists for operators who use multiple AI runtimes and need one local place
to see, direct, govern, recover, and learn from that work without handing
ownership to a remote platform or a hidden autonomous system.

## SynKraken Is

- local-first
- runtime-neutral
- an AI workforce control plane
- a management harness
- a governance layer
- a memory layer
- a coordination system
- an observability layer

## SynKraken Is Not

- another coding agent
- an orchestration LLM
- a chatbot
- a CrewAI clone
- a hidden autonomous swarm

## Control Boundary

Users own:

- subscriptions
- API keys
- costs
- runtimes

SynKraken owns:

- visibility
- governance
- coordination
- recovery

## Product Direction

SynKraken starts as open-source local infrastructure. The product path is:

```text
OSS
↓
Packs
↓
Vertical products
```

The open-source layer defines the durable control plane: daemon, storage,
operator surfaces, runtime adapters, rooms, roles, governance events, memory,
tasks, and auditability.

Packs add opinionated but optional workflow, runtime, and domain bundles on
top of the open-source layer.

Vertical products may later package SynKraken for specific operating contexts,
but they must not force private assumptions, personal aliases, or one
industry's workflow into the generic OSS core.

## Expansion Rule

Every new feature should strengthen the control plane. It should improve at
least one of visibility, governance, coordination, memory, recovery,
observability, runtime neutrality, or local ownership.

Features that make SynKraken act like a hidden agent, opaque planner, chatbot,
or vendor-specific orchestration layer are outside the vision.
