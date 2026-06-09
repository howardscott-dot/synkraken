# Installing SynKraken

## Requirements

- Python 3.11+
- One or more of: Goose, Claude Code, Hermes, OpenClaw (optional — SynKraken works with whatever adapters are configured and available)

## Install the daemon

```bash
pip install -e .
```

## Configure adapters

Copy the example config:

```bash
cp examples/config.example.json config.json
```

Edit `config.json` and enable only the adapters you have installed.
Set `command` to the full path if the binary is not in your PATH.
See `examples/config.paths.local.example.json` for a reference.

## Start the daemon

```bash
synkraken run --config config.json
```

The daemon listens on `127.0.0.1:9460` by default. All surfaces (CLI, TUI, Web)
connect to this URL.

## Surfaces

After starting the daemon:
- **Web Command Deck**: open `http://localhost:9460` in your browser
- **Terminal TUI**: `synkraken tui --config config.json`
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
