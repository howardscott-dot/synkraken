# Documentation Positioning GitHub Readiness PRD

Date: 2026-06-01

## 1. Objective

Update SynKraken's public-facing documentation so the project is described as
an open-source AI Workforce Operating System: a local-first control plane for
coordinating, governing, tracing, and operating heterogeneous AI workers.

## 2. Problem

SynKraken has evolved beyond its initial message routing, TUI, and web command
deck roots. The codebase now includes runtime discovery, workforce reputation,
rooms, goals, decisions, handoffs, proposal governance, flight recorder replay,
incidents, dead letters, memory governance, and a Tauri desktop Console with a
spatial operations canvas. Several documents still emphasize router, utility,
framework, or dashboard language, which undersells the current product and can
mislead GitHub visitors about the actual operator model.

## 3. Documentation Affected

- `README.md`
- `CHANGELOG.md`
- `apps/console/README.md`
- `docs/ARCHITECTURE.md`
- `docs/COMMAND_DECK_SPEC.md`
- `docs/WORKFORCE_MODEL.md`
- `docs/CONTROL_PLANE_DOCTRINE.md`
- `docs/COST_AND_RUNTIME_DOCTRINE.md`
- new product, governance, console, operator, screenshot, and GitHub metadata
  documentation under `docs/`

## 4. Positioning Changes

- Lead with "open-source AI Workforce Operating System."
- Describe SynKraken as a local-first operator control plane for AI workers.
- Emphasize operator authority, governance, traceability, recovery, reputation,
  rooms, and spatial operations.
- Keep claims grounded: local-first, no cloud SaaS claim, no autonomous
  production execution claim, and v0.1 proposal execution remains simulated.

## 5. Terminology Changes

Prefer:

- AI Workforce Operating System
- operator control plane
- runtime governance platform
- human-supervised AI workforce
- spatial operations console
- runtime reputation
- flight recorder / replay / trace

Avoid as primary positioning:

- multi-agent router
- agent framework
- TUI utility
- chatbot wrapper
- autonomous swarm
- message bus

Technical references to routing, messages, adapters, and event transport may
remain where they accurately describe implementation details.

## 6. Files Expected To Change

Expected new files:

- `docs/PRODUCT_VISION.md`
- `docs/CORE_CONCEPTS.md`
- `docs/GOVERNANCE_MODEL.md`
- `docs/SPATIAL_CANVAS_MODEL.md`
- `docs/UI_CONSOLE_DOCTRINE.md`
- `docs/OPERATOR_GUIDE.md`
- `docs/WHY_SYNKRAKEN.md`
- `docs/GITHUB_DESCRIPTION.md`
- `docs/screenshots/README.md`
- `docs/prds/2026-06-01-documentation-positioning-github-readiness.md`

Expected modified files:

- `README.md`
- `CHANGELOG.md`
- `apps/console/README.md`
- `docs/ARCHITECTURE.md`
- `docs/COMMAND_DECK_SPEC.md`
- `docs/WORKFORCE_MODEL.md`
- `docs/CONTROL_PLANE_DOCTRINE.md`
- `docs/COST_AND_RUNTIME_DOCTRINE.md`

## 7. Acceptance Criteria

- README answers what SynKraken is, why it exists, what it can do, how to run
  it, and why it differs from chatbot wrappers, IDE copilots, terminal
  multiplexers, workflow automation, and agent frameworks.
- New docs define canonical vocabulary, governance model, spatial canvas model,
  console doctrine, operator workflow, long-term product vision, rationale, and
  GitHub metadata copy.
- Architecture and doctrine docs use AI Workforce Operating System / operator
  control plane language while preserving accurate implementation details.
- Screenshot inventory exists without inventing screenshot files.
- Documentation remains honest about current limitations, including simulated
  execution in proposal governance v0.1.
- No runtime behavior, daemon logic, storage logic, Console behavior, or API
  behavior is changed.

## 8. Validation Plan

Run:

```bash
python3 scripts/context_audit.py
python3 -m compileall synkraken scripts
git diff --check
```

Where practical, verify referenced commands against `synkraken/cli_main.py`,
root `package.json`, `apps/console/package.json`, and existing scripts.

## 9. Explicit Out Of Scope

- Runtime behavior changes
- Daemon logic changes
- Storage schema or query changes
- Console behavior or UI implementation changes
- API changes
- New product features
- Cloud, SaaS, auth, RBAC, or multi-user claims
- Generated screenshots or large design exports
- Frontend builds unless documentation changes require them
- Rewriting private or unrelated implementation files already dirty in the
  working tree

## Completion Update

### Completed Work

- Rewrote `README.md` as a GitHub landing page for SynKraken as an
  open-source AI Workforce Operating System.
- Created canonical product and operator docs for vision, rationale, core
  concepts, governance, spatial canvas, Console doctrine, operator workflow,
  GitHub description copy, and screenshot inventory.
- Updated architecture, command deck, workforce, control-plane, cost/runtime,
  Console README, and changelog wording to reflect the current product shape.
- Preserved implementation-accurate language for routing, messages, adapters,
  event streams, SQLite, and daemon ownership where those terms describe real
  system mechanics.
- Added screenshot inventory placeholders without inventing image assets.

### Deferred Work

- Actual screenshots remain deferred until stable image assets are committed.
- Deeper rewrites of older historical docs such as `docs/VISION_01.md`,
  `docs/CATEGORY_POSITION.md`, and `docs/PACKS_ARCHITECTURE.md` remain future
  cleanup.
- No frontend build was run because this sprint changed documentation only.

### Tests And Validation Run

- `python3 scripts/context_audit.py`: passed with existing LICENSE exception.
- `python3 -m compileall synkraken scripts`: passed.
- `git diff --check`: passed after removing extra blank lines at EOF.

### Known Limitations

- Documentation now describes the intended public product position, but some
  older historical docs may still use earlier control-plane wording.
- Proposal execution is still documented as simulated for sensitive actions in
  v0.1; no runtime execution behavior was changed.
- Existing uncommitted implementation changes elsewhere in the working tree
  were not modified as part of this documentation sprint.
