# Development

## Local commands

### Run the daemon
```bash
python3 -m synkraken --config ./config.local.json
```

Or use the installed wrapper:
```bash
synkraken-daemon --config ./config.local.json
```


### User-level systemd service

```bash
./scripts/install-user-service.sh                 # defaults to ./config.local.json
systemctl --user enable --now synkraken
synkraken status                                   # service state + daemon health
synkraken stop daemon
synkraken start daemon
synkraken restart                                  # short alias for restart daemon
./scripts/uninstall-user-service.sh
```

Pass a different config path to the installer if needed:

```bash
./scripts/install-user-service.sh ~/.config/synkraken/config.json
```

### Operator CLI
```bash
synkraken start daemon
synkraken status
synkraken health
synkraken agents
synkraken send hermes "Reply with exactly: HELLO"
synkraken tui
synkraken web
synkraken config
```

### Live integration test

`scripts/live_integration_test.py` exercises a running local daemon through the
installed CLI and HTTP API. It does not launch the TUI or Web UI, and it writes
timestamped audit artifacts under `audits/`:

```bash
python3 scripts/live_integration_test.py --skip-restart
python3 scripts/live_integration_test.py --agents goose,hermes
python3 scripts/live_integration_test.py --daemon-url http://127.0.0.1:9460
```

Each run creates:

```text
audits/live-test-YYYYMMDD-HHMMSS/
├── report.md
├── raw.json
└── commands.log
```

Use `--skip-restart` while iterating. Omit it before release if the user-level
service is installed and restart coverage is desired.

## Repository conventions

- `examples/config.example.json` is generic and safe to publish
- `config.local.json` is local-only and ignored by git
- `data/` is runtime state and ignored by git
- `audits/` contains local integration-test reports and is ignored by git
- installed local wrappers in `~/.local/bin/` are machine-local and not part of the repo

## Adding new agents

1. Choose a color pair from `docs/AGENT_PALETTE.md`
2. Add the agent configuration to your config JSON
3. Ensure the agent has a compatible bridge skill installed
4. Verify connectivity with `synkraken agents`

## Release checklist

- [ ] Update version in `pyproject.toml`
- [ ] Update `CHANGELOG.md` (create if missing)
- [ ] Run `scripts/smoke_test.py`
- [ ] Run `python3 scripts/live_integration_test.py --skip-restart`
- [ ] Test TUI with all configured agents
- [ ] Verify docs are complete
- [ ] Tag and push
