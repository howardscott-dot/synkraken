# Development

## Local commands

### Run the daemon
```bash
python3 -m agent_fabric --config ./config.local.json
```

Or use the installed wrapper:
```bash
agent-fabric --config ./config.local.json
```

### Operator CLI
```bash
synkraken health
synkraken agents
synkraken send hermes "Reply with exactly: HELLO"
synkraken tui
synkraken config
```

## Repository conventions

- `examples/config.example.json` is generic and safe to publish
- `config.local.json` is local-only and ignored by git
- `data/` is runtime state and ignored by git
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
- [ ] Test TUI with all configured agents
- [ ] Verify docs are complete
- [ ] Tag and push