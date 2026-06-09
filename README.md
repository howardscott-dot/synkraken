# SynKraken

Open-source AI Workforce Operating System.

SynKraken is a local-first control plane for managing heterogeneous AI workers:
Claude Code, Goose, Hermes, OpenClaw, Crush, Google Antigravity, and future
CLI runtimes. It gives operators one place to coordinate workers, govern
proposals, inspect runtime health, replay what happened, recover failures, and
operate through terminal, web, CLI, and MCP-facing surfaces without replacing
the runtimes they already use.

SynKraken is not a chatbot wrapper, an orchestration LLM, a CrewAI clone, a
cloud SaaS product, or a hidden autonomous swarm. It is an operator system for
AI work: workers may propose, humans approve, and SynKraken records the trail.

## What SynKraken Is

SynKraken runs a local daemon that owns state in SQLite and exposes HTTP/SSE
APIs to several operator surfaces: a terminal TUI, a local Web Command Deck,
the CLI, and future MCP-compliant tools. Adapters invoke external AI runtimes through
their native CLIs. The daemon records messages, deliveries, missions,
outcomes, rooms, tasks, goals, decisions, handoffs, proposals, memory events,
incidents, dead letters, and replayable traces.

## Why It Exists

One-agent chat and single-agent IDE assistants are useful, but they are not
enough for managing real AI work. Once several AI runtimes are involved, the
operator needs durable rooms, visible assignments, approval boundaries,
runtime reliability signals, failure recovery, and replayable evidence of what
happened. Terminal multiplexers show shells. Workflow tools run steps.
SynKraken manages the workforce state around AI work.

## Feature Overview

SynKraken has three primary operator surfaces:

```
CLI                → synkraken send, synkraken rooms, synkraken memory, etc.
Terminal TUI       → Interactive dashboard with panels for workforce, rooms, events
Web Command Deck   → Browser-based at http://localhost:9460 (when daemon is running)
MCP tools          → Planned standards-compliant tool surface over daemon state
```

Key capabilities in brief:
- **Workforce** — discover and monitor registered AI runtimes
- **Rooms** — persistent, searchable collaboration rooms with transcripts
- **Missions** — governance containers for structured AI work
- **Memory** — operator-approved shared memory with bounded injection
- **Flight Recorder** — replayable trace of any message run
- **Dead Letter Recovery** — retry and replay failed deliveries

## Core Capabilities

- AI workforce management across heterogeneous local runtimes
- runtime discovery and adapter-backed worker registration
- runtime reputation, trust scores, and workforce health
- mission governance containers for meaningful AI workforce outcomes
- outcome governance for desired results, evidence, confidence, and progress
- workforce assignments for visible ownership, contributors, blockers, review,
  completion, and handoffs
- persistent operational rooms with room memory and searchable transcripts
- bounded discussions, team tasks, and goal runs
- proposal approval governance for execution authority
- decision records and handoffs
- flight recorder replay, operational trace, and latest incident context
- dead letter capture, retry, and replay recovery controls
- peer-reviewed shared memory governance with bounded injection
- Shared Workforce Memory for visible, approved operator notes and scoped
  mission, outcome, assignment, room, runtime, and global context
- deterministic briefing, live activity, and operational awareness from daemon read models
- CLI, TUI, Web Command Deck, and future MCP-compliant surfaces

## Architecture

```text
Operator
  │
  ├─ CLI
  ├─ TUI
  ├─ Web Command Deck
  └─ MCP clients and tools
        │ HTTP / SSE on loopback
        ▼
SynKraken Daemon
  ├─ HTTP API and event stream
  ├─ runtime fabric and dispatch
  ├─ proposal, governance, memory, trace, incident, and recovery models
  └─ SQLite state store
        │ subprocess adapter calls
        ▼
AI workers: Claude Code, Goose, Hermes, OpenClaw, Crush, Google Antigravity,
and future runtime adapters
```

The daemon is the source of truth. Operator surfaces render daemon state and
invoke daemon APIs. SQLite is local, durable, and inspectable. Adapters stay
small leaf integrations around external runtimes.

## Quick Start

Install SynKraken with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/howardscott-dot/synkraken/main/scripts/install.sh | bash
```

The installer creates `~/.synkraken`, installs commands into `~/.local/bin`,
and launches `synkraken config`, where you choose local workers or SSH workers.

From a development checkout:

```bash
pip install -e .

# Discover runtimes without changing config.
synkraken discover
synkraken discover --json --verbose

# Interactive setup: discover runtimes, install bridge skills, create config.
synkraken config

# Install, start, and validate the runtime on Linux or macOS.
synkraken install

# Check state.
synkraken status
synkraken health
synkraken doctor
synkraken agents
synkraken workforce

# Open operator surfaces.
synkraken tui
synkraken web
```

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) for Linux, macOS, uninstall,
diagnostics, and the Windows roadmap.

Basic operator commands:

```text
synkraken send goose "summarize current status in one line"
synkraken send broadcast "status check"
synkraken memory note --title "Q2 engineering priorities" --body "Focus on API reliability and reducing deploy cycle time." --scope-type global --importance high
synkraken memory pending
synkraken memory approve <memory-id>
synkraken rooms
synkraken trace <id>
synkraken replay <id>
synkraken proposals
synkraken incident latest
synkraken retry dead-letter <id>
```

## Configuring Adapter Paths

If your AI runtimes (Goose, Claude, Hermes, etc.) are installed in non-standard
locations, copy `examples/config.paths.local.example.json` to your working
directory and pass it when starting the daemon:

```bash
synkraken run --config config.paths.local.example.json
```

Edit the `adapters.<name>.command` array to use the full path to each binary,
for example `["/home/myuser/.local/bin/goose"]` instead of `["goose"]`.

## Retired Console Prototype

The native Tauri Console in `apps/console` is retired as an active product
surface. It remains in the repository as prototype/design history only. New
operator work should target the daemon API, CLI, TUI, Web Command Deck, and
future MCP-compliant tools. See
[`docs/CONSOLE_RETIREMENT.md`](docs/CONSOLE_RETIREMENT.md).

Shared Workforce Memory is visible and governed. Approved memory can be
retrieved and injected into worker dispatches; proposed, rejected, and archived
records remain inspectable for audit. See
[`docs/WORKFORCE_MEMORY_MODEL.md`](docs/WORKFORCE_MEMORY_MODEL.md).

The Activity screen is deterministic and daemon-backed. It shows recent
runtime, room, governance, and failure events newest first, with runtime, room,
mission, outcome, assignment, and event type filters. It is an awareness
surface only; it does not schedule, plan, execute, or summarize with an AI
model.

## Missions

Mission is the primary organisational object for SynKraken v0.9. A mission is
a governance container around meaningful work, not a task, project, ticket,
schedule, or board. Missions link workers, rooms, traces, incidents,
proposals, and relationships so the operator can answer what the workforce is
doing and which outcomes are progressing.

The daemon exposes mission read models through `/v1/missions`,
`/v1/missions/summary`, and mission-scoped workers, activity, incidents, and
proposal endpoints. Console Mission Centre renders those records as an
operator cockpit beside Workforce, Rooms, Incidents, Proposals, and Traces.

## Outcomes

Outcome is the primary success object for SynKraken v1.0. Workers perform
activity, missions organise work, and outcomes measure whether the desired
result was achieved. Outcomes are linked to missions and can connect to
workers, traces, incidents, proposals, evidence, confidence, and status.

The daemon exposes outcome read models through `/v1/outcomes`,
`/v1/outcomes/summary`, mission-scoped outcomes, and outcome-scoped workers,
activity, incidents, and proposal endpoints. Console Outcome Centre is the
operator surface for seeing which results are completed, progressing, in
review, blocked, or waiting for approval.

## Assignments

Assignment is the workforce accountability object for SynKraken v1.1. An
assignment is work currently owned by one worker, with optional contributor
workers and links to a mission, outcome, and room. It is not a task, ticket,
schedule, board, or project plan.

The daemon exposes assignment read/write endpoints through `/v1/assignments`,
assignment-scoped activity, handoffs, proposals, traces, worker assignment
state, and mission/outcome/room assignment context. Console Assignment Centre
lets the operator create assignments, assign one owner, add contributors, mark
waiting or blocked, request review, complete work, and record explicit
handoffs. SynKraken does not automatically reassign, escalate, schedule, or
complete assignments.

## Governance

SynKraken's execution authority model is:

```text
Agents propose.
Humans approve.
SynKraken executes and records.
```

Workers can propose sensitive actions. Operators approve, reject, cancel, or
execute through daemon governance endpoints. In v0.1, proposal execution is
recorded as simulated execution; SynKraken does not grant workers autonomous
shell, git, file, restart, retry, replay, or delete authority.

## Flight Recorder And Trace

The Flight Recorder reconstructs work from existing durable records. Replay
and trace views show messages, deliveries, dead letters, decisions, handoffs,
tasks, goals, proposals, memory markers, runtime participation, failures, and
outcomes. The purpose is operational understanding: what happened, which
worker was involved, what failed, and what can be recovered.

## Runtime Reputation

Runtime reputation is deterministic and delivery-derived. SynKraken tracks
successful replies, empty replies, timeouts, failures, wrong identity markers,
suspicious output, proposal outcomes, average duration, trust score, and health
status. Health statuses are `healthy`, `degraded`, `unstable`, and `failing`.

These signals make weak runtime behavior visible. They do not silently disable
workers, hide failures, or replace operator judgment.

## Incident Management

Failed deliveries and dead letters become inspectable operational facts.
Operators can inspect latest incident context, open traces, retry failed
deliveries, replay dead letters, and see how incidents relate to workers,
rooms, proposals, and messages.

## Operator Surfaces

SynKraken is daemon-first. The TUI is the primary terminal operator surface.
The Web Command Deck is the browser operator surface. The CLI remains the
scriptable surface. MCP compliance is the next standards-based integration
surface. All of them call daemon APIs; none reads SQLite directly or owns a
second state model.

## Development

Runtime code is Python 3.10+ and stdlib-only.

Useful checks:

```bash
python3 scripts/smoke_test.py
python3 scripts/live_integration_test.py --skip-restart
python3 scripts/context_audit.py
python3 -m compileall synkraken scripts
```

The live integration test requires a running daemon. Individual subsystem smoke
tests live under `scripts/`.

## Roadmap

Near-term direction:

- room-scoped delivery and runtime histories
- richer TUI and Web Command Deck workflows
- MCP-compliant tool surface over daemon state
- more adapter conformance coverage
- governed execution extensions beyond the current simulated proposal execution
  model, still under explicit operator authority

## Running Multiple Instances

To run more than one SynKraken instance simultaneously, give each a unique
`instance_name` in the config:

```json
{
  "instance": {
    "instance_name": "dev",
    "organisation_name": "My Org",
    "default_workspace": ""
  }
}
```

Each instance gets its own SQLite database (`synkraken-dev.db`) and will not
conflict with other running instances. Attempting to start two instances with
the same `instance_name` will fail fast with a lock error.

```bash
synkraken run --config config-dev.json
synkraken run --config config-prod.json
```

## Documentation

- [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md)
- [`docs/PRODUCT_DOCTRINE.md`](docs/PRODUCT_DOCTRINE.md)
- [`docs/WHY_SYNKRAKEN.md`](docs/WHY_SYNKRAKEN.md)
- [`docs/CORE_CONCEPTS.md`](docs/CORE_CONCEPTS.md)
- [`docs/ASSIGNMENT_MODEL.md`](docs/ASSIGNMENT_MODEL.md)
- [`docs/GOVERNANCE_MODEL.md`](docs/GOVERNANCE_MODEL.md)
- [`docs/SPATIAL_CANVAS_MODEL.md`](docs/SPATIAL_CANVAS_MODEL.md)
- [`docs/UI_CONSOLE_DOCTRINE.md`](docs/UI_CONSOLE_DOCTRINE.md)
- [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/CONTROL_PLANE_DOCTRINE.md`](docs/CONTROL_PLANE_DOCTRINE.md)
- [`docs/WORKFORCE_MODEL.md`](docs/WORKFORCE_MODEL.md)
