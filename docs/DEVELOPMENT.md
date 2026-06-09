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


### Cross-platform runtime service

```bash
synkraken install                                  # Linux user service or macOS LaunchAgent
synkraken status
synkraken doctor
synkraken stop
synkraken start
synkraken restart
synkraken uninstall                                # preserves config and data
```

Pass a different config path to the installer if needed:

```bash
synkraken install --config ~/.config/synkraken/config.json
```

### Operator CLI
```bash
synkraken start
synkraken status
synkraken health
synkraken agents
synkraken send hermes "Reply with exactly: HELLO"
synkraken tui
synkraken web
synkraken config
```

### Active operator surfaces

The supported product surfaces are:

- CLI
- TUI
- Web Command Deck
- daemon API and future MCP-compliant tool surface

The historical Tauri Console under `apps/console` is retired as an active
surface. Do not add release-blocking console smoke tests, Console build steps,
or new Console UI work unless explicitly reviving the prototype.

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
- [ ] Smoke-test Web Command Deck if web-facing routes changed
- [ ] Smoke-test MCP tool surface when MCP routes/tools change
- [ ] Verify docs are complete
- [ ] Tag and push
