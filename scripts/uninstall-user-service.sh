#!/usr/bin/env bash
set -euo pipefail

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/synkraken.service"

systemctl --user disable --now synkraken.service >/dev/null 2>&1 || true
rm -f "$UNIT_PATH"
systemctl --user daemon-reload
systemctl --user reset-failed synkraken.service >/dev/null 2>&1 || true

cat <<MSG
Removed user service:
  $UNIT_PATH
MSG
