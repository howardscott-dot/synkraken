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
- **Visible per-agent activity rows** in chat while deliveries are queued,
  sent, thinking, replied, failed, or timed out, including one row per
  recipient for `@everyone` and room broadcasts
- **A local Web Command Deck** for room transcripts, room creation, live agent
  presence, direct messaging, broadcast, and room messaging over the same
  backend as the TUI
- **Durable Agent Presence v0.1** for inspectable operational state: online,
  idle, working, blocked, offline, disabled, last seen, current room, and
  current task
- **Room Memory v0.1** for persistent, inspectable room context: purpose,
  objective, rules, constraints, focus, and notes. It is injected concisely
  into room-scoped prompts.
- **Team Task Mode v0.1** for explicitly-invoked room teamwork: clarify,
  nominate, select an owner, execute, review, and produce a final report in
  the visible room transcript.
- **Team Governance v0.1** for inspectable team runs, approval-required mode,
  approval/rejection commands, and durable team event audit trails.
- **Durable Tasks v0.1** for the first step beyond chat: optionally linked to a
  room, assigned agent, and source message
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

# 4. Install and start the user service
./scripts/install-user-service.sh
synkraken start daemon

# 5. Sanity check
synkraken status
synkraken health
synkraken agents

# 6. Open the TUI
synkraken tui

# Or launch the local Web Command Deck
synkraken web
```

That's it. The setup wizard does the boring parts for you — runtime
detection, skill installation, config bootstrap — and tells you exactly
what to do next.

## Uninstall

```bash
# If you installed the user service, remove it first
./scripts/uninstall-user-service.sh

# Interactive — walks you through removing the bridge skill from each
# runtime, optionally clears local preferences and stored chat history,
# and tells you how to remove the Python package
synkraken uninstall
pip uninstall synkraken
```

Your `config.local.json` is never touched by either uninstall path — it's
your file. Delete it manually if you want it gone.

## Talking to agents

Once the TUI is open:

```text
@goose what's the most-recently-modified file in src/?
@hermes write a one-paragraph summary of the last commit
@everyone in one line: state your model and runtime
@everyone --global in one line: state your model and runtime
/discuss goose hermes "which adapter should own the smoke test?"
#brainstorm anyone seen issues with the new auth flow?
```

…and so on. Plain text with no `/` or `@` prefix sends to the current room
when you've entered one. Inside an entered room, `@everyone …` also targets the
current room, so the outbound message and agent replies stay in that room's
transcript. Use `@everyone --global …` when you explicitly want a fleet-wide
broadcast from inside a room. Direct mentions such as `@goose …` are also
room-associated while you are inside a room, so the outbound message and that
agent's reply stay visible in the room transcript. Use `@goose --global …` to
force a separate direct/global conversation. `/help` inside the TUI lists every
command.

While a send is active, the chat panel shows transient rows such as
`goose thinking…`, `hermes thinking…`, and `claude thinking…`. Successful rows
collapse into the actual replies as they arrive; failed or timed-out deliveries
remain visible inline instead of only appearing in the bottom status bar.

Discussion Mode is a bounded, human-started agent exchange. Use
`/discuss <agent1> <agent2> "topic"` to have SynKraken alternate turns between
agents, defaulting to four total agent messages. The final turn asks for a
recommendation instead of starting another round. If you are inside a room, the
topic, visible turn markers such as `goose turn 1`, each reply, and any failure
are stored in that room transcript. Outside a room, they are stored in a normal
conversation. Optional flags are available now:

```text
/discuss --turns 4 goose hermes "topic"
/discuss --room test1 goose hermes "topic"
```

Team Task Mode is a bounded room-only workflow. Use `/team "question or task"`
inside a room to ask all room agents to clarify the task, nominate an owner and
reviewer, let SynKraken choose the owner deterministically, collect owner work,
collect review, and write a final report back into the room. It also creates a
durable task linked to the room and assigned owner. It does not run in the
background, schedule follow-up work, or let agents work outside the visible
room transcript.

Team Governance makes each team task inspectable as a durable team run. Runs
track participants, owner, reviewers, status, final report, approval mode, and
an append-only event trail. `AUTO` mode completes after the final report.
`REVIEW_REQUIRED` mode stops at `awaiting_approval` and requires `/approve <id>`
or `/reject <id>` before the task is marked done or blocked.

If a critical Team Mode phase times out, SynKraken preserves the completed room
transcript, marks the team run and linked task `blocked`, records `timeout`,
`failed_phase`, and `run_blocked` team events, and writes a structured failure
summary into the room. Use `/team-run <id>` or `GET /v1/team-runs/{id}` to
inspect the partial run. Continuing a blocked team run with `/continue-team-run`
is future work.

Useful local TUI commands:

```text
/help      show available commands
/status    show daemon URL, daemon health, agent count, and current view/filter
/health    show the raw daemon health summary
/agents    list configured agents
/presence  list agent operational presence
/agent ID  show one agent's status and recent presence events
/rooms     list rooms
/memory    show or edit current room memory
/tasks     list recent/open tasks
/discuss   start a bounded multi-agent discussion
/team      run bounded room team task mode
/team-runs list recent team runs
/team-run  inspect one team run, including failure summary and partial transcript
/approve   approve a pending team run
/reject    reject a pending team run
/clear     clear local command output
```

Slash commands are handled by the TUI itself; unknown commands stay local and
show `Unknown command: /whatever. Type /help.` instead of being routed to an
agent or creating a dead letter.

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

Room Memory is persistent room context. Operators can store a room purpose,
objective, rules, constraints, active focus, and notes. Room broadcasts,
room-scoped direct messages, and room discussions receive a concise memory
header, capped below 500 characters, before the operator message. This is not
agent memory, RAG, embeddings, semantic search, autonomous planning, decisions,
or cloud sync.

## Live integration test

For an end-to-end check against a running local daemon, run:

```bash
python3 scripts/live_integration_test.py --skip-restart
```

The test uses the installed `synkraken` CLI plus the daemon HTTP API. It checks
presence, sends direct messages, broadcasts, room messages, a bounded
discussion when goose and hermes are available, task lifecycle updates, and a
clean fake-agent failure.
Each run writes a local audit bundle under `audits/live-test-YYYYMMDD-HHMMSS/`
with `report.md`, `raw.json`, and `commands.log`.

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
                    │  synkraken TUI + Web Command Deck                  │
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

The Web Command Deck is served separately on `127.0.0.1:9461` and proxies the
existing daemon API on `127.0.0.1:9460`, so the TUI and web UI remain peers over
one shared backend.

The project now has an explicit agent doctrine in `docs/AGENT_MODEL.md`:
configuration bootstraps agents, but once registered they are treated as
durable operational entities so future presence, handoffs, and permissions can
extend one model rather than several.

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/health`                                       | health + adapter list                |
| GET    | `/v1/agents`                                    | agents with durable presence         |
| GET    | `/v1/agents/{id}`                               | one agent presence record            |
| GET    | `/v1/agents/{id}/events`                        | recent durable agent events          |
| POST   | `/v1/messages`                                  | dispatch a message (the main hammer) |
| GET    | `/v1/conversations?limit=N`                     | recent conversations                 |
| GET    | `/v1/conversations/{id}`                        | full conversation thread             |
| GET    | `/v1/deliveries?limit=N`                        | recent deliveries                    |
| GET    | `/v1/dead-letters?limit=N`                      | failed deliveries                    |
| GET    | `/v1/events/stream`                             | SSE stream of bridge events          |
| GET    | `/v1/rooms`                                     | list rooms                           |
| POST   | `/v1/rooms`                                     | create a room                        |
| GET    | `/v1/rooms/{name}`                              | fetch a room (members, metadata)     |
| GET    | `/v1/rooms/{name}/memory`                       | fetch room memory                    |
| PUT    | `/v1/rooms/{name}/memory`                       | update room memory                   |
| GET    | `/v1/rooms/{name}/memory/events`                | room memory history                  |
| DELETE | `/v1/rooms/{name}`                              | delete a room                        |
| POST   | `/v1/rooms/{name}/members`                      | add a member                         |
| DELETE | `/v1/rooms/{name}/members/{adapter_id}`         | remove a member                      |
| GET    | `/v1/rooms/{name}/messages?limit=N`             | room transcript                      |
| POST   | `/v1/discussions`                               | run a bounded agent discussion       |
| POST   | `/v1/team-tasks`                                | run bounded room team task mode      |
| GET    | `/v1/team-runs`                                 | list recent team runs                |
| GET    | `/v1/team-runs/{id}`                            | inspect a team run and events        |
| GET    | `/v1/team-runs/{id}/events`                     | team run audit events                |
| POST   | `/v1/team-runs/{id}/approve`                    | approve an awaiting team run         |
| POST   | `/v1/team-runs/{id}/reject`                     | reject an awaiting team run          |
| GET    | `/v1/tasks`                                     | list tasks                           |
| POST   | `/v1/tasks`                                     | create a task                        |
| PATCH  | `/v1/tasks/{id}`                                | update a task                        |
| POST   | `/v1/tasks/{id}/comment`                        | append a durable task comment        |
| GET    | `/v1/tasks/{id}/events`                         | ordered durable task history         |

POST `/v1/messages` body:

```json
{
  "source": "operator",
  "target": "hermes",
  "body":   "Reply with one line summarising current status."
}
```

Or target `broadcast` or `room:<name>`.

POST `/v1/discussions` body:

```json
{
  "source": "operator",
  "agents": ["goose", "hermes"],
  "topic": "Compare two implementation approaches",
  "max_turns": 4,
  "room_name": "brainstorm"
}
```

`room_name` is optional. `max_turns` is bounded from 1 to 20; the default
operator command uses 4. SynKraken coordinates each turn and instructs agents
not to message each other directly, preventing autonomous loops outside the
visible transcript.

Tasks are durable work records, not workflow automation. A task can optionally
belong to a room, be assigned to an agent, and point back to the message that
created it. Tasks carry lightweight ownership metadata (`created_by`,
`updated_by`) and an append-only event history for auditability.

POST `/v1/team-tasks` body:

```json
{
  "source": "operator",
  "room_name": "brainstorm",
  "question": "What is the safest implementation plan?",
  "turns": 4,
  "approval_mode": "REVIEW_REQUIRED"
}
```

Team Task Mode must name a room. SynKraken writes the prompt, clarifications,
nominations, owner selection, owner output, reviews, and final report into that
room transcript. It creates a durable task, assigns the selected owner, and
records task events for nomination, assignment, review, and completion where
available. `approval_mode` is optional and defaults to `AUTO`.

Agent presence is durable operational state, not memory, decisions, scheduling,
or chain-of-thought. Presence records answer whether a configured agent is
online, idle, working, blocked, offline, or disabled; what visible task or room
it is associated with; and when SynKraken last observed activity. Presence
events record state transitions such as message receipt, reply, discussion
activity, timeout, room membership, and task assignment.

Room Memory is durable operational room context, not hidden agent memory. It is
stored in `room_memory`, audited in `memory_events`, and injected only for
room-scoped message, broadcast, and discussion prompts.

SQLite foreign-key enforcement is enabled for new connections. Existing
databases created before Tasks Hardening v0.15 automatically gain the new
ownership columns, but SQLite cannot add a new foreign key constraint to an
already-created table with `ALTER TABLE`; recreate or migrate the `tasks` table
if you need database-level `assigned_agent_id` enforcement on an older data
store.

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

For a foreground/manual run:

```bash
synkraken-daemon --config ./config.local.json
```

For normal Linux use, install the preferred **user-level systemd service** from
the repo root. The installer writes `~/.config/systemd/user/synkraken.service`
and points it at this checkout's `config.local.json` by default:

```bash
./scripts/install-user-service.sh                 # install user service
systemctl --user enable --now synkraken            # enable at login + start now
synkraken status                                   # service state + daemon health
synkraken stop daemon                              # stop via the user service
synkraken start daemon                             # start again
synkraken restart                                  # restart (short alias)
./scripts/uninstall-user-service.sh               # disable + remove service
```

If you keep config elsewhere, pass its absolute or relative path when installing:

```bash
./scripts/install-user-service.sh ~/.config/synkraken/config.json
```

The service starts when your user session starts. `examples/synkraken.service`
is also available as a manual template if you prefer to maintain the unit file
yourself.

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
