# AGENTS.md — Working in SynKraken

## What this project is

SynKraken is a local-first, runtime-neutral **AI workforce control plane** that lets heterogeneous AI CLI runtimes (Claude Code, Goose, Hermes, OpenClaw, etc.) communicate via directed messages, broadcasts, and persistent multi-agent chat rooms.

The daemon (`synkraken-daemon`) owns all state: SQLite persistence, message routing, event bus, agent orchestration. The TUI and Web Command Deck are clients over HTTP + SSE. The bridge skill (`skills/synkraken-bridge/`) is read by participating agents so they can call back into SynKraken.

**It is not a coding agent, orchestration LLM, or CrewAI clone.** The architectural doctrine is documented in `docs/`.

---

## Essential Commands

### Development

```bash
# Install in editable mode (zero runtime dependencies)
pip install -e .

# Run the daemon directly (requires --config)
python3 -m synkraken --config ./config.local.json
synkraken-daemon --config ./config.local.json

# TUI (requires running daemon)
synkraken tui

# Web Command Deck (separate process, proxies daemon API)
synkraken web

# Smoke test (requires running daemon)
python3 scripts/smoke_test.py

# Live integration test (requires running daemon)
python3 scripts/live_integration_test.py --skip-restart

# Context audit — catches private names, personal aliases, local paths
python3 scripts/context_audit.py
```

### Lifecycle (requires systemd user service)

```bash
./scripts/install-user-service.sh
systemctl --user enable --now synkraken
synkraken status
synkraken start daemon
synkraken stop daemon
synkraken restart          # alias for restart daemon
./scripts/uninstall-user-service.sh
```

### Setup

```bash
synkraken config           # interactive: discover runtimes, install bridge skills, create config.local.json
synkraken config --rediscover  # re-scan and merge/replace/skip
synkraken discover          # show detected runtimes without changing config
synkraken discover --json --verbose  # full details
synkraken install-skills    # install bridge skill into configured runtimes only
synkraken uninstall        # interactive removal of skills + cleanup
```

### Operator CLI

```bash
synkraken health           # daemon health + adapter list
synkraken agents           # registered adapters with status
synkraken send <target> "message"   # send through the bridge
synkraken send hermes "hi"
synkraken send broadcast "status check"
synkraken runtimes         # runtime registry entries
synkraken runtime doctor   # runtime diagnostics
synkraken recent           # recent conversations
synkraken deliveries       # recent deliveries
synkraken dead-letters     # failed deliveries
```

---

## Architecture

### Components

```
synkraken/
  __main__.py          daemon entry point (python -m synkraken)
  cli_main.py          operator CLI (synkraken command)
  api.py               HTTP request handler + SSE stream
  fabric.py            AgentFabric: routing, dispatch, retry, team/goal orchestration
  storage.py           SQLite persistence layer
  router.py            target resolution (direct / broadcast / room:)
  models.py            FabricMessage, AdapterReply dataclasses
  discovery.py         local runtime detection + config merge
  config.py            JSON config validation
  tui.py               curses TUI client
  web.py               web Command Deck server
  adapters/
    base.py            BaseAdapter abstract class
    __init__.py        ADAPTER_TYPES registry + build_adapter factory
    goose.py           GooseAdapter
    claude.py          ClaudeAdapter
    hermes.py          HermesAdapter
    openclaw.py        OpenClawAdapter
    antigravity.py      Google AntigravityAdapter
    cli_utils.py       shared subprocess runner
    text_normalize.py  output cleaning utilities
```

### Daemon ports

- `127.0.0.1:9460` — daemon HTTP API + SSE event stream
- `127.0.0.1:9461` — Web Command Deck (proxies daemon at 9460)

### Key data model

`FabricMessage` is the core transport object: `source`, `target`, `body`, `conversation_id`, `message_id`, `reply_to`, `hop_count`, `metadata`.

`AdapterReply` is the per-delivery result: `ok`, `body`, `error`, `duration_ms`, `external_reference`, `raw`.

SQLite is the authoritative store. Schema is defined in `storage.py` `SCHEMA` constant. All connections use `PRAGMA foreign_keys = ON`. The `Storage` class uses a `threading.Lock` and `check_same_thread=False` for thread-safe access from the threading HTTP server.

---

## Code Conventions

### Python style

- Python 3.10+
- `from __future__ import annotations` in every module
- Type hints encouraged but not enforced
- **No runtime dependencies** — stdlib only (except no framework deps)
- **No `# noqa`, no comments** unless explaining non-obvious intent (never communicate through code comments)
- Dataclasses with `slots=True` for models (`models.py`)
- Composition over factory abstraction

### Adapter pattern

Each adapter extends `BaseAdapter` (abstract) with a `send(message: FabricMessage) -> AdapterReply` method. Adapters are instantiated via `build_adapter(adapter_id, config)` which looks up the type in `ADAPTER_TYPES` dict.

**All adapters use `cli_utils.run_command`** for subprocess execution — never `subprocess.run` directly in adapter code.

Output normalization pattern: strip tool chatter, blank lines, status messages; prefer terminal ALLCAPS marker lines.

### Dataclass conventions

`FabricMessage.normalized()` populates `conversation_id` from `message_id` if unset — always call it before dispatch. The `AgentFabric` always uses normalized messages.

### Config validation

`config.py` validates and sets defaults for server, storage, routing, memory, goal, and adapters. Never modify config in place without going through `load_config`.

### Routing targets

- `goose` — direct to adapter `goose`
- `broadcast` — all agents except source
- `room:<name>` — members of named room (resolved via `storage.get_room_members`)

### Event bus

`EventBus` in `fabric.py` is a thread-safe pub/sub over `queue.Queue`. SSE subscribers poll with 15-second timeouts and send ping comments to keep connections alive. `api.py` `_stream_events` handles the SSE protocol.

---

## Critical Gotchas

1. **`conversation_id` is not auto-assigned until `.normalized()` is called.** `FabricMessage.__post_init__` does NOT set it — always call `.normalized()` before using or storing a message.

2. **`Storage` uses a single shared `sqlite3.Connection` with `check_same_thread=False`.** All mutations go through `with self._lock` to avoid corruption. Read methods also use the lock for consistency.

3. **`api.py` has no `do_DELETE` for rooms — only `DELETE /v1/rooms/{name}`** (removes room entirely). Member removal uses `DELETE /v1/rooms/{name}/members/{adapter_id}`.

4. **Room names are lowercased on write** (`api.py` POST `/v1/rooms` does `name = str(payload.get("name", "")).strip().lower()`). The regex validation is `^[a-z0-9][a-z0-9_-]{0,62}$`.

5. **`agent_events`, `task_events`, `team_events`, `goal_events`, `memory_events` are all append-only audit trails.** No updates or deletes. Use them for traceability but not for current-state queries.

6. **`agents` table uses `preferred_roles_json` and `capabilities_json`** as column names — JSON-serialized. Use `Storage.list_agents()` / `Storage.get_agent()` which deserialize these automatically.

7. **Adapters can raise `TimeoutError`** (or anything) from `send()`. `AgentFabric._adapter_exception_reply` catches all exceptions and converts them to failed `AdapterReply` objects with status `timeout` or `failed` depending on whether the word "timeout" appears in the error message.

8. **SSE keepalive**: The `_stream_events` method sends `': ping\n\n'` comments every 15 seconds. Clients that don't handle comment lines may misparse the stream.

9. **`cli_utils.run_command`** captures stdout/stderr separately. Stderr is NOT appended to stdout in normal operation — adapters that want to surface stderr do so explicitly in their `AdapterReply.body` fallback (e.g., goose adapter uses stderr when stdout is empty).

10. **`synkraken-send`** is a separate CLI entry point (`synkraken/cli_send.py`) used by the bridge skill. It is distinct from `synkraken` (cli_main.py) and `synkraken-daemon` (__main__.py).

11. **Memory injection is bounded**: Shared Memory is only injected for `peer_approved` entries within `max_items_injected` and `max_chars_injected` budgets. Room memory is capped at 485 characters. These limits are enforced at dispatch time, not at proposal time.

12. **Goal Mode and Team Task Mode are synchronous** — they block the calling thread until all phases complete. In a production setup with `ThreadingHTTPServer`, this means concurrent goal/team runs can run in parallel across threads, but a single run blocks its thread.

13. **SQLite migrations use `ALTER TABLE ... ADD COLUMN`** for additive changes. The `_migrate_schema` method handles old databases gracefully. Foreign key constraints cannot be added to existing tables with `ALTER TABLE`.

14. **`goal_runs.reviewers` and `goal_runs.participants`** are stored as JSON text in the DB (not normalized) — parsed at read time in `_goal_run_from_row`.

15. **`SHARED_MEMORY_TYPES`** in `storage.py` (`fact`, `decision`, `preference`, `rule`, `lesson`, `technical_note`, `project_context`) are the authoritative list. Proposals with unknown types are rejected.

16. **`config.local.json` is gitignored.** `examples/config.example.json` and `examples/config.paths.local.example.json` are the shipped reference configs.

17. **When editing `api.py`**: route matching is order-sensitive. More specific routes (e.g., `/v1/rooms/{name}/messages`) must come before generic parameterized routes (e.g., `/v1/rooms/{name}`). All path params use `re.fullmatch` with `unquote` for URL-decoding.

---

## Testing Approach

There is no pytest or test framework. Tests are smoke tests:

- `scripts/smoke_test.py` — minimal sanity check (health + agents + broadcast), run before opening a PR
- `scripts/live_integration_test.py` — full integration test against a running daemon; writes audit bundles to `audits/live-test-YYYYMMDD-HHMMSS/`
- Individual `scripts/*_smoke_test.py` files test specific subsystems (discussion, team, goal, memory, room routing, presence, etc.)

The release checklist in `docs/DEVELOPMENT.md` requires running both smoke_test.py and live_integration_test.py.

`scripts/context_audit.py` checks for private names, personal aliases, local paths, and installation-specific context before publishing.

---

## File naming and structure

- **Single-file modules** preferred for focused utilities (e.g., `router.py`, `models.py`, `config.py`)
- **`adapters/`** contains one file per runtime adapter
- **`docs/`** contains doctrine documents (must be read before changing architecture, roles, governance, memory, or positioning)
- **`examples/`** contains generic, publish-safe config examples
- **`skills/synkraken-bridge/`** is the portable instruction file installed into other runtimes
- **`scripts/`** contains operational scripts and smoke tests
- **`[ `** (a file named `[`) is NOT a config file — it's a workspace marker or placeholder from the original repo scaffold, not meaningful to the project

---

## Key entry points

| Command | Invokes |
|---------|---------|
| `synkraken` | `cli_main.py:main()` |
| `synkraken-daemon` | `__main__.py:main()` (via `python -m synkraken`) |
| `synkraken-send` | `cli_send.py:main()` |
| `python -m synkraken` | `__main__.py:main()` |

The TUI (`tui.py`) and Web Deck (`web.py`) are separate client processes — they do NOT import from the daemon modules.

---

## Config schema (summary)

Top-level keys: `server` (host/port), `storage` (sqlite_path), `adapters` (runtime configs), `runtime_registry` (discovered-but-unsupported runtimes), `routing` (max_hops, timeouts, retry), `memory` (injection limits), `goal` (round/threshold defaults), `instance` (name/org/workspace).

Adapter config keys per runtime: `type`, `command` (argv list), `timeout_seconds`, `system`/`system_prefix`/`message_prefix` (prompt framing), `capabilities`, `cost_tier`, `supported_modes`, `enabled`. Adapter-specific keys (e.g., `bare`, `permission_mode` for Claude; `agent_id` for OpenClaw) are documented in each adapter's source docstring.

---

## Adding a new adapter

1. Create `synkraken/adapters/<my_runtime>.py` with `MyRuntimeAdapter(BaseAdapter)` and `send() -> AdapterReply`
2. Import and register in `synkraken/adapters/__init__.py` (`ADAPTER_TYPES` dict + `build_adapter`)
3. (Optional) Add detection to `discovery.py` (`RUNTIME_REGISTRY` tuple + `runtime_to_adapter_config`)
4. (Optional) Add color pair in `tui.py` (`_AGENT_COLOR_PAIRS`)
5. (Optional) Update `skills/synkraken-bridge/SKILL.md`
6. Smoke test: `scripts/smoke_test.py`

Typical adapter is 40–100 lines. Reuse `cli_utils.run_command`. See `CONTRIBUTING.md` for the full checklist.
