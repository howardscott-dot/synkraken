# Capture Console Screenshots

This is the repeatable screenshot process for SynKraken Console public docs.
It is intentionally manual and lightweight until browser or Tauri automation is
worth maintaining.

## Canonical Screenshot Set

Save screenshots under `docs/screenshots/` with these exact filenames:

| File | Console view |
|---|---|
| `canvas.png` | Spatial Operations Canvas |
| `workforce.png` | Workforce Command Centre |
| `rooms.png` | Rooms |
| `proposal-governance.png` | Proposal Governance |
| `flight-recorder.png` | Flight Recorder / Trace Explorer |
| `incident-centre.png` | Incident Centre |

## Ideal Capture Setup

- Viewport: 1440 x 1000 minimum, 1600 x 1000 preferred.
- Scale: 100 percent browser/desktop scaling when practical.
- Theme: default dark Console style.
- Data: generic demo-safe daemon state only.
- Rooms: use generic names such as `ops`, `coding`, or `research`.
- Workers: use generic adapter ids returned by the local daemon.
- Text: no private project names, local usernames, absolute paths, API keys,
  personal aliases, customer names, or proprietary room contents.

## Start Console

Start a local daemon first:

```bash
python3 -m synkraken --config ./config.local.json
```

Then open Console:

```bash
cd apps/console
npm run tauri dev
```

Or from the repo root:

```bash
npm run console:dev
```

## Per-Screenshot Guidance

### `canvas.png`

Show the Spatial Operations Canvas with several nodes visible, relationship
lines if available, top status bar, left navigation, and Canvas Inspector if a
useful node is selected.

### `workforce.png`

Show the Workforce Command Centre with the runtime table, health/trust/latency
columns, and at least one selected or inspectable runtime row if available.

### `rooms.png`

Show the Rooms screen with room list, selected room detail, members, memory or
notes, recent activity, and broadcast panel.

### `proposal-governance.png`

Show the Proposal Governance screen with pending queue or all proposals,
approval requirement, risk, proposer, and action controls visible. Use generic
proposal content.

### `flight-recorder.png`

Show the Flight Recorder / Trace Explorer with a loaded replay or trace,
summary metrics, timeline rows, and filters visible.

### `incident-centre.png`

Show the Incident Centre with failing runtime or dead-letter context, recovery
links, and trace/replay affordances visible.

## After Capture

1. Save files with exact names under `docs/screenshots/`.
2. Run:

```bash
python3 scripts/console_screenshot_check.py
python3 scripts/context_audit.py
git diff --check
```

3. Update `README.md` to embed screenshots once all expected PNG files exist.

