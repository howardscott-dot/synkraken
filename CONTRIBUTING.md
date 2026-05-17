# Contributing to SYNKRAKEN

Thanks for your interest. Synkraken is a small project but already does
something useful — issues, fixes, new adapters, and TUI polish are all
welcome.

## Quick contribution paths

| Want to… | Where to start |
|---|---|
| Report a bug | Open an issue with reproduction steps and your `synkraken health` output |
| Suggest a feature | Open an issue describing the use case |
| Add an adapter for a new AI runtime | Read `synkraken/adapters/base.py` and copy one of the existing adapters as a template |
| Improve the TUI | `synkraken/tui.py` — single-file curses app, no external deps |
| Improve the bridge skill | `skills/synkraken-bridge/SKILL.md` — read by other agents to learn the protocol |

## Development setup

```bash
git clone https://github.com/howardscott-dot/synkraken.git
cd synkraken

# (Optional but recommended) virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode — zero runtime deps, so this is fast
pip install -e .

# Copy the example config and edit it to match the runtimes you have
cp examples/config.example.json config.local.json
$EDITOR config.local.json

# Start the daemon
synkraken-daemon --config ./config.local.json &

# Sanity check
synkraken health
synkraken agents

# Open the TUI
synkraken tui
```

## Running the smoke test

```bash
python3 scripts/smoke_test.py
```

## Code style

- Python 3.10+.
- Stdlib only — no runtime dependencies. The whole point of the project is to
  be a single `pip install -e .` away from working. If you have a strong case
  for adding a dependency, open an issue first.
- Type hints encouraged but not required. Use `from __future__ import annotations`
  at the top of new modules so forward refs work cleanly on 3.10.
- Prefer composition over abstraction. The codebase is intentionally flat
  (no factories where a function would do).
- Keep adapter modules independent of one another — each adapter is a leaf.

## Adding a new adapter

A new adapter is:

1. A new module in `synkraken/adapters/`, e.g. `synkraken/adapters/my_runtime.py`.
2. A `MyRuntimeAdapter` class extending `BaseAdapter` with a `send(message)
   -> AdapterReply` method.
3. Registration in `synkraken/adapters/__init__.py` — add an import and
   an entry in `ADAPTER_TYPES`.
4. (Optional) Detection in `synkraken/discovery.py` so `synkraken config`
   finds it.
5. (Optional) A color pair in `synkraken/tui.py` (`_AGENT_COLOR_PAIRS`)
   so messages from your runtime show in a distinct color.

A typical adapter is 40–100 lines. Reuse `cli_utils.run_command` for
subprocess handling and `text_normalize.normalize_text_output` for cleaning
up assistant output that includes tool chatter.

## Adding a runtime to the bridge skill

When you add an adapter, update `skills/synkraken-bridge/SKILL.md` so other
agents know your runtime can be addressed.

## Pull requests

- One topic per PR. A new adapter + a TUI rewrite + a docs pass = three PRs.
- Run the smoke test before opening the PR.
- Write a clear PR description: what you changed and why.
- If your change is user-visible, add a line to `CHANGELOG.md` under
  `## [Unreleased]`.

## Reporting security issues

Please don't open public issues for security problems. Email the maintainer
directly (address in `LICENSE`'s copyright line).

## License

By contributing, you agree your contributions will be licensed under the
MIT License — the same terms as the project (see `LICENSE`).
