# Installation

## Requirements

- Python 3.10 or newer
- Linux with a user systemd session, or macOS with LaunchAgents
- at least one supported AI runtime for workforce dispatch

## From A Checkout

```bash
pip install -e .
synkraken config
synkraken install
```

`synkraken install` installs the platform runtime integration, starts
SynKraken, and verifies health. It returns a failure if the runtime does not
become healthy.

## Linux

SynKraken installs a user service under the current account. Operators should
use `synkraken start`, `stop`, `restart`, and `status`; direct service-manager
commands are not required.

## macOS

SynKraken installs
`~/Library/LaunchAgents/com.synkraken.daemon.plist`. It uses the native
LaunchAgent lifecycle and starts automatically for the signed-in user.

## Windows Roadmap

The v2.3 runtime abstraction includes a Windows backend contract but no fake
service implementation. Windows install currently exits with a clear
not-implemented message. Future work must implement native lifecycle,
automatic recovery, and health validation before Windows is advertised as
supported.

## Diagnostics

```bash
synkraken status
synkraken doctor
synkraken health
```

## Uninstall

```bash
synkraken uninstall
```

This removes service integration and preserves configuration, projects,
knowledge, conversations, and database files. Use `--remove-skills` only when
bridge skills should also be removed interactively.
