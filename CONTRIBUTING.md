# Contributing to SynKraken

## Getting Started

```bash
git clone <repo>
cd synkraken
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # Install daemon + dev deps (pytest, ruff)
```

SynKraken has **no runtime dependencies** — the daemon and all operator
surfaces are pure Python standard library. The `[dev]` extra only adds test
and lint tooling.

## Running the Daemon

Start the daemon in the foreground (logs to stdout) with an example config:

```bash
synkraken-daemon --config examples/config.example.json
```

Then, in another terminal, drive it with the CLI or TUI:

```bash
synkraken status
synkraken tui
synkraken web        # local web command deck
```

`synkraken start` / `stop` / `restart` manage the daemon as a background
user service instead (LaunchAgent on macOS, systemd user unit on Linux).

## Key Files

- `synkraken/__main__.py`     — daemon entrypoint (`synkraken-daemon`)
- `synkraken/api.py`          — HTTP/SSE API server (daemon)
- `synkraken/storage.py`      — SQLite data layer
- `synkraken/fabric.py`       — core agent coordination logic
- `synkraken/adapters/`       — per-runtime adapter implementations
- `synkraken/cli_main.py`     — CLI (`synkraken`)
- `synkraken/tui.py`          — terminal UI
- `synkraken/web.py`          — web command deck

> `apps/console/` (the Tauri desktop console) is **retired** — see
> `docs/CONSOLE_RETIREMENT.md`. Do not add features there; the active web
> surface is `synkraken/web.py`.

## Code Style

- Run `ruff check synkraken/` before committing (must be clean).
- Python 3.11 minimum — no type ignores or `Any` without comment.
- New SQLite tables need a migration in `storage.py`.
- New API endpoints need corresponding CLI and TUI commands.

## Testing

```bash
make test                       # pytest suite under tests/
pytest tests/ -v                # verbose

# Offline smoke checks (no running daemon required):
python scripts/task_smoke_test.py
python scripts/adapter_conformance_smoke_test.py

# Guard against private-material leaks before pushing:
python scripts/context_audit.py
```

## Filing Issues

Please include:
- SynKraken version (from `pyproject.toml`, or `pip show synkraken`)
- OS and Python version (`python --version`)
- Steps to reproduce
- Relevant daemon logs (run `synkraken-daemon --config <path>` in the
  foreground and copy the stdout output)
