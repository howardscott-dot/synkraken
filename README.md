# SYNKRAKEN / agent-fabric

A local inter-agent fabric and operator console for heterogeneous AI runtimes.

**SYNKRAKEN** is the human-facing shell and TUI.
**agent-fabric** is the bridge daemon and routing core underneath it.

## What it does

- runs a local bridge daemon
- routes directed and broadcast messages across configured AI runtimes
- stores conversations and deliveries in SQLite
- exposes a small local HTTP API
- provides a local operator CLI and TUI
- supports bridge skills that can be installed into agent systems

## Quick start

```bash
# Install
pip install -e .

# Configure (interactive setup)
synkraken config

# Start the daemon
agent-fabric --config ./config.local.json &

# Check health
synkraken health

# Open the TUI
synkraken tui
```

## Agent Color Palette

Universal color assignments for agent identification:

| Agent | Dark (headers) | Light (chat) |
|-------|-----------------|--------------|
| `goose` | Grey `#7F7F7F` | Silver `#B0B0B0` |
| `hermes` | Amber `#B38F00` | Gold `#FFCC00` |
| `openclaw` | Coral `#CC4433` | Salmon `#E07060` |

See `docs/AGENT_PALETTE.md` for full specification.

## Main commands

### Health
```bash
synkraken health
```

### List agents
```bash
synkraken agents
```

### Send a directed message
```bash
synkraken send hermes "Reply with exactly: HELLO"
```

### Broadcast to all agents
```bash
synkraken send broadcast "Reply with one line naming your runtime."
```

### Open the TUI
```bash
synkraken tui
```

### Setup mode
```bash
synkraken config
```

## Configuration

Use one of the example configs in `examples/`:

- `examples/config.example.json` — uses executable names from `PATH`
- `examples/config.paths.local.example.json` — shows explicit absolute paths

Your active local config can live outside version control:
- `config.local.json`

## Repository layout

```
agent_fabric/          core package
docs/                  specifications and documentation
examples/              example configs and service files
scripts/               helper scripts
skills/                portable bridge skill
```

## License

MIT