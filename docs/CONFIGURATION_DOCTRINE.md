# Configuration Doctrine

SynKraken ships as generic local infrastructure. The repository must not encode
one operator's identity, business context, client work, proprietary project
names, local usernames, absolute machine paths, or personal workflows.

All tailoring belongs outside shipped defaults.

## Static Code

Static code, packaged docs, bundled skills, examples, tests, and default prompts
must remain generic. They may name supported runtime integrations, protocol
concepts, and neutral examples, but they must not include installation-specific
goals or private context.

Allowed examples:

- `operator`
- `room:general`
- `/path/to/project`
- `Build consulting platform`
- `Coordinate a portable software project`

Disallowed examples:

- personal names as actors or agents
- local usernames or home directories
- proprietary project names
- business plans, client names, or internal methodologies
- one user's recurring workflow

## Install Context

Installation context is customisable through local configuration. Optional
fields may identify the local deployment without changing shipped defaults:

- `instance.instance_name`
- `instance.organisation_name`
- `instance.default_workspace`

These fields are optional and empty in examples.

Runtime discovery output belongs in local config. `config.local.json` may store
adapter blocks and `runtime_registry` entries discovered on the operator's
machine, including local command paths and version strings. Shipped defaults
must stay generic and must not encode one machine's discovered runtimes.

## Workspace Context

Workspace-specific purpose, project labels, and team conventions belong in
workspace config or runtime context. They should not appear in repository
defaults.

## Room Context

Room-specific context belongs in Room Memory. Operators can set room purpose,
objective, rules, constraints, focus, and notes after installation.

## Goal Context

Goal Mode goal text, criteria, reviewer feedback, token notes, guardrail notes,
and final reports are runtime room context. Shipped defaults may define generic
limits such as `goal.max_rounds`, `goal.threshold`,
`goal.max_context_chars`, `goal.max_revision_chars`, `goal.max_reviewers`, and
`goal.max_agents`, but they must not encode project-specific goals, private
workflows, or organisation-specific success criteria.

Goal Mode is bounded team execution, not hidden background autonomy or a way to
ship project-specific defaults.

## Memory Context

Shared Memory may store durable workspace knowledge only after proposal and
peer review. It remains visible, bounded, inspectable, and token-conscious.

Shared Memory is not a place for hidden personal profiling, private business
context in shipped defaults, vector search, RAG, cloud sync, or autonomous
background memory mining.

## Skills And Runtime Context

Runtime-specific skills may explain how to use SynKraken generically. Local
agent identity, preferred workflow, and organisation-specific methods must be
provided by the runtime's own local configuration or by user prompts, not by
the shared SynKraken repository.

## Audit Rule

Run `python3 scripts/context_audit.py` before publishing. Any finding must be
removed, made generic, or documented as a deliberate exception.
