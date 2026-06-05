# Product Doctrine And Screenshots PRD

Date: 2026-06-01

## Objective

Create the canonical product doctrine document for SynKraken and complete the
screenshot documentation inventory so the project philosophy and public visual
asset plan are discoverable from the README.

## Files Affected

Expected new file:

- `docs/PRODUCT_DOCTRINE.md`
- `docs/prds/2026-06-01-product-doctrine-and-screenshots.md`

Expected modified files:

- `README.md`
- `docs/screenshots/README.md`

## Acceptance Criteria

- Product doctrine exists at `docs/PRODUCT_DOCTRINE.md`.
- Doctrine covers the ten required principles:
  - Truth Over Polish
  - Human Approval Over Autonomy
  - Visibility Over Magic
  - Replayability Over Memory
  - Relationships Over Lists
  - Workspaces Over Screens
  - Operators Over Users
  - Governance Before Scale
  - Heterogeneous Workforce
  - Local First
- Each principle explains why it exists, what behavior it encourages, and what
  behavior it discourages.
- Screenshot inventory names the expected screenshot files:
  - `canvas.png`
  - `workforce.png`
  - `rooms.png`
  - `proposal-governance.png`
  - `flight-recorder.png`
  - `incident-centre.png`
- Missing screenshots are documented as missing with capture instructions.
- README links to `docs/PRODUCT_DOCTRINE.md`.
- Runtime behavior, daemon logic, storage logic, Console behavior, and product
  features are unchanged.

## Validation Plan

Run:

```bash
python3 scripts/context_audit.py
python3 -m compileall synkraken scripts
git diff --check
```

## Out Of Scope

- Runtime behavior changes
- Daemon logic changes
- Storage logic changes
- Console functionality changes
- API changes
- Generating fake screenshots
- Committing large design exports
- Frontend builds
- New product features

## Completion Update

### Completed

- Created `docs/PRODUCT_DOCTRINE.md` as the canonical philosophical source of
  truth for SynKraken.
- Documented all ten required doctrine principles with why, encouraged
  behavior, and discouraged behavior.
- Updated `docs/screenshots/README.md` with the expected screenshot filenames,
  missing status, capture instructions, and README policy.
- Updated `README.md` to link `docs/PRODUCT_DOCTRINE.md`.
- Updated the README screenshot section to list expected screenshot paths with
  missing status instead of broken image links.

### Validation Run

- `python3 scripts/context_audit.py`: passed with the existing LICENSE
  exception.
- `python3 -m compileall synkraken scripts`: passed.
- `git diff --check`: passed.

### Known Limitations

- No screenshot PNG files are committed yet.
- Screenshot capture remains a future asset task.
- No runtime, daemon, storage, API, or Console functionality was changed.
