#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${SYNKRAKEN_REPO_URL:-https://github.com/howardscott-dot/synkraken.git}"
BRANCH="${SYNKRAKEN_BRANCH:-main}"
INSTALL_HOME="${SYNKRAKEN_HOME:-$HOME/.synkraken}"
BIN_DIR="${SYNKRAKEN_BIN_DIR:-$HOME/.local/bin}"
PYTHON_BIN="${PYTHON:-python3}"
RUN_CONFIG=1
CONFIG_ARGS=()
CONFIG_ARG_COUNT=0

usage() {
  cat <<EOF
Install SynKraken into a private venv, add commands to ~/.local/bin,
then launch the interactive setup flow.

Usage:
  install.sh [options]

Options:
  --repo URL                  Git repository to install from
  --branch NAME               Git branch or tag to install
  --home DIR                  Install home, default: ~/.synkraken
  --bin-dir DIR               Command shim directory, default: ~/.local/bin
  --skip-config               Install only; do not run synkraken config
  --remote HOST               Automation only: prefill SSH worker host
  --remote-user USER          Automation only: prefill SSH username
  --remote-port PORT          Automation only: prefill SSH port
  --ssh-identity-file PATH    Automation only: prefill SSH private key
  --remote-working-dir DIR    Automation only: prefill remote worker directory
  --remote-path DIR           Automation only: extra remote PATH directory
  -h, --help                  Show this help

Examples:
  curl -fsSL https://raw.githubusercontent.com/howardscott-dot/synkraken/main/scripts/install.sh | bash
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_URL="${2:?missing value for --repo}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?missing value for --branch}"
      shift 2
      ;;
    --home)
      INSTALL_HOME="${2:?missing value for --home}"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="${2:?missing value for --bin-dir}"
      shift 2
      ;;
    --skip-config)
      RUN_CONFIG=0
      shift
      ;;
    --remote|--remote-user|--remote-port|--ssh-identity-file|--remote-working-dir|--remote-path)
      CONFIG_ARGS+=("$1" "${2:?missing value for $1}")
      CONFIG_ARG_COUNT=$((CONFIG_ARG_COUNT + 2))
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "SynKraken needs git to install from GitHub." >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "SynKraken needs Python 3.10+ on PATH as $PYTHON_BIN." >&2
  exit 1
fi

PY_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
)"

SRC_DIR="$INSTALL_HOME/src"
VENV_DIR="$INSTALL_HOME/venv"

mkdir -p "$INSTALL_HOME" "$BIN_DIR"

if [[ -d "$SRC_DIR/.git" ]]; then
  echo "Updating SynKraken in $SRC_DIR"
  git -C "$SRC_DIR" fetch --quiet origin "$BRANCH"
  git -C "$SRC_DIR" checkout --quiet "$BRANCH"
  git -C "$SRC_DIR" pull --ff-only --quiet origin "$BRANCH"
elif [[ -e "$SRC_DIR" ]]; then
  echo "Install path exists but is not a git checkout: $SRC_DIR" >&2
  exit 1
else
  echo "Installing SynKraken from $REPO_URL"
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$SRC_DIR"
fi

echo "Creating Python $PY_VERSION environment"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"$VENV_DIR/bin/pip" install -e "$SRC_DIR"

for name in synkraken synkraken-daemon synkraken-send; do
  cat > "$BIN_DIR/$name" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/$name" "\$@"
EOF
  chmod +x "$BIN_DIR/$name"
done

echo
echo "SynKraken installed."
echo "  source: $SRC_DIR"
echo "  venv:   $VENV_DIR"
echo "  bin:    $BIN_DIR"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo
    echo "Add this to your shell profile if synkraken is not found:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    export PATH="$BIN_DIR:$PATH"
    ;;
esac

if [[ "$RUN_CONFIG" -eq 1 ]]; then
  echo
  echo "Starting SynKraken setup."
  if [[ "$CONFIG_ARG_COUNT" -eq 0 ]]; then
    echo "Setup will ask whether your workers are local or on another machine over SSH."
  else
    echo "Using setup values provided on the install command line."
  fi
  if [[ -r /dev/tty ]]; then
    if [[ "$CONFIG_ARG_COUNT" -eq 0 ]]; then
      (cd "$SRC_DIR" && "$BIN_DIR/synkraken" config </dev/tty)
    else
      (cd "$SRC_DIR" && "$BIN_DIR/synkraken" config "${CONFIG_ARGS[@]}" </dev/tty)
    fi
  else
    echo "No interactive terminal found, so setup was skipped."
    echo "Run this later:"
    echo "  cd \"$SRC_DIR\" && synkraken config ${CONFIG_ARGS[*]}"
  fi
else
  echo
  echo "Next:"
  echo "  cd \"$SRC_DIR\""
  echo "  synkraken config"
fi

if [[ -f "$SRC_DIR/config.local.json" ]]; then
  echo
  echo "Installing and starting the SynKraken runtime."
  (cd "$SRC_DIR" && "$BIN_DIR/synkraken" install --config "$SRC_DIR/config.local.json")
fi
