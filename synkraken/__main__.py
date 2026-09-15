from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import serve
from .config import load_config
from .fabric import AgentFabric
from .storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the synkraken local daemon")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    return parser


def main() -> None:
    import fcntl
    import sys

    parser = build_parser()
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"ERROR: config file not found: {args.config}")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {args.config}: {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"ERROR: invalid config in {args.config}: {exc}")
        sys.exit(1)
    sqlite_path = config.storage.get("sqlite_path", "./data/synkraken.db")
    sqlite_full_path = (config.path.parent / sqlite_path).resolve() if not Path(sqlite_path).is_absolute() else Path(sqlite_path)
    lock_path = sqlite_full_path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"ERROR: Another SynKraken instance is already running (lock held on {lock_path})")
        print("  Either stop the other instance or use a different instance_name in config.")
        sys.exit(1)
    storage = Storage(sqlite_full_path)
    fabric = AgentFabric(config.raw, storage)
    host = str(config.server.get("host", "127.0.0.1"))
    port = int(config.server.get("port", 9460))
    auth_token = config.server.get("auth_token") or None
    serve(fabric=fabric, host=host, port=port, auth_token=auth_token)


if __name__ == "__main__":
    main()
