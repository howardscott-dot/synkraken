# Console Retirement

## Status

The Tauri Console under `apps/console` is retired as an active SynKraken
product surface.

It remains in the repository as historical prototype and design reference only.
Do not treat it as release-blocking, do not add new Console product features,
and do not require Console build or smoke tests for normal SynKraken releases.

## Official Surfaces

Active SynKraken surfaces are:

- daemon HTTP API and SSE event stream
- CLI
- TUI
- Web Command Deck
- future MCP-compliant tool surface

The daemon remains the source of truth for SQLite state, rooms, dispatch,
events, governance, memory, assignments, missions, outcomes, runbooks,
artifacts, evidence, approvals, and traces.

## What To Do With Console Ideas

Useful Console ideas should be harvested into active surfaces:

- deterministic briefing -> daemon read model, CLI, TUI, Web
- room operations -> daemon API, CLI, TUI, Web
- governance inbox -> daemon API, CLI, TUI, Web
- spatial relationships -> daemon read model first, then Web if useful
- command palette ideas -> TUI slash commands and Web command affordances

Do not revive Console-only models, direct SQLite reads, or a second backend.

## Tests

Existing `scripts/console_*_smoke_test.py` files are historical source checks.
They are not part of the active release checklist. New smoke tests should
target daemon APIs, CLI, TUI behaviour, Web Command Deck behaviour, and MCP
tool contracts.
