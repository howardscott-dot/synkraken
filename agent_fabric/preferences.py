from __future__ import annotations

from pathlib import Path
import json

PREFS_PATH = Path.home() / '.synkraken' / 'preferences.json'
DEFAULT_PREFS = {
    'default_view': 'dashboard',
    'event_filter': 'all',
    'refresh_seconds': 3,
    'last_target': 'hermes',
}


def load_preferences() -> dict:
    try:
        if PREFS_PATH.exists():
            data = json.loads(PREFS_PATH.read_text(encoding='utf-8'))
            prefs = DEFAULT_PREFS.copy()
            prefs.update({k: v for k, v in data.items() if k in DEFAULT_PREFS})
            return prefs
    except Exception:
        pass
    return DEFAULT_PREFS.copy()


def save_preferences(prefs: dict) -> None:
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe = DEFAULT_PREFS.copy()
    safe.update({k: v for k, v in prefs.items() if k in DEFAULT_PREFS})
    PREFS_PATH.write_text(json.dumps(safe, indent=2), encoding='utf-8')
