from __future__ import annotations

from pathlib import Path
import shutil


def discover_local_runtimes() -> list[dict]:
    results: list[dict] = []

    goose_bin = shutil.which('goose') or '/home/howard/.local/bin/goose'
    if Path(goose_bin).exists():
        results.append({
            'id': 'goose',
            'label': 'Goose',
            'type': 'goose',
            'detected': True,
            'skill_path': None,
        })

    hermes_root = Path('/home/howard/.hermes')
    if hermes_root.exists():
        results.append({
            'id': 'hermes',
            'label': 'Hermes',
            'type': 'hermes',
            'detected': True,
            'skill_path': str(hermes_root / 'skills' / 'agent-fabric-bridge'),
        })

    openclaw_root = Path('/home/howard/.openclaw')
    if openclaw_root.exists():
        results.append({
            'id': 'openclaw-main',
            'label': 'OpenClaw main (Stanley)',
            'type': 'openclaw',
            'detected': True,
            'skill_path': str(openclaw_root / 'workspace' / 'skills' / 'agent-fabric-bridge'),
        })

    return results
