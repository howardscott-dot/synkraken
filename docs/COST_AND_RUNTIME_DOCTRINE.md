# Cost And Runtime Doctrine

## Ownership

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
- traceability
- local operator workflow state

## Runtime Boundary

SynKraken invokes configured runtimes through adapters. It does not bundle,
resell, proxy, or abstract away provider accounts by default.

Each runtime keeps its own subscription model, API key handling, permissions,
tool policy, and provider-specific constraints. SynKraken records and exposes
the coordination state around runtime use.

## Cost Boundary

SynKraken must be token-conscious, but it is not the payer or provider. Its
job is to make work visible enough that users can understand and control cost.

Cost-conscious features include:

- bounded rounds
- context budgets
- token police roles
- compact summaries between rounds
- visible memory injection limits
- runtime reputation and health signals that help prefer cheap healthy workers
  in cheap mode and trusted premium workers in full mode
- explicit operator approval modes where needed

## Product Rule

Do not hide provider cost behind SynKraken language. Documentation and product
surfaces should make clear that users bring the runtimes and pay their costs.

SynKraken may help reduce waste, prevent runaway loops, and recover from
failures, but it must not imply free execution or vendor-owned capacity.

SynKraken does not assume all runtimes are equally reliable or equally
appropriate for every cost mode. Runtime health may bias selection, but the
operator still owns the enabled runtime set, subscriptions, and cost exposure.
Health bias must never silently remove or disable a configured worker.

## Positioning Rule

Documentation may describe SynKraken as an open-source AI Workforce Operating
System, but it must not imply that SynKraken owns provider capacity, absorbs
model cost, brokers subscriptions, or provides cloud execution by default.
