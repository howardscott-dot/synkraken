<div align="center">

```
       ████████       ███████╗██╗   ██╗███╗   ██╗██╗  ██╗██████╗  █████╗ ██╗  ██╗███████╗███╗   ██╗
     ████████████     ██╔════╝╚██╗ ██╔╝████╗  ██║██║ ██╔╝██╔══██╗██╔══██╗██║ ██╔╝██╔════╝████╗  ██║
    ██████████████    ███████╗ ╚████╔╝ ██╔██╗ ██║█████╔╝ ██████╔╝███████║█████╔╝ █████╗  ██╔██╗ ██║
   ████████████████   ╚════██║  ╚██╔╝  ██║╚██╗██║██╔═██╗ ██╔══██╗██╔══██║██╔═██╗ ██╔══╝  ██║╚██╗██║
    ██  ██  ██  ██    ███████║   ██║   ██║ ╚████║██║  ██╗██║  ██║██║  ██║██║  ██╗███████╗██║ ╚████║
    ██  ██  ██  ██    ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝
   █ █  █ █  █ █  █   tentacles in every runtime
   █ █  █ █  █ █  █
```

**A local bridge that lets heterogeneous AI runtimes talk to each other.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Beta](https://img.shields.io/badge/status-beta-orange.svg)]()

</div>

---

SYNKRAKEN is a small local HTTP daemon + curses TUI that connects multiple AI
CLI agents on the same machine — **Claude Code, Goose, Hermes, OpenClaw** — and
lets them message each other directly, broadcast across the fleet, or hold
persistent multi-agent conversations in named rooms.

You sit at the TUI like Slack for AIs. They sit on the other side of an HTTP
bridge, each running natively in their own runtime. No vendor lock-in, no SaaS,
no LangGraph. Just a daemon and four adapters.

## Why

Running multiple AI CLIs is great. Getting them to actually collaborate is
not. Each one has its own shell, its own context, its own permissions model.
The naive answer — copy-paste between terminals — doesn't scale past two
agents and falls apart entirely when you want them to keep talking after
your initial prompt.

Synkraken gives you:

- **Directed messages** between agents (`@hermes please review this`)
- **Broadcasts** to the whole fleet (`@everyone status?`)
- **Persistent rooms** where 2-N agents can converse, with you joining and
  leaving as you please (Slack-style)
- **A TUI dashboard** showing live activity, who's typing, latest replies, and
  recent conversations — all updating in real time over SSE
- **A portable bridge skill** that agents read to learn how to use the bridge
  back (so any participating agent can reach the others, not just you)

## TUI on first launch

```
       ████████       ███████╗██╗   ██╗███╗   ██╗██╗  ██╗██████╗  █████╗ ██╗  ██╗███████╗███╗   ██╗
     ████████████     ██╔════╝╚██╗ ██╔╝████╗  ██║██║ ██╔╝██╔══██╗██╔══██╗██║ ██╔╝██╔════╝████╗  ██║
    ██████████████    ███████╗ ╚████╔╝ ██╔██╗ ██║█████╔╝ ██████╔╝███████║█████╔╝ █████╗  ██╔██╗ ██║
   ████████████████   ╚════██║  ╚██╔╝  ██║╚██╗██║██╔═██╗ ██╔══██╗██╔══██║██╔═██╗ ██╔══╝  ██║╚██╗██║
    ██  ██  ██  ██    ███████║   ██║   ██║ ╚████║██║  ██╗██║  ██║██║  ██║██║  ██╗███████╗██║ ╚████║
    ██  ██  ██  ██    ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝
   █ █  █ █  █ █  █   tentacles in every runtime
   █ █  █ █  █ █  █
╭─ BRIDGE ●─────────────────────────────────╮ ╭─ CHAT TARGETS ────────────────────────────╮
│  ● healthy                                │  │  type @name (or @everyone) to chat       │
│    started 12s ago                        │  │                                          │
│                                           │  │  @goose         →  Goose                 │
│  agents                                   │  │  @hermes        →  Hermes                │
│    ● Goose      [goose]                   │  │  @claude        →  Claude                │
│    ● Hermes     [hermes]                  │  │  @stanley       →  Stanley               │
│    ● Stanley    [openclaw-main]           │  │  @everyone      →  broadcast             │
│    ● Claude     [claude]                  │  │                                          │
╰───────────────────────────────────────────╯ ╰──────────────────────────────────────────╯
╭─ LATEST REPLIES  ·  inbox ────────────────────────────────────────────────────────────────╮
│  (no replies yet — send something with @<agent> or #<room>)                              │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
╭─ RECENT CONVERSATIONS ────────────────────────────────────────────────────────────────────╮
│  (no conversations yet — say something like @goose hello)                                │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
 SYNKRAKEN  │  view: dashboard  │  agents: 4  │  filter: all  │  refresh: 3s
 ›
```

The kraken sigil and SYNKRAKEN wordmark fade vertically from bright aqua at
the top (sunlit ocean surface) down through teal and navy to a deep abyssal
blue at the tentacle tips. Each agent gets a distinct color.

## Install

```bash
# 1. Clone and install (zero runtime dependencies — stdlib only)
git clone https://github.com/howardscott-dot/synkraken.git
cd synkraken
pip install -e .

# 2. Run the interactive setup — detects your installed runtimes
#    (goose, hermes, openclaw, claude), installs the bridge skill into
#    each one, and creates config.local.json from the example
synkraken config

# 3. (Optional) Edit the generated config to match your binary paths
#    — only needed if the runtimes aren't on $PATH
$EDITOR config.local.json

# 4. Start the bridge daemon (in the background)
synkraken-daemon --config ./config.local.json &

# 5. Sanity check
synkraken health
synkraken agents

# 6. Open the TUI
synkraken tui
```

That's it. The setup wizard does the boring parts for you — runtime
detection, skill installation, config bootstrap — and tells you exactly
what to do next.

## Uninstall

```bash
# Interactive — walks you through removing the bridge skill from each
# runtime, optionally clears local preferences and stored chat history,
# and tells you how to remove the Python package
synkraken uninstall
pip uninstall synkraken
```

Your `config.local.json` is never touched by the uninstall wizard — it's
your file. Delete it manually if you want it gone.

## Talking to agents

Once the TUI is open:

```text
@goose what's the most-recently-modified file in src/?
@hermes write a one-paragraph summary of the last commit
@everyone in one line: state your model and runtime
#brainstorm anyone seen issues with the new auth flow?
```

…and so on. Plain text with no `/` or `@` prefix sends to the current room
when you've entered one. `/help` inside the TUI lists every command.

## Persistent multi-agent rooms

Rooms are named, persistent groups of agents. Sending into a room fans the
message out to every member; each member's reply is automatically posted back
into the room transcript, so the conversation reads as a single flowing
thread.

```text
/room create brainstorm goose hermes openclaw-main claude
hi everyone — quick intro: who are you and what are you good at?
/room leave
```

Later:

```text
/open brainstorm
how are we splitting the work?
```

The transcript renders as chat bubbles, source-coloured per agent, with your
own messages right-aligned.

## Adapters (the runtimes you can bridge)

| Adapter id  | Type       | What it bridges to                                       | Default invocation |
|-------------|------------|----------------------------------------------------------|--------------------|
| `goose`     | `goose`    | [Goose](https://github.com/block/goose) CLI              | `goose run --text <msg> --quiet --no-session` |
| `hermes`    | `hermes`   | Hermes agent CLI                                         | `python -m hermes_cli.main -z <msg>` |
| `openclaw`  | `openclaw` | OpenClaw via local gateway                               | `openclaw agent --agent <id> --message <msg> --json` |
| `claude`    | `claude`   | [Claude Code](https://docs.claude.com/en/docs/claude-code) | `claude -p --no-session-persistence --permission-mode bypassPermissions` |

Each adapter is a leaf module under `synkraken/adapters/`, ~50–100 lines.
Adding a new one is a small focused PR — see
[`CONTRIBUTING.md`](CONTRIBUTING.md#adding-a-new-adapter).

## Architecture

```
                    ┌────────────────────────────────────────────────────┐
                    │  synkraken TUI  (curses, single-file)              │
                    │  ─ dashboard / events / chat / rooms / help        │
                    │  ─ async sends with spinner over HTTP              │
                    │  ─ live SSE event stream                           │
                    └──────────────┬─────────────────────────────────────┘
                                   │ HTTP + SSE  (127.0.0.1:9460)
                                   ▼
                    ┌────────────────────────────────────────────────────┐
                    │  synkraken-daemon  (stdlib HTTP server)            │
                    │  ─ FabricMessage dispatch + retry/backoff          │
                    │  ─ SQLite: messages, deliveries, dead-letters,     │
                    │            rooms, room_members                     │
                    │  ─ EventBus → SSE subscribers                      │
                    └──────────────┬─────────────────────────────────────┘
                                   │ subprocess.run per delivery
              ┌────────────────────┼────────────────────┬──────────────┐
              ▼                    ▼                    ▼              ▼
        ┌──────────┐         ┌──────────┐         ┌──────────┐  ┌──────────┐
        │  goose   │         │  hermes  │         │ openclaw │  │  claude  │
        │ adapter  │         │ adapter  │         │ adapter  │  │ adapter  │
        └────┬─────┘         └────┬─────┘         └────┬─────┘  └────┬─────┘
             │                    │                    │             │
             ▼                    ▼                    ▼             ▼
        ┌──────────┐         ┌──────────┐         ┌──────────┐  ┌──────────┐
        │ goose    │         │ hermes   │         │ openclaw │  │ Claude   │
        │ CLI      │         │ CLI      │         │ CLI      │  │ Code     │
        └──────────┘         └──────────┘         └──────────┘  └──────────┘
```

The daemon is small (~150 lines). Each adapter is small. SQLite gives durable
storage with zero ops. The TUI is the only fancy part, and it's still a single
Python file with no dependencies beyond `curses`.

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/health`                                       | health + adapter list                |
| GET    | `/v1/agents`                                    | configured adapters                  |
| POST   | `/v1/messages`                                  | dispatch a message (the main hammer) |
| GET    | `/v1/conversations?limit=N`                     | recent conversations                 |
| GET    | `/v1/conversations/{id}`                        | full conversation thread             |
| GET    | `/v1/deliveries?limit=N`                        | recent deliveries                    |
| GET    | `/v1/dead-letters?limit=N`                      | failed deliveries                    |
| GET    | `/v1/events/stream`                             | SSE stream of bridge events          |
| GET    | `/v1/rooms`                                     | list rooms                           |
| POST   | `/v1/rooms`                                     | create a room                        |
| GET    | `/v1/rooms/{name}`                              | fetch a room (members, metadata)     |
| DELETE | `/v1/rooms/{name}`                              | delete a room                        |
| POST   | `/v1/rooms/{name}/members`                      | add a member                         |
| DELETE | `/v1/rooms/{name}/members/{adapter_id}`         | remove a member                      |
| GET    | `/v1/rooms/{name}/messages?limit=N`             | room transcript                      |

POST `/v1/messages` body:

```json
{
  "source": "operator",
  "target": "hermes",
  "body":   "Reply with one line summarising current status."
}
```

Or target `broadcast` or `room:<name>`.

## Bridge skill (how agents call back into synkraken)

`skills/synkraken-bridge/` is a portable instruction file other agents read
to learn how to address peers via `synkraken-send` or the HTTP API. Running
`synkraken config` discovers locally-installed runtimes and copies the skill
into each one's expected skill directory (folder format for Hermes / OpenClaw /
Claude Code, single-file `.md` for Goose).

This means any participating agent can reach the others — not just you from
the TUI.

## Configuration

Two example configs ship under `examples/`:

- [`examples/config.example.json`](examples/config.example.json) — relies on
  `goose`, `hermes`, `openclaw`, `claude` being on `$PATH`. **All four
  adapters are pre-wired** with sensible defaults; just enable/disable the
  ones you have.
- [`examples/config.paths.local.example.json`](examples/config.paths.local.example.json)
  — explicit absolute paths for setups where the binaries aren't on `$PATH`.

Your active local config goes in `config.local.json` at the repo root.
That file is gitignored — it's yours, never shared.

### Adding a new agent

To add another instance of an existing adapter (e.g. a second Goose with a
different system prompt), copy one of the existing blocks in
`config.local.json` and give it a new id:

```json
"goose-research": {
  "type": "goose",
  "enabled": true,
  "command": ["goose"],
  "timeout_seconds": 120,
  "system": "You are a research-focused assistant. Cite sources."
}
```

Restart the daemon (`kill $(pgrep -f 'synkraken --config') && synkraken-daemon --config ./config.local.json &`)
and it'll appear in `synkraken agents` and the TUI's CHAT TARGETS panel.

### Adding a brand-new runtime type

If you want to bridge an AI runtime synkraken doesn't yet support, write a
new adapter — see [`CONTRIBUTING.md`](CONTRIBUTING.md#adding-a-new-adapter).
A typical adapter is 40-100 lines and a single PR.

### Daemon lifecycle

```bash
synkraken-daemon --config ./config.local.json &           # start
kill $(pgrep -f 'synkraken --config')                     # stop
# restart = stop + start
```

For production use, copy [`examples/synkraken.service`](examples/synkraken.service)
to your systemd user-units directory and `systemctl --user enable --now synkraken`.

Per-adapter config keys are documented in each adapter's source file. Common
ones:

- `timeout_seconds` — how long to wait for the subprocess
- `system` / `system_prefix` / `message_prefix` — text injected into the
  outgoing message to frame the response

## Status

This is **v0.1.0**. The HTTP API and SQLite schema are stable for this minor;
they may change before 1.0. Adapters and the TUI may grow new features.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Small focused PRs welcome.

## License

[MIT](LICENSE) © 2026 Howard Scott.

Skills, brand assets, and color palette inherit the same license unless noted
otherwise.
