from __future__ import annotations

from pathlib import Path
import shutil


def discover_local_runtimes() -> list[dict]:
    """Detect locally-installed AI runtimes that synkraken knows how to bridge.

    Discovery is intentionally conservative: a runtime is reported only when
    its CLI is on `$PATH` (for goose/claude) or when its conventional config
    directory exists under `$HOME` (for hermes/openclaw). Each entry includes
    the per-runtime `skill_path` so `synkraken config` can install the bridge
    skill into the right place for that runtime's loader.
    """
    results: list[dict] = []
    home = Path.home()

    if shutil.which('goose'):
        results.append({
            'id': 'goose',
            'label': 'Goose',
            'type': 'goose',
            'detected': True,
            # Goose uses single-file markdown skills in this directory.
            'skill_path': str(home / '.config' / 'goose' / 'skills'),
            'skill_format': 'single_file',
        })

    hermes_root = home / '.hermes'
    if hermes_root.exists():
        results.append({
            'id': 'hermes',
            'label': 'Hermes',
            'type': 'hermes',
            'detected': True,
            'skill_path': str(hermes_root / 'skills' / 'synkraken-bridge'),
        })

    openclaw_root = home / '.openclaw'
    if openclaw_root.exists():
        results.append({
            'id': 'openclaw-main',
            'label': 'OpenClaw main',
            'type': 'openclaw',
            'detected': True,
            'skill_path': str(openclaw_root / 'workspace' / 'skills' / 'synkraken-bridge'),
        })

    if shutil.which('claude'):
        results.append({
            'id': 'claude',
            'label': 'Claude Code',
            'type': 'claude',
            'detected': True,
            'skill_path': str(home / '.claude' / 'skills' / 'synkraken-bridge'),
        })

    return results
