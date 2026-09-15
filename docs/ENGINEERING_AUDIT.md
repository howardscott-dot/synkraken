# SynKraken Engineering Audit — Pre-Open-Source Review

**Date:** 2026-07-04
**Scope:** Full codebase — backend daemon, HTTP/SSE API, agent fabric, runtime
adapters, storage, CLI, TUI, web command deck, retired Tauri console, Docker
(none present), configuration, logging, tests, docs, build, and DX.
**Method:** Seven parallel subsystem reviews (security, storage, fabric,
adapters, CLI/TUI, frontend, docs/DX), findings triaged by severity, then the
highest-value fixes implemented in validated batches.

---

## Executive Summary

SynKraken's core is better engineered than its scaffolding suggested. The
runtime is pure-Python-standard-library (no runtime dependencies), the data
model is auditable and consistently locked, adapters are uniformly time-bounded
and free of shell injection, and failure paths feed a real dead-letter/replay
system. The gaps that blocked an open-source release fell into three buckets:
(1) a **trust boundary** problem — an unauthenticated API that drives
permission-bypassed, code-executing AI runtimes; (2) a handful of **latent
correctness bugs** in storage and the fabric; and (3) **meta-layer untruth** —
`pyproject`, `Makefile`, `CONTRIBUTING`, and the README documented commands,
dependencies, and a test suite that did not match reality.

This pass fixed the whole security-hardening cluster that was safely
implementable without a runtime rewrite, the storage data-loss bugs, and the
entire DX/truthfulness gap, and it added a real test suite and CI. The
remaining work (a principal-bound authorization model, a background-job model
for long orchestrations, per-adapter environment scoping) is documented under
Remaining Risks — it is design work, not cleanup.

### Scorecard (0–10)

| Dimension | Before | After | Notes |
|---|---|---|---|
| **Production readiness** | 3 | 6 | Single-operator localhost: solid. Multi-user/networked: still needs authz + job model. |
| **Security** | 3 | 6.5 | Was loopback-bind-only. Now Host-validation, optional token, CSP, subprocess isolation, XSS fixed. Authz model still status-based. |
| **Code quality** | 6 | 7 | Clean idioms, but 4 god-files (storage 7.3k, tui 4.4k, fabric 4k, App.tsx 6.8k retired). |
| **Architecture** | 6 | 6.5 | Sound doctrine (everything is an auditable row). Trust + execution architecture are the two structural gaps. |
| **Maintainability** | 5 | 7 | Real tests + CI + accurate docs added; heavy duplication remains in storage/adapters. |
| **Technical debt** | 4 | 6 | Data-loss bugs paid down; god-files and duplication remain. |

---

## Critical Issues

### C1 — Unauthenticated API drives code-executing runtimes  ✅ mitigated
**Why it matters:** The daemon's purpose is to dispatch prompts to AI CLIs, some
configured with permissions bypassed (`bypassPermissions`,
`--dangerously-skip-permissions`). Any process able to reach the port could
drive them → host code execution. `actor`/`source` were caller-asserted, so
governance gates were advisory.
**Fix applied:** Optional bearer-token auth (`server.auth_token` /
`SYNKRAKEN_TOKEN`), enforced on every method with constant-time compare and
plumbed through CLI/TUI/web clients; non-loopback binds warn and require a
token. **Not fully closed:** binding actor/source to an authenticated identity
(principal-based authorization) is design work — see Remaining Risks R1.

### C2 — CSRF / DNS-rebinding via missing Host/Origin validation  ✅ fixed
**Why it matters:** The API parsed JSON regardless of `Content-Type` and never
checked `Host`, so a malicious web page in the operator's browser could POST to
`127.0.0.1` (a CORS-simple request, no preflight) and blind-fire state changes
into code-executing agents; DNS-rebinding extended this.
**Fix applied:** `Host` header is validated against a loopback allow-list on
loopback binds (daemon and web deck). Verified: spoofed Host → 403, loopback →
200.

### C3 — Broadcast amplification / runaway cost  ✅ mitigated
**Why it matters:** `max_hops` never guarded the real loop vector — `hop_count`
was not propagated through the agent→bridge→dispatch path, so an injected
"broadcast to everyone" instruction fanned out N^k, each hop spawning paid
inference subprocesses.
**Fix applied:** A global `routing.max_concurrent_dispatch` semaphore (default
8) caps total concurrent adapter executions across all nested dispatches,
bounding the blast radius regardless of hop lineage. **Not fully closed:**
lineage-based hop counting through the bridge remains — see R2.

### C4 — Adapters run runtimes with permissions bypassed on untrusted input  ⚠️ partially mitigated
**Why it matters:** Every local adapter passes a "no guardrails" flag and feeds
the untrusted message body as the prompt, so a prompt-injected message becomes
host code execution.
**Fix applied (defense-in-depth):** subprocess process-group kill on timeout
(no orphaned agents), `stdin=DEVNULL`, output size cap, terminal-control
stripping before CLI print, and an argument-injection `--` guard. **Not
closed:** defaulting to a restricted permission mode and sandboxing runtimes is
a product decision — see R3.

### C5 — Storage `INSERT OR REPLACE` cascade-deletes children / breaks FKs  ✅ fixed
**Why it matters:** `create_mission` and `create_outcome` used `INSERT OR
REPLACE` (DELETE+INSERT), which cascade-deleted all child rows (outcomes,
workers, rooms, traces, incidents, proposals) on any idempotent re-create;
`save_message` would raise a foreign-key `IntegrityError` once a message had
deliveries (retry/replay paths).
**Fix applied:** all three converted to `INSERT … ON CONFLICT DO UPDATE`.
Verified: re-creating a mission preserves outcomes and workers (1→1).

### C6 — Stored XSS in the web command deck  ✅ fixed
**Why it matters:** `esc()` escaped `<>&` but **not quotes**, and its output was
interpolated into double-quoted HTML attributes carrying untrusted agent output
(`data-task-title="${esc(message.body)}"`) — stored XSS in the operator's
browser, which proxies privileged approve/execute endpoints.
**Fix applied:** `esc()` now escapes `"` and `'`; added a strict
Content-Security-Policy plus `X-Content-Type-Options`/`X-Frame-Options`.
Verified in the served `app.js` and response headers.

---

## High Priority

| ID | Issue | Status |
|---|---|---|
| H1 | Subprocess timeout killed only the direct child; grandchildren (node/MCP) orphaned and kept spending | ✅ process-group kill on timeout |
| H2 | Full parent environment (all provider API keys) passed to every child | ⚠️ documented (R4) — blanket allow-list risks breaking runtimes untested |
| H3 | TUI crashed with a raw traceback when the daemon was unreachable (`URLError` never converted) | ✅ `URLError`→`TuiHttpError` in all TUI HTTP helpers |
| H4 | Escape-sequence injection: untrusted agent output printed raw to the terminal by the CLI | ✅ control chars stripped at CLI print sinks |
| H5 | Shared memory was a self-replicating prompt-injection channel (agent-proposed memory auto-approved by a peer agent) | ✅ `memory.auto_review` defaults off |
| H6 | No WAL / `busy_timeout`; single connection + global lock fully serialized storage | ✅ WAL + `busy_timeout=5000` + `synchronous=NORMAL` |
| H7 | TOCTOU races on approve/reject (read-check-write across lock boundaries) | ⚠️ documented (R5) — needs CAS `UPDATE … WHERE status=?` |
| H8 | Long orchestrations (team/goal/discuss) run inside the HTTP request thread; cancellation cosmetic | ⚠️ documented (R6) — needs a background-job model |
| H9 | No pruning of ~15 append-only tables; missing indexes on hot query columns | ⚠️ documented (R7) |

---

## Medium Priority

| ID | Issue | Status |
|---|---|---|
| M1 | Unbounded `limit` params (uncaught `ValueError` → 500) and unbounded request-body size (DoS) | ✅ body cap (4 MB) + `_limit_param` clamp helper |
| M2 | `find_duplicate_memory` used unescaped `LIKE` wildcards → false-positive dedup rejections | ✅ wildcards escaped with `ESCAPE '\'` |
| M3 | Verbose error leakage (`{"error": str(exc)}`) | ⚠️ partially — nosniff added; generic-error split remains |
| M4 | Argument injection: unprefixed body passed as positional CLI arg (antigravity, ollama) | ✅ antigravity `--` guard; ollama left (positional contract) — R8 |
| M5 | `config` instance-name suffixing used global `.replace(".db", …)`, corrupting paths | ✅ suffix-only rewrite |
| M6 | Daemon dumped raw tracebacks on missing/malformed config | ✅ friendly one-line errors + exit 1 |
| M7 | Confidence bug: `max(100, …)` forced confidence ≥ 100 | ✅ `max(0, min(100, …))` |
| M8 | Config secrets file world-readable; no `chmod 0600` | ⚠️ documented (R9) |
| M9 | Room-name case/quoting inconsistency between CLI `search`/`summarize` and others | ⚠️ documented (R10) |

---

## Low Priority (selected)

- Dashboard polling on the UI thread (TUI) and 4s/5s polling in the retired
  console with no visibility gating — R6-adjacent.
- Duplication: ~6 copies of adapter `_normalize_output`, ~2 of `build_env`; a
  `SubprocessAdapter` base would remove ~150–200 lines. Storage has ~450 lines
  of duplicate DDL between `SCHEMA` and `_migrate_*`, plus repeated event-store
  and `_from_row` patterns.
- Dead code: `branding._glitch_margin`, no-op `if key == 'evidence'`, `p_tui`'s
  meaningless `--json`.
- Migration strategy runs three mechanisms at once (`CREATE IF NOT EXISTS`,
  per-boot `ALTER`, versioned `schema_migrations`).

---

## Changes Made

**Security hardening (daemon + web):**
- `api.py`: `_gate()` (Host allow-list + optional constant-time bearer token) on
  every verb; body-size cap; `_limit_param` clamp; `nosniff`; `serve()` warns on
  non-loopback bind without a token; token read from config/`SYNKRAKEN_TOKEN`.
- `web.py`: `esc()` escapes quotes (XSS); CSP + security headers on all
  responses; Host validation; proxy forwards `Authorization`; non-loopback warn.
- `config.py`: validates `server.auth_token`; fixes `.db` suffix corruption.
- `__main__.py`: graceful config-error messages; passes `auth_token` to `serve`.
- CLI/TUI clients (`cli_main.py`, `cli_send.py`, `tui.py`): send
  `SYNKRAKEN_TOKEN`; TUI converts `URLError` to a normal error.

**Subprocess / adapter hardening:**
- `adapters/cli_utils.py`: `Popen` with `start_new_session`, process-group kill
  on timeout, `stdin=DEVNULL`, output cap.
- `adapters/text_normalize.py`: `strip_terminal_controls`; applied at CLI print
  sinks. `adapters/antigravity.py`: `--` end-of-options guard.

**Storage correctness:**
- `storage.py`: `create_mission`/`create_outcome`/`save_message` →
  `ON CONFLICT DO UPDATE` (no cascade delete / FK break); WAL + busy_timeout +
  synchronous=NORMAL; `find_duplicate_memory` wildcard escaping.

**Fabric:**
- `fabric.py`: global `max_concurrent_dispatch` semaphore; `memory.auto_review`
  default off; confidence clamp fix.

**DX / truthfulness / release hygiene:**
- `pyproject.toml`: removed 4 unused deps (stdlib-only), added classifiers/urls,
  dropped stray `asyncio_mode`.
- Fixed `synkraken run` → `synkraken-daemon --config` across README, Makefile,
  CONTRIBUTING; rewrote CONTRIBUTING; fixed `install-skills` in AGENTS.md.
- Standardized Python floor on 3.11 (doctor, install.sh, README, docs);
  fixed install.sh silent-death version check.
- Removed `docs/sales/*.docx` and `.monitor/baseline.json`; gitignored both.
- Merged install docs (removed `docs/INSTALL.md`).
- Added **real `tests/` pytest suite** (config, storage, adapters, API
  security), **GitHub Actions CI**, and **SECURITY.md**.
- Fixed a date-brittle and a typo'd smoke test; archived 21 retired-console
  smoke tests under `scripts/archive/console/`; registered new repo-URL
  exceptions in `context_audit.py`; relaxed a brittle timing threshold.

**Validation after every batch:** `ruff` (clean), `compileall` (pkg + scripts +
tests), `pytest tests/` (17 passed), offline smoke suite (41 passed),
`context_audit` (0 findings), and end-to-end daemon + web-deck boot with curl
checks of Host/token/body-cap/CSP.

---

## Remaining Risks (future work)

- **R1 — Principal-based authorization.** Derive `actor`/`source` from an
  authenticated identity (operator vs. agent token classes); forbid agent
  tokens from approve/execute endpoints; require approver ≠ proposer. Until
  then, approvals are advisory even with the token enabled.
- **R2 — Lineage-based loop budget.** Propagate `conversation_id`/`hop_count`
  through the agent→bridge→dispatch path and enforce hop budget server-side; the
  concurrency cap bounds blast radius but does not stop a slow amplification.
- **R3 — Runtime sandboxing.** Default to a restricted permission mode; make
  danger flags loud opt-ins; run runtimes as a low-privilege user / container.
- **R4 — Per-adapter environment scoping.** Replace `dict(os.environ)` with an
  allow-list so a runtime sees only its own key, not every provider secret. Not
  applied blindly because it can break runtimes that need specific env; needs
  per-adapter testing.
- **R5 — Compare-and-swap state transitions** to close approve/reject TOCTOU
  races (`UPDATE … WHERE status=?`, treat rowcount 0 as conflict).
- **R6 — Background-job model** for team/goal/discuss with real cooperative
  cancellation and SSE progress, instead of blocking the HTTP request thread.
- **R7 — Retention + indexes.** Prune the ~15 append-only tables; add indexes on
  `messages(timestamp/source)`, `deliveries(created_at)`, `proposals(*_by)`;
  split list-row from detail hydration to kill the mission/outcome query
  fan-out that will collapse the dashboard at scale.
- **R8 — ollama `--` guard** (left out: its positional-arg contract).
- **R9 — `chmod 0600`** on the config file (adapter env/secrets).
- **R10 — Room-name normalization helper** shared across CLI/TUI.
- **God-file decomposition:** split `storage.py`, `fabric.py`, `tui.py` along
  their existing seams; extract a `SubprocessAdapter` base; consolidate storage
  migrations on the versioned mechanism (removes ~450 lines of duplicate DDL).
- **Retired console:** `apps/console` (Tauri/React, 2.6 GB local build) is
  retired. Recommend archiving it out of the main tree to a branch/separate
  repo, leaving a pointer in `docs/CONSOLE_RETIREMENT.md`.
- **Known-brittle test:** `broadcast_fanout_smoke_test.py` uses a wall-clock
  threshold and can flake under heavy CPU contention (dispatch is a proven
  ~0.36s concurrent). Recommend re-expressing it as an overlap assertion.
- **Docs to cut for OSS:** the `*_DOCTRINE.md`, vision/positioning files, and
  `docs/prds/` (internal PRDs about a retired console) add noise; move to an
  internal repo.
