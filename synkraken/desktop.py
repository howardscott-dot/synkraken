from __future__ import annotations

import fcntl
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import secrets
import signal
from threading import Thread

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.storage import Storage
from synkraken.web import CommandDeckHandler


def main() -> None:
    directory = Path(os.environ.get('SYNKRAKEN_DESKTOP_HOME',
                     str(Path.home() / 'Library/Application Support/SynKraken')))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'desktop.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        storage = Storage(directory / 'workspace.db')
        fabric = AgentFabric({'adapters': {}, 'routing': {'retry_limit': 0},
                              'engine': {'skill_roots': [str(directory / 'skills')]}}, storage)
        os.environ['SYNKRAKEN_TOKEN'] = secrets.token_urlsafe(32)

        class API(FabricRequestHandler):
            auth_token = os.environ['SYNKRAKEN_TOKEN']

        API.fabric = fabric
        api = ThreadingHTTPServer(('127.0.0.1', 0), API)
        Thread(target=api.serve_forever, daemon=True).start()

        class Web(CommandDeckHandler):
            daemon_url = f'http://127.0.0.1:{api.server_port}'

        web = ThreadingHTTPServer(('127.0.0.1', 0), Web)
        signal.signal(signal.SIGTERM, lambda *_: exit_process())
        print(f'http://127.0.0.1:{web.server_port}/', flush=True)
        try:
            web.serve_forever()
        finally:
            with fabric.bots._guard:
                for budget in fabric.bots._controls.values():
                    budget.cancelled.set()
            fabric.bots._executor.shutdown(wait=True, cancel_futures=True)
            fabric.bots.browsers.close()
            web.server_close()
            api.shutdown()
            api.server_close()


def exit_process() -> None:
    raise SystemExit(0)


if __name__ == '__main__':
    main()
