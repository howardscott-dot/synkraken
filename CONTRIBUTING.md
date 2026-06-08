# Contributing to SynKraken

## Getting Started

```bash
git clone <repo>
cd synkraken
pip install -e ".[dev]"    # Install daemon + dev deps
make test                    # Run the test suite
```

## Key Files

- `synkraken/api.py`         — HTTP/SSE API server (daemon)
- `synkraken/storage.py`     — SQLite data layer
- `synkraken/fabric.py`       — Core agent coordination logic
- `synkraken/adapters/`       — Per-runtime adapter implementations
- `apps/console/src/`         — React frontend (Tauri)
- `apps/console/src-tauri/`   — Tauri Rust backend

## Code Style

- Run `ruff check synkraken/` before committing
- Python 3.11 minimum — no type ignores or `Any` without comment
- New SQLite tables need a migration in `storage.py`
- New API endpoints need corresponding CLI and TUI commands

## Testing

```bash
make test        # full suite
pytest -v        # with verbose output
```

## Filing Issues

Please include:
- SynKraken version (`synkraken --version`)
- OS and Python version
- Steps to reproduce
- Relevant daemon logs (`synkraken run --verbose`)
