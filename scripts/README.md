# Scripts

## Tests

The authoritative unit suite lives in `tests/` and runs with `pytest tests/`
(also `make test`). It covers config validation, storage correctness, adapter
subprocess hygiene, and the daemon HTTP security gate — all offline, no running
daemon or external runtimes required.

The `scripts/*_smoke_test.py` files are additional self-contained integration
checks (most run fully offline against a temporary database). They are useful
for exercising broader flows and are run in CI alongside the pytest suite.

A few smoke tests require a **running daemon** or **real runtimes** and are not
run in CI: `smoke_test.py`, `live_integration_test.py`, `cli_stress_test.py`.

Active smoke tests target:

- daemon API behavior
- CLI behavior
- TUI behavior
- Web Command Deck behavior
- adapter conformance
- future MCP tool contracts

## Archived

`scripts/archive/console/` holds historical source checks for the **retired**
Tauri Console prototype (see `docs/CONSOLE_RETIREMENT.md`). They assert against
`apps/console/src/App.tsx` and are not part of the active release checklist.
