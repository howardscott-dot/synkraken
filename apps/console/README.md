# SynKraken Console

SynKraken Console v0.2 is a Tauri desktop client for the local SynKraken daemon.
It does not own state, mutate SQLite, or replace the CLI, TUI, or Web Command
Deck. It talks to the daemon HTTP API at `http://127.0.0.1:9460` by default.

Console v0.2 is organized around operator workflows:

- Workforce Command Centre
- Rooms
- Flight Recorder
- Proposal Governance
- Incident Centre
- Global status bar and command palette

## Run

Start the daemon separately, then run:

```bash
cd apps/console
npm install
npm run tauri dev
```

From the repo root:

```bash
npm run console:dev
```

## Build

```bash
cd apps/console
npm run build
npm run tauri build
```

The frontend-only build validates TypeScript and Vite output. The Tauri build
also requires local Rust and system WebView build dependencies.

## Daemon API

Console v0.2 consumes:

- `GET /health`
- `GET /v1/agents`
- `GET /v1/workforce`
- `GET /v1/workforce/health`
- `GET /v1/rooms`
- `GET /v1/rooms/{name}`
- `GET /v1/rooms/{name}/messages`
- `GET /v1/rooms/{name}/memory`
- `POST /v1/rooms/{name}/members`
- `DELETE /v1/rooms/{name}/members/{adapter_id}`
- `POST /v1/messages`
- `GET /v1/proposals`
- `GET /v1/proposals/pending`
- `GET /v1/proposal/{id}`
- `POST /v1/proposal/approve`
- `POST /v1/proposal/reject`
- `POST /v1/proposal/execute`
- `GET /v1/replay/{id}`
- `GET /v1/trace/{id}`
- `GET /v1/incident/latest`
- `GET /v1/dead-letters?limit=N`

Set `VITE_SYNKRAKEN_DAEMON_URL` to point the frontend at a different daemon
URL during development.

## v0.2 Limitations

- no auth
- no settings persistence
- no packaged release automation
- no memory governance UI
- no goal or team task UI
- no native notifications
- proposal controls call existing daemon governance endpoints only
- live updates use polling rather than SSE
