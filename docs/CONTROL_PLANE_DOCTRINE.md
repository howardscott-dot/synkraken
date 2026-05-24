# Control Plane Doctrine

## Purpose

SynKraken coordinates AI workforces without becoming the worker, model, or
runtime. It is the local control plane around heterogeneous runtimes.

## Responsibilities

SynKraken is responsible for:

- visibility into agents, rooms, tasks, memory, deliveries, and failures
- governance over bounded workflows, approvals, roles, and audit trails
- coordination across direct messages, broadcasts, rooms, discussions, team
  tasks, and goals
- recovery through durable storage, blocked states, dead letters, and
  inspectable partial transcripts
- observability through append-only events and operator surfaces
- runtime discovery that inventories local tools without executing work,
  inferring subscriptions, or storing secrets

SynKraken is not responsible for:

- paying runtime or model costs
- hiding API keys or subscriptions inside the product
- replacing model-provider controls
- pretending to be the agent that performed the work
- running unbounded background autonomy

## Local-First Contract

The default deployment is local: loopback networking, SQLite persistence,
operator-owned configuration, and runtime adapters invoked on the same machine.

Remote deployment, multi-user auth, cloud memory, and product integrations may
exist later, but they must build on the same visible control-plane model rather
than redefining it.

## Runtime Neutrality

Runtimes sit behind leaf adapters. Adapters may know how to invoke Claude Code,
Goose, Hermes, OpenClaw, or future runtimes, but the control plane must not
collapse into one runtime's assumptions.

The daemon owns durable concepts. Runtimes own their model behavior, provider
accounts, prompt handling, and execution costs.

Runtime discovery must remain neutral. It may find commands, safe version
strings, capabilities declared by SynKraken's registry, and supported adapter
modes. It must not imply that SynKraken owns the runtime, pays for it, can use
it without operator approval, or has verified account entitlements.

## Operator Authority

Human command remains primary. SynKraken may coordinate work after an explicit
operator action, but it must keep bounded workflows visible, interruptible, and
auditable.

Hidden loops, hidden memory writes, silent agent-to-agent control, and
permissionless execution are outside the doctrine.

Discovery and onboarding must preserve operator authority. `merge` keeps
existing adapter settings, `replace` rewrites only after an explicit choice,
and `skip` leaves local configuration unchanged.
