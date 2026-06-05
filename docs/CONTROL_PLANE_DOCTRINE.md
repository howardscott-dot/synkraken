# Control Plane Doctrine

## Purpose

SynKraken is an open-source AI Workforce Operating System. It coordinates AI
workforces without becoming the worker, model, or runtime. Its core is the
local operator control plane around heterogeneous runtimes.

## Responsibilities

SynKraken is responsible for:

- visibility into agents, rooms, tasks, memory, deliveries, and failures
- governance over bounded workflows, approvals, roles, and audit trails
- execution authority through explicit proposals, approvals, rejections,
  cancellations, simulated execution records, and proposal audit events
- coordination across direct messages, broadcasts, rooms, discussions, team
  tasks, and goals
- recovery through durable storage, blocked states, dead letters, and
  inspectable partial transcripts
- observability through append-only events and operator surfaces
- deterministic workforce health through delivery-derived runtime reputation,
  trust scores, health statuses, and lightweight incident summaries
- runtime discovery that inventories local tools without executing work,
  inferring subscriptions, or storing secrets
- spatial operations over workforce objects through Console canvas nodes,
  relationships, inspector views, and detail screens

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

Operator surfaces are part of runtime neutrality. They must render the actual
enabled workforce reported by the daemon and must not encode fixed worker
slots, fixed adapter counts, or hidden allowlists. Unknown adapter ids should
remain visible with generic presentation.

Visibility includes weak behavior. Empty replies, suspicious or unexpected
output, wrong identity replies, timeouts, blocked deliveries, and failures are
control-plane facts; clients must surface them plainly instead of suppressing
or smoothing them away.

Runtime reputation is part of visibility and governance. SynKraken does not
assume all AI workers are equally reliable; it continuously evaluates
operational quality with deterministic counters and explicit health rules. It
must not become hidden AI scoring, an opaque scheduler, or a reason to silently
disable runtimes. Any routing effect must remain a visible bias under operator
authority.

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

## Approval And Execution Authority

SynKraken's execution authority model is:

```text
Agents may propose.
Humans approve.
SynKraken executes.
Everything is traceable.
```

Workers do not directly execute sensitive actions through SynKraken. A worker
may create a proposal for an action such as shell execution, git operations,
restart, delete, write, replay, retry, memory promotion, or room summary
promotion. The proposal records risk, approval requirement, links to related
rooms/tasks/goals/decisions/handoffs/messages, and the execution payload.

Approval & Execution Governance v0.1 is deterministic and hardcoded rather
than policy-scripted. It classifies action risk, records whether approval is
required, and explains why. Approval changes proposal status only. Execution is
not autonomous and does not run dangerous shell, git, file, or daemon actions
in v0.1; it records simulated execution so the authority trail is durable and
replayable.

This governance layer is not RBAC, enterprise IAM, a policy DSL, hidden
autonomy, or an agent permission system. It is the local authority ledger for
operator-controlled execution flow.

## Product Boundary

SynKraken may be ambitious as an operating layer for AI workforces, but public
documentation must stay honest about current scope. It is local-first. It is
not a cloud SaaS claim. Proposal execution for sensitive actions is simulated
in v0.1. Operator surfaces should not imply hidden autonomous production
execution.
