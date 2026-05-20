# Identity And Role Doctrine

## Core Rule

Roles are not identities.

An identity is the durable operational record for a configured runtime. A role
is a task-scoped responsibility assigned for a bounded workflow.

## Shipped Roles

SynKraken may ship these generic roles:

- `owner`
- `reviewer`
- `guardrail`
- `token_police`
- `coordinator`
- `specialist`

These roles are generic enough for OSS defaults, packs, and future vertical
products.

## Never Ship

Generic SynKraken code, docs, prompts, examples, tests, and default
configuration must never ship:

- personal aliases
- private names
- founder context
- industry assumptions

Local deployments may configure their own display names, runtime identities,
workspace labels, room memory, shared memory, skills, and prompt context.
Those belong outside repository defaults.

## Role Semantics

`owner` is accountable for producing the primary output of a bounded task or
goal.

`reviewer` critiques output against criteria, risks, missing work, and quality.

`guardrail` checks scope, security, architecture boundaries, policy fit, goal
drift, and overengineering risk.

`token_police` checks context size, prompt bloat, compaction, and whether
another round is worth the cost.

`coordinator` helps structure work and handoffs without becoming a hidden
planner.

`specialist` contributes scoped expertise when a task benefits from it.

## Documentation Rule

When docs need examples, use generic runtime ids, neutral rooms, and generic
role labels. Do not encode a particular person's life, business, or workflow
into the public project.
