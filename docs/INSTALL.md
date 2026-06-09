# Installing SynKraken

## Requirements

- Python 3.11+
- One or more of: Ollama, Goose, Claude Code, Hermes, OpenClaw, Crush, or Antigravity

## Install, Configure, And Start

```bash
./scripts/setup.sh
```

Then open the terminal UI:

```bash
synkraken tui
```

If SynKraken is already installed, use `synkraken setup` to refresh local
worker configuration and restart the runtime. For SSH workers or advanced
rediscovery, use `synkraken config`.

## Surfaces

After starting the daemon:
- **Web Command Deck**: open `http://localhost:9460` in your browser
- **Terminal TUI**: `synkraken tui`
- **CLI**: `synkraken --help`

## Retired Console Prototype

The historical Tauri Console under `apps/console` is no longer an official
operator surface. Do not install Rust or Node just to use SynKraken. Use the
TUI, Web Command Deck, CLI, and future MCP-compliant tools instead.

## Platform Notes

**macOS**: If you use Homebrew Python, ensure `python3` points to 3.11+.
**Linux**: On Ubuntu/Debian, `sudo apt install build-essential` is useful for
general development.
**Windows**: Use WSL2. SynKraken is a local-first tool and is not tested on native Windows.
