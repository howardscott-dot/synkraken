from __future__ import annotations

from pathlib import Path
import json
import shutil

from .branding import NAME, TAGLINE, print_logo
from .discovery import discover_local_runtimes


# The bridge skill ships inside this Python package; locate it relative to
# the package install (works no matter where the user installed synkraken).
_PKG_DIR = Path(__file__).resolve().parent
SKILL_SOURCE = (_PKG_DIR.parent / 'skills' / 'synkraken-bridge')
# We look for the local config in the current working directory, which is
# the conventional place to run synkraken commands from (the repo root).
DEFAULT_CONFIG_PATH = Path.cwd() / 'config.local.json'
EXAMPLE_CONFIG_PATH = _PKG_DIR.parent / 'examples' / 'config.example.json'
PREFS_DIR = Path.home() / '.synkraken'


# ── helpers ───────────────────────────────────────────────────────────────
def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f' [{default}]' if default else ''
    try:
        answer = input(f'{prompt}{suffix}: ').strip()
    except EOFError:
        return default or ''
    return answer or (default or '')


def _confirm(prompt: str, default_yes: bool = True) -> bool:
    suffix = ' [Y/n]' if default_yes else ' [y/N]'
    raw = _ask(prompt + suffix, default='').lower()
    if not raw:
        return default_yes
    return raw[:1] == 'y'


def _copy_skill_folder(dst_dir: Path) -> None:
    """Folder-format install: SKILL.md + references/examples.md."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SOURCE / 'SKILL.md', dst_dir / 'SKILL.md')
    ref_dst = dst_dir / 'references'
    ref_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SOURCE / 'references' / 'examples.md', ref_dst / 'examples.md')


def _copy_skill_single_file(dst_dir: Path, skill_name: str = 'synkraken-bridge') -> None:
    """Goose-style install: single .md file in the skills dir."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SOURCE / 'SKILL.md', dst_dir / f'{skill_name}.md')


def _install_skill_into(runtime: dict) -> tuple[bool, str]:
    skill_path = runtime.get('skill_path')
    if not skill_path:
        return False, 'no install path known for this runtime'
    try:
        if runtime.get('skill_format') == 'single_file':
            _copy_skill_single_file(Path(skill_path))
            return True, f'installed (single file) at {skill_path}/synkraken-bridge.md'
        _copy_skill_folder(Path(skill_path))
        return True, f'installed at {skill_path}'
    except Exception as exc:  # noqa: BLE001
        return False, f'failed: {exc}'


def _uninstall_skill_from(runtime: dict) -> tuple[bool, str]:
    skill_path = runtime.get('skill_path')
    if not skill_path:
        return False, 'no skill path known'
    target = Path(skill_path)
    try:
        if runtime.get('skill_format') == 'single_file':
            single = target / 'synkraken-bridge.md'
            if single.exists():
                single.unlink()
                return True, f'removed {single}'
            return False, f'not installed at {single}'
        if target.exists():
            shutil.rmtree(target)
            return True, f'removed {target}'
        return False, f'not installed at {target}'
    except Exception as exc:  # noqa: BLE001
        return False, f'failed: {exc}'


def _selected_runtimes(runtimes: list[dict], raw: str) -> list[dict]:
    if not raw or raw.lower() == 'none':
        return []
    if raw.lower() == 'all':
        return runtimes
    selected_indexes = {
        int(x.strip()) for x in raw.split(',') if x.strip().isdigit()
    }
    return [rt for idx, rt in enumerate(runtimes, start=1) if idx in selected_indexes]


# ── install / setup walkthrough ───────────────────────────────────────────
def run_setup() -> None:
    print_logo()
    print()
    print(f'{NAME} setup walkthrough')
    print(TAGLINE)
    print()
    print('─' * 78)

    if not SKILL_SOURCE.exists():
        print(f'Bridge skill source not found at {SKILL_SOURCE}.')
        print('This is unusual — did the package install correctly?')
        return

    # ── 1. detect runtimes ────────────────────────────────────────────
    print()
    print('[1/3] Detecting installed AI runtimes…')
    runtimes = discover_local_runtimes()
    if not runtimes:
        print('     no supported runtimes found on this machine.')
        print('     install one of: goose, hermes, openclaw, claude (Claude Code),')
        print('     then re-run `synkraken config`.')
        return
    for idx, runtime in enumerate(runtimes, start=1):
        print(f"     {idx}. ✓ {runtime['label']}  ({runtime['type']})")

    # ── 2. install bridge skill ───────────────────────────────────────
    print()
    print('[2/3] Install the synkraken-bridge skill into selected runtimes')
    print('     Enter numbers separated by commas (e.g. 1,2), "all", or "none".')
    raw = _ask('     Selection', default='all')
    selected = _selected_runtimes(runtimes, raw)
    if not selected:
        print('     skipped — no skills installed.')
    else:
        for runtime in selected:
            ok, msg = _install_skill_into(runtime)
            marker = '✓' if ok else '✗'
            print(f"     {marker} {runtime['label']}: {msg}")

    # ── 3. local config ───────────────────────────────────────────────
    print()
    print('[3/3] Local daemon configuration')
    if DEFAULT_CONFIG_PATH.exists():
        try:
            cfg = json.loads(DEFAULT_CONFIG_PATH.read_text())
            adapters = list(cfg.get('adapters', {}).keys())
            print(f'     ✓ {DEFAULT_CONFIG_PATH.name} exists')
            print(f'     configured adapters: {", ".join(adapters) if adapters else "(none)"}')
        except Exception as exc:  # noqa: BLE001
            print(f'     ! {DEFAULT_CONFIG_PATH.name} exists but is unreadable ({exc})')
    else:
        print(f'     ✗ {DEFAULT_CONFIG_PATH.name} does not exist')
        if EXAMPLE_CONFIG_PATH.exists() and _confirm(
                f'     create it from {EXAMPLE_CONFIG_PATH.name}?'):
            try:
                DEFAULT_CONFIG_PATH.write_text(EXAMPLE_CONFIG_PATH.read_text())
                print(f'     ✓ created {DEFAULT_CONFIG_PATH}')
                print(f'       edit it to match your local adapter binaries:')
                print(f'         $EDITOR {DEFAULT_CONFIG_PATH.name}')
            except Exception as exc:  # noqa: BLE001
                print(f'     ✗ could not create config: {exc}')
        else:
            print(f'     to create it manually:')
            print(f'       cp {EXAMPLE_CONFIG_PATH} {DEFAULT_CONFIG_PATH.name}')

    print()
    print('─' * 78)
    print('Setup complete.')
    print()
    print('Next steps:')
    print(f'  1. (Optional) Edit {DEFAULT_CONFIG_PATH.name} to set adapter commands or')
    print('     add more agents — see README.md for adapter config reference.')
    print('  2. Start the daemon manually:')
    print(f'       synkraken-daemon --config ./{DEFAULT_CONFIG_PATH.name}')
    print('     Or install the user service:')
    print('       ./scripts/install-user-service.sh')
    print('       systemctl --user enable --now synkraken')
    print('  3. Open the TUI:')
    print('       synkraken tui')
    print()
    print('Run `synkraken uninstall` to remove the bridge skill from runtimes')
    print('and clean up. Your config.local.json and data/ are never touched.')


# ── uninstall ─────────────────────────────────────────────────────────────
def run_uninstall() -> None:
    print_logo()
    print()
    print(f'{NAME} uninstall')
    print()
    print('This will remove the synkraken-bridge skill from detected runtimes,')
    print('and optionally clear your local preferences and stored data.')
    print()
    print('─' * 78)

    runtimes = discover_local_runtimes()
    if not runtimes:
        print('No installed runtimes detected — nothing to uninstall the skill from.')
    else:
        print()
        print('Detected runtimes:')
        for idx, runtime in enumerate(runtimes, start=1):
            path = runtime.get('skill_path', '?')
            print(f'  {idx}. {runtime["label"]}  ({path})')
        print()
        print('Remove the synkraken-bridge skill from these runtimes?')
        raw = _ask('Selection (numbers, "all", or "none")', default='all')
        selected = _selected_runtimes(runtimes, raw)
        if not selected:
            print('  skipped.')
        else:
            for runtime in selected:
                ok, msg = _uninstall_skill_from(runtime)
                marker = '✓' if ok else '·'
                print(f'  {marker} {runtime["label"]}: {msg}')

    print()
    print('Local files synkraken created:')
    if PREFS_DIR.exists():
        print(f'  preferences:  {PREFS_DIR}')
        if _confirm(f'  remove {PREFS_DIR}?', default_yes=False):
            try:
                shutil.rmtree(PREFS_DIR)
                print(f'  ✓ removed {PREFS_DIR}')
            except Exception as exc:  # noqa: BLE001
                print(f'  ✗ {exc}')
    else:
        print('  preferences:  (none — never written)')

    # data/ is in the repo dir, not the home dir
    data_dir = Path.cwd() / 'data'
    if data_dir.exists():
        print(f'  data store:   {data_dir}  (conversation + room history)')
        if _confirm(f'  remove {data_dir}?', default_yes=False):
            try:
                shutil.rmtree(data_dir)
                print(f'  ✓ removed {data_dir}')
            except Exception as exc:  # noqa: BLE001
                print(f'  ✗ {exc}')
    else:
        print('  data store:   (none in cwd)')

    print()
    print('─' * 78)
    print('Uninstall walkthrough complete.')
    print()
    print('Still installed (left untouched):')
    print(f'  - config.local.json (your local adapter config)')
    print(f'  - the synkraken Python package itself')
    print()
    print('To finish removing the package:')
    print('  pip uninstall synkraken')
