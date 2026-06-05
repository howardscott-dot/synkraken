# Screenshot And GitHub Visualisation PRD

Date: 2026-06-01

## Objective

Create a repeatable screenshot capture process for SynKraken Console and make
the README screenshot section GitHub-ready without introducing broken image
links or fake visual assets.

## Files Affected

Expected new files:

- `docs/prds/2026-06-01-screenshot-and-github-visualisation.md`
- `scripts/capture_console_screenshots.md`
- `scripts/console_screenshot_check.py`

Expected modified files:

- `README.md`
- `docs/screenshots/README.md`

## Acceptance Criteria

- Canonical screenshot set is documented:
  - Spatial Operations Canvas
  - Workforce Command Centre
  - Rooms
  - Proposal Governance
  - Flight Recorder
  - Incident Centre
- Screenshot documentation defines ideal screen size, layout, data state, and
  capture guidance.
- README screenshot section has no broken image links.
- If screenshot files are missing, README shows clearly labelled placeholders
  and expected filenames.
- Lightweight screenshot existence check is available through
  `scripts/console_screenshot_check.py`.
- No runtime behavior, daemon behavior, governance logic, Console
  functionality, or product features are changed.

## Validation Plan

Run:

```bash
python3 scripts/context_audit.py
python3 -m compileall synkraken scripts
git diff --check
```

Also run:

```bash
python3 scripts/console_screenshot_check.py
```

The screenshot check is expected to report missing screenshots until PNG files
are captured and committed.

## Out Of Scope

- Browser automation
- Tauri automation
- Screenshot generation
- Fake screenshots or placeholder images
- Runtime, daemon, storage, API, governance, or Console behavior changes
- Frontend builds
- Large design exports

## Completion Update

### Completed

- Documented the canonical Console screenshot strategy in
  `docs/screenshots/README.md`.
- Added manual capture instructions in `scripts/capture_console_screenshots.md`.
- Added lightweight screenshot existence check in
  `scripts/console_screenshot_check.py`.
- Updated the README screenshot section to appear before Core Capabilities and
  show clear missing placeholders with expected filenames.
- Avoided broken image links because the PNG files are not committed yet.

### Validation Run

- `python3 scripts/console_screenshot_check.py`: reports the six expected
  missing screenshot files.
- `python3 scripts/context_audit.py`: passed with the existing LICENSE
  exception.
- `python3 -m compileall synkraken scripts`: passed.
- `git diff --check`: passed.

### Known Limitations

- No screenshots were captured in this sprint.
- Screenshot automation remains manual by design.
- README should be updated to embed images after all canonical PNG files are
  captured and committed.
