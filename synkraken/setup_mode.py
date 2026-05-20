from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import termios
import tty

from .branding import NAME, print_logo
from .discovery import (
    discover_local_runtimes,
    merge_discovered_config,
    parse_runtime_selection,
)


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


def _selected_runtimes(runtimes: list[dict], raw: str, *, supported_only: bool = False) -> list[dict]:
    return parse_runtime_selection(runtimes, raw, supported_only=supported_only)


def _read_config(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    if EXAMPLE_CONFIG_PATH.exists():
        cfg = json.loads(EXAMPLE_CONFIG_PATH.read_text(encoding='utf-8'))
        cfg['adapters'] = {}
        cfg['runtime_registry'] = {}
        return cfg
    return {"adapters": {}, "runtime_registry": {}}


def _write_config(path: Path, config: dict) -> None:
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _merge_choice(default: str = 'merge') -> str:
    raw = _ask('     Config update (merge, replace, skip)', default=default).lower()
    return raw if raw in {'merge', 'replace', 'skip'} else default


def _print_runtime(runtime: dict, idx: int) -> None:
    support = 'adapter' if runtime.get('adapter_supported') else 'registry only'
    version = f"  {runtime['version']}" if runtime.get('version') else ''
    print(f"     {idx}. ✓ {runtime['label']}  ({runtime['runtime_type']}, {support}){version}")


def _config_label(runtime: dict) -> str:
    if runtime.get('runtime_id') == 'google-antigravity':
        return 'Antigravity'
    return str(runtime.get('label') or runtime.get('runtime_id') or runtime.get('id'))


def _print_discovered_checklist(runtimes: list[dict], selected_indexes: set[int] | None = None, cursor: int | None = None) -> None:
    selected_indexes = selected_indexes or set()
    print('Discovered AI workers:')
    print()
    for idx, runtime in enumerate(runtimes):
        marker = '[x]' if idx in selected_indexes else '[ ]'
        prefix = '> ' if cursor == idx else ''
        print(f'{prefix}{marker} {_config_label(runtime)}')
    print()


def _render_checklist(runtimes: list[dict], selected_indexes: set[int], cursor: int) -> None:
    print('\033[H\033[J', end='')
    _print_discovered_checklist(runtimes, selected_indexes, cursor)
    print('Select:')
    print('(space=toggle enter=confirm)')


def _interactive_selection(runtimes: list[dict]) -> list[dict] | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    selected_indexes: set[int] = set()
    cursor = 0
    original = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin)
        while True:
            _render_checklist(runtimes, selected_indexes, cursor)
            key = sys.stdin.read(1)
            if key in {'\r', '\n'}:
                break
            if key == ' ':
                if cursor in selected_indexes:
                    selected_indexes.remove(cursor)
                else:
                    selected_indexes.add(cursor)
                continue
            if key in {'j', 'J'}:
                cursor = min(len(runtimes) - 1, cursor + 1)
                continue
            if key in {'k', 'K'}:
                cursor = max(0, cursor - 1)
                continue
            if key == '\x1b':
                suffix = sys.stdin.read(2)
                if suffix == '[A':
                    cursor = max(0, cursor - 1)
                elif suffix == '[B':
                    cursor = min(len(runtimes) - 1, cursor + 1)
        _render_checklist(runtimes, selected_indexes, cursor)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original)
    print()
    return [runtime for idx, runtime in enumerate(runtimes) if idx in selected_indexes]


def _select_runtimes_for_config(runtimes: list[dict]) -> list[dict]:
    selected = _interactive_selection(runtimes)
    if selected is not None:
        return selected
    _print_discovered_checklist(runtimes)
    print('Select:')
    print('(space=toggle enter=confirm)')
    print()
    raw = _ask('Enter numbers')
    return _selected_runtimes(runtimes, raw)


def _update_config_from_selection(runtimes: list[dict], selected: list[dict], *, default_behaviour: str = 'merge', prompt_behaviour: bool = True) -> dict:
    print()
    print('Local daemon configuration')
    if not selected:
        print('     skipped — no runtimes selected for config.')
        return {"behaviour": "skip", "adapters_added": [], "adapters_replaced": [], "registry_added": []}
    behaviour = _merge_choice(default=default_behaviour) if prompt_behaviour else default_behaviour
    if behaviour == 'skip':
        print('     skipped — config not changed.')
        return {"behaviour": "skip", "adapters_added": [], "adapters_replaced": [], "registry_added": []}
    try:
        cfg = _read_config(DEFAULT_CONFIG_PATH)
        merged, summary = merge_discovered_config(cfg, selected, behaviour=behaviour)
        _write_config(DEFAULT_CONFIG_PATH, merged)
        print(f'     ✓ wrote {DEFAULT_CONFIG_PATH.name}')
        adapters = summary.get('adapters_added') or []
        replaced = summary.get('adapters_replaced') or []
        registry = summary.get('registry_added') or []
        if adapters:
            print(f'     added adapters: {", ".join(adapters)}')
        if replaced:
            print(f'     replaced adapters: {", ".join(replaced)}')
        if registry:
            print(f'     registry entries: {", ".join(registry)}')
        unsupported = [rt['runtime_id'] for rt in selected if not rt.get('adapter_supported')]
        if unsupported:
            print(f'     registry-only runtimes: {", ".join(unsupported)}')
        return summary
    except Exception as exc:  # noqa: BLE001
        print(f'     ✗ could not update config: {exc}')
        return {"behaviour": "failed", "adapters_added": [], "adapters_replaced": [], "registry_added": []}


# ── install / setup walkthrough ───────────────────────────────────────────
def run_setup(*, rediscover: bool = False) -> None:
    if not SKILL_SOURCE.exists():
        print(f'Bridge skill source not found at {SKILL_SOURCE}.')
        print('This is unusual — did the package install correctly?')
        return

    runtimes = discover_local_runtimes()
    if not runtimes:
        print('Discovered AI workers:')
        print()
        print('Total found: 0')
        return

    selected = _select_runtimes_for_config(runtimes)
    supported_selected = [runtime for runtime in selected if runtime.get('adapter_supported')]

    print()
    print('Bridge skill')
    if not supported_selected:
        print('     skipped — no skills installed.')
    else:
        for runtime in supported_selected:
            ok, msg = _install_skill_into(runtime)
            marker = '✓' if ok else '✗'
            print(f"     {marker} {runtime['label']}: {msg}")

    _update_config_from_selection(
        runtimes,
        selected,
        default_behaviour='merge',
        prompt_behaviour=rediscover,
    )

    print()
    print('Setup complete.')
    print()
    print('Next steps:')
    print(f'  1. Review {DEFAULT_CONFIG_PATH.name} if you want custom commands or')
    print('     additional agent instances — see README.md for adapter config reference.')
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
