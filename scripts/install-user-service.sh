#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${1:-$ROOT/config.local.json}"
CONFIG_PATH="$(realpath -m "$CONFIG_PATH")"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/synkraken.service"
DAEMON_BIN="$(command -v synkraken-daemon || true)"

if [[ -z "$DAEMON_BIN" ]]; then
  cat >&2 <<MSG
synkraken-daemon was not found on PATH.

Install the package first, for example:
  pip install -e "$ROOT"
MSG
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  cat >&2 <<MSG
Config not found: $CONFIG_PATH

Create one first, for example:
  cp "$ROOT/examples/config.example.json" "$ROOT/config.local.json"

Or pass an explicit config path:
  $0 /absolute/path/to/config.json
MSG
  exit 1
fi

mkdir -p "$UNIT_DIR"
cat > "$UNIT_PATH" <<EOF_UNIT
[Unit]
Description=SynKraken local bridge daemon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$DAEMON_BIN --config $CONFIG_PATH
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF_UNIT

systemctl --user daemon-reload

cat <<MSG
Installed user service:
  $UNIT_PATH

Using config:
  $CONFIG_PATH

Next:
  systemctl --user enable --now synkraken
MSG
