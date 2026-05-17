# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-17

### Added — initial public release

**Daemon and routing**

- Local HTTP daemon (`synkraken-daemon`) listening on `127.0.0.1:9460` by default.
- Stdlib-only HTTP server (`http.server.ThreadingHTTPServer`); no runtime dependencies.
- SQLite persistence for messages, deliveries, dead letters, rooms, and room members.
- Routing engine resolving `target = "<adapter>"`, `"broadcast"`, or `"room:<name>"`.
- Retry-with-backoff per delivery; failed deliveries land in a dead-letter table.
- Server-sent events stream at `/v1/events/stream` publishing
  `message.accepted`, `typing.started`, `typing.stopped`, `delivery.recorded`,
  and `dead-letter.recorded`.

**Adapters**

- `goose` — Block's Goose CLI via `goose run --text … --quiet --no-session`.
- `hermes` — Hermes agent via its Python CLI.
- `openclaw` — OpenClaw via `openclaw agent --agent <id> --message <body> --json`.
- `claude` — Anthropic Claude Code via `claude -p`. Supports OAuth or
  `ANTHROPIC_API_KEY`, with optional `--bare` and `--permission-mode` knobs.

**Rooms**

- Persistent multi-agent chat rooms (`room:<name>`).
- API CRUD: list, create, fetch, delete; add/remove members; fetch transcript.
- Each member's reply is automatically posted back into the room transcript,
  so the conversation reads as a flowing thread.

**Operator CLI and TUI**

- `synkraken health | agents | send | broadcast | recent | deliveries | dead-letters | history`.
- Curses TUI (`synkraken tui`) with:
  - SYNKRAKEN kraken sigil + wordmark with vertical ocean-fade colour
    (truecolor on terminals that support it, 256-color and 8-color fallbacks).
  - Boxed panels (dashboard, events, conversations, rooms, deadletters,
    adapters, help, chat, command-result) with rounded chrome.
  - Dashboard with three panels: BRIDGE STATUS / CHAT TARGETS,
    LATEST REPLIES (inbox), RECENT CONVERSATIONS.
  - Chat-bubble rendering for conversation and room transcripts.
  - `@goose hi`, `@hermes @claude debate this`, `@everyone …` natural mention syntax.
  - `#room hi` shorthand and Slack-style in-room mode after `/open <name>` or `/room enter`.
  - Asynchronous sends with an animated braille spinner — UI never freezes
    while a runtime takes 10+ seconds to reply.
  - Tab-completion for commands, mentions, room subcommands, targets.
  - SIGINT double-tap to quit, SSE-driven typing indicators.

**Portable bridge skill**

- `skills/synkraken-bridge/SKILL.md` is the documentation other agents read
  to learn how to participate. `synkraken config` discovers locally installed
  runtimes and copies the skill into each one's expected skill directory
  (folder format for Hermes / OpenClaw / Claude Code; single-file for Goose).

### Notes

- This is a v0.1.0 release. The HTTP API and the SQLite schema are stable for
  this minor; they may change before 1.0.
- All paths default to standard locations under `$HOME` and `$PATH`; nothing
  is hardcoded to a specific user.

[Unreleased]: https://github.com/howardscott-dot/synkraken/compare/v0.1.0...HEAD
[0.1.0]:      https://github.com/howardscott-dot/synkraken/releases/tag/v0.1.0
