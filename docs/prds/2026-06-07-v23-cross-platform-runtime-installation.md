# SynKraken v2.3 Cross-Platform Runtime & Installation

## Product Decision

SynKraken owns installation, startup, recovery, health validation, and service
lifecycle. Operators manage SynKraken, not operating-system service managers.

## Objective

Make SynKraken installable and operational on Linux and macOS through one
command, while defining an honest Windows service contract for future work.

## Runtime Architecture

`RuntimeService` defines install, uninstall, start, stop, restart, status, and
recovery. `LinuxRuntimeService` uses a systemd user unit.
`MacOSRuntimeService` uses `com.synkraken.daemon` as a LaunchAgent.
`FutureWindowsRuntimeService` exposes the same contract but returns an explicit
not-implemented result.

CLI, TUI, Web Command Deck, and native Console recovery delegate to this
contract. Installation succeeds only after `/health` reports healthy.

## Commands

- `synkraken install`
- `synkraken uninstall`
- `synkraken start`
- `synkraken stop`
- `synkraken restart`
- `synkraken status`
- `synkraken doctor`
- `synkraken health`

`uninstall` removes runtime integration and preserves configuration, projects,
knowledge, conversations, and SQLite data. Bridge-skill cleanup remains
available through `--remove-skills`.

## Platform Behavior

Linux installs and enables a user service with automatic restart.

macOS writes `~/Library/LaunchAgents/com.synkraken.daemon.plist`, bootstraps it
into the current GUI domain, enables it, and starts it with `kickstart`.

Windows is architecture-only in v2.3. A future implementation should use a
per-user Windows service or approved startup mechanism while preserving the
same lifecycle and health-validation contract.

## Recovery

Health, TUI, Web Command Deck, and native Console startup attempt to recover an
installed runtime before failing. Failure copy recommends `synkraken install`
or `synkraken doctor` rather than showing raw connection errors.

## Acceptance Criteria

- Linux and macOS install through `synkraken install`.
- Installation fails when health validation fails.
- Lifecycle commands contain no platform-specific operator requirements.
- Status reports platform, service state, health, uptime, and URL.
- Doctor checks Python, service, database, port, config, and providers.
- Uninstall preserves user data by default.
- Automated smoke tests execute Linux and macOS service behavior.

## Validation Plan

- `python3 scripts/cross_platform_runtime_smoke_test.py`
- `python3 -m compileall synkraken scripts`
- `npm run build --prefix apps/console`
- `cargo check --manifest-path apps/console/src-tauri/Cargo.toml`
- `python3 scripts/context_audit.py`
- `git diff --check`
