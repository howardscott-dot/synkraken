# Screenshot Inventory

This directory is the public screenshot inventory for SynKraken. The primary
Console screenshots are not currently committed, so the root README uses
placeholder rows instead of broken image links.

## Canonical Screenshots

Ideal capture size: 1600 x 1000. Minimum acceptable size: 1440 x 1000. Use the
default dark Console theme, generic demo-safe daemon data, and no private
project names, local usernames, absolute paths, API keys, personal aliases,
customer names, or proprietary room contents.

| File | Screenshot | Purpose | What should be visible | Recapture when | Status |
|---|---|---|---|---|---|
| `canvas.png` | Spatial Operations Canvas | Show SynKraken's spatial operations workspace | Canvas grid, several nodes, relationship lines when available, top status, left navigation, optional inspector | Canvas layout, node model, relationship rendering, inspector, or visual style changes | missing |
| `activity.png` | Activity | Show deterministic live operations awareness | Activity summary bar, newest-first feed, runtime/room/event filters, runtime, room, event type, timestamp, and summary columns | Activity read model, filters, summary bar, or live awareness layout changes | missing |
| `workforce.png` | Workforce Command Centre | Show runtime health and reputation | Runtime table, health, trust, latency, failures, empty replies, selected/detail context if available | Workforce fields, reputation model, sorting, or table layout changes | missing |
| `rooms.png` | Rooms | Show persistent operational rooms | Room list, selected room detail, members, memory/notes, recent activity, broadcast panel | Room layout, room memory, member controls, or room transcript presentation changes | missing |
| `proposal-governance.png` | Proposal Governance | Show approval workflow | Pending/all proposals, risk, approval requirement, proposer, room/goal links, approve/reject/execute controls | Proposal lifecycle, governance controls, or proposal table/detail layout changes | missing |
| `flight-recorder.png` | Flight Recorder | Show replay and trace investigation | Replay/trace id field, summary metrics, filters, timeline rows, failure context if available | Trace/replay data model, filters, timeline layout, or naming changes | missing |
| `incident-centre.png` | Incident Centre | Show incident and recovery workflow | Failing runtimes or dead letters, incident cards, recovery hints, trace/replay links | Incident model, dead-letter recovery, runtime health, or incident layout changes | missing |

## Ideal Data State

Use a generic local daemon state with:

- at least two enabled workers
- at least one room such as `ops`
- at least one room message
- at least several live activity records across replies, proposals, approvals,
  and failures
- at least one proposal, preferably pending or recently executed
- at least one replayable trace
- at least one dead letter or degraded/failing runtime for Incident Centre
- no private project data

If a local environment cannot safely produce all states, capture the available
screens and leave missing assets uncommitted.

## Capture Process

Follow [`../../scripts/capture_console_screenshots.md`](../../scripts/capture_console_screenshots.md).

After capture, run:

```bash
python3 scripts/console_screenshot_check.py
python3 scripts/context_audit.py
git diff --check
```

## README Policy

Until all expected PNG files exist, the root README should show a placeholder
table with expected filenames and missing status. Once the PNG files are
committed, update the README to embed or link them directly.
