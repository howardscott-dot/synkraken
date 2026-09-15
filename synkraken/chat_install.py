from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

from .config import load_config


def prepare_config(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as handle:
            json.dump({'server': {'host': '127.0.0.1', 'port': 9460},
                       'storage': {'sqlite_path': str(path.parent / 'data' / 'synkraken.db')},
                       'adapters': {}}, handle, indent=2)
    load_config(path)
    return path


def open_setup(daemon_url: str, directory: Path) -> None:
    url = 'http://127.0.0.1:9461/'
    try:
        with urlopen(url, timeout=1) as response:
            if b'<title>SynKraken' not in response.read(4096):
                raise ValueError('Port 9461 belongs to another application')
    except OSError:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'web.log').open('ab') as log:
            process = subprocess.Popen([sys.executable, '-m', 'synkraken.web', '--host', '127.0.0.1',
                '--port', '9461', '--daemon-url', daemon_url], stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
        for _ in range(20):
            if process.poll() is not None:
                raise ValueError('The chat workspace did not start; check web.log')
            try:
                with urlopen(url, timeout=.5) as response:
                    if b'<title>SynKraken' in response.read(4096):
                        break
            except OSError:
                time.sleep(.1)
        else:
            raise ValueError('Chat setup is not reachable yet. Run synkraken web')
    print('Choose your default model and sign in in the setup conversation: ' + url)
    webbrowser.open(url)
