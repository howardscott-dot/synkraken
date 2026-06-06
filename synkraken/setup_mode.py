from __future__ import annotations

from getpass import getuser
from pathlib import Path
import json
import shutil

from .branding import NAME, print_logo
from .discovery import (
    RUNTIME_REGISTRY,
    SUPPORTED_ADAPTER_TYPES,
    discover_local_runtimes,
    discover_remote_runtimes,
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
BRIDGE_SKILL_INSTALLER_TYPES = {"claude", "goose", "hermes", "openclaw"}


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


def _default_ssh_identity_file() -> str:
    candidate = Path.home() / '.ssh' / 'synkraken_worker'
    if candidate.exists():
        return str(candidate)
    return str(Path.home() / '.ssh' / 'id_ed25519')


def _default_remote_working_dir(remote_user: str | None = None) -> str:
    user = remote_user or getuser()
    return f'/home/{user}/synkraken'


def _default_ssh_options(identity_file: str | None = None) -> list[str]:
    options = ['-o', 'BatchMode=yes']
    if identity_file:
        options.extend(['-o', 'IdentitiesOnly=yes'])
    return options


def _collect_discovery_options() -> dict:
    print('Worker location')
    print()
    print('1. This machine')
    print('2. Another machine over SSH')
    print()
    raw = _ask('Where are your AI workers? (1 local, 2 ssh)', default='1').strip().lower()
    if raw not in {'2', 'ssh', 'remote'}:
        return {}

    remote_host = _ask('SSH host or IP')
    if not remote_host:
        print()
        print('No SSH host entered; using local discovery.')
        return {}
    remote_user = _ask('SSH username', default=getuser())
    remote_port_raw = _ask('SSH port', default='22')
    try:
        remote_port = int(remote_port_raw)
    except ValueError:
        remote_port = 22
    ssh_identity_file = _ask('SSH private key file', default=_default_ssh_identity_file())
    remote_working_dir = _ask(
        'Remote working directory',
        default=_default_remote_working_dir(remote_user),
    )
    remote_path: list[str] = []
    while True:
        extra_path = _ask('Extra remote PATH directory (blank when done)', default='')
        if not extra_path:
            break
        remote_path.append(extra_path)
    return {
        'remote_host': remote_host,
        'remote_user': remote_user,
        'remote_port': remote_port,
        'ssh_identity_file': ssh_identity_file,
        'remote_working_dir': remote_working_dir,
        'remote_path': remote_path,
        'ssh_options': _default_ssh_options(ssh_identity_file),
    }


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


def _expected_skill_file(runtime: dict) -> Path | None:
    skill_path = runtime.get('skill_path')
    if not skill_path:
        return None
    target = Path(skill_path).expanduser()
    if runtime.get('skill_format') == 'single_file':
        return target / 'synkraken-bridge.md'
    return target / 'SKILL.md'


def _display_path(path: Path | str) -> str:
    raw = str(path)
    home = str(Path.home())
    if raw == home:
        return '~'
    if raw.startswith(home + '/'):
        return '~/' + raw[len(home) + 1:]
    return raw


def _runtime_label(runtime: dict) -> str:
    if runtime.get('runtime_id') == 'google-antigravity':
        return 'Antigravity'
    return str(runtime.get('label') or runtime.get('runtime_name') or runtime.get('runtime_id') or runtime.get('id'))


def _bridge_skip_reason(runtime: dict) -> str:
    if runtime.get('remote_host'):
        return 'remote SSH runtime; install the bridge skill on that host if the runtime needs callback instructions'
    capabilities = set(runtime.get('capabilities') or [])
    if 'local_model' in capabilities or runtime.get('runtime_id') in {'ollama', 'lm-studio'}:
        return 'local model runtime; bridge skill not applicable'
    return 'bridge skill installer not implemented for this runtime yet'


def _supports_bridge_skill_install(runtime: dict) -> bool:
    if runtime.get('remote_host'):
        return False
    adapter_type = str(runtime.get('adapter_type') or runtime.get('type') or '')
    return adapter_type in BRIDGE_SKILL_INSTALLER_TYPES and bool(runtime.get('skill_path'))


def _install_skill_into(runtime: dict) -> tuple[bool, str]:
    skill_path = runtime.get('skill_path')
    expected = _expected_skill_file(runtime)
    if not skill_path or expected is None:
        return False, 'no install path known for this runtime'
    try:
        if runtime.get('skill_format') == 'single_file':
            _copy_skill_single_file(Path(skill_path).expanduser())
        else:
            _copy_skill_folder(Path(skill_path).expanduser())
        if not expected.exists():
            return False, f'expected installed file missing at {_display_path(expected)}'
        installed_at = expected if runtime.get('skill_format') == 'single_file' else Path(skill_path).expanduser()
        return True, _display_path(installed_at)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _install_bridge_skills_for_runtimes(runtimes: list[dict]) -> list[dict]:
    results: list[dict] = []
    for runtime in runtimes:
        label = _runtime_label(runtime)
        if not _supports_bridge_skill_install(runtime):
            results.append({
                "status": "skipped",
                "label": label,
                "detail": _bridge_skip_reason(runtime),
            })
            continue
        ok, detail = _install_skill_into(runtime)
        results.append({
            "status": "installed" if ok else "failed",
            "label": label,
            "detail": detail,
        })
    return results


def _print_bridge_skill_results(results: list[dict]) -> None:
    print()
    print('Bridge skill installation:')
    print()
    if not results:
        print('- none')
        return
    for result in results:
        status = result.get('status')
        label = result.get('label')
        detail = result.get('detail')
        if status == 'installed':
            print(f'✓ {label}')
            print(f'  installed at: {detail}')
        elif status == 'failed':
            print(f'✗ {label}')
            print(f'  failed: {detail}')
        else:
            print(f'- {label}')
            print(f'  skipped: {detail}')


def _runtime_definition_by_id() -> dict[str, object]:
    return {definition.runtime_id: definition for definition in RUNTIME_REGISTRY}


def _runtime_from_config(runtime_id: str, config_item: dict, *, home: Path | None = None) -> dict:
    home = home or Path.home()
    definitions = _runtime_definition_by_id()
    definition = definitions.get(runtime_id)
    adapter_type = str(config_item.get('adapter_type') or config_item.get('type') or (definition.adapter_type if definition else 'unsupported'))
    runtime_type = str(config_item.get('runtime_type') or (definition.runtime_type if definition else adapter_type))
    label = str(config_item.get('runtime_name') or (definition.label if definition else runtime_id))
    capabilities = list(config_item.get('capabilities') or (list(definition.capabilities) if definition else []))
    runtime = {
        "id": runtime_id,
        "runtime_id": runtime_id,
        "label": label,
        "runtime_name": label,
        "type": runtime_type,
        "runtime_type": runtime_type,
        "adapter_type": adapter_type,
        "adapter_supported": adapter_type in SUPPORTED_ADAPTER_TYPES,
        "capabilities": capabilities,
    }
    if definition and definition.skill_path_template:
        runtime["skill_path"] = definition.skill_path_template.format(home=str(home))
        runtime["skill_format"] = definition.skill_format
    return runtime


def _configured_enabled_runtimes(config: dict, *, home: Path | None = None) -> list[dict]:
    home = home or Path.home()
    selected: dict[str, dict] = {}

    for runtime_id, item in (config.get('runtime_registry') or {}).items():
        if not isinstance(item, dict):
            continue
        if item.get('enabled') is False:
            selected[str(runtime_id)] = _runtime_from_config(str(runtime_id), item, home=home)

    for runtime_id, item in (config.get('adapters') or {}).items():
        if not isinstance(item, dict) or item.get('enabled') is False:
            continue
        selected[str(runtime_id)] = _runtime_from_config(str(runtime_id), item, home=home)

    for runtime_id, item in (config.get('runtime_registry') or {}).items():
        if not isinstance(item, dict) or item.get('enabled') is not True:
            continue
        selected[str(runtime_id)] = _runtime_from_config(str(runtime_id), item, home=home)

    return list(selected.values())


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
    location = f" via ssh:{runtime['remote_host']}" if runtime.get('remote_host') else ''
    print(f"     {idx}. ✓ {runtime['label']}  ({runtime['runtime_type']}, {support}){location}{version}")


def _config_label(runtime: dict) -> str:
    if runtime.get('runtime_id') == 'google-antigravity':
        label = 'Antigravity'
    else:
        label = str(runtime.get('label') or runtime.get('runtime_id') or runtime.get('id'))
    if runtime.get('remote_host'):
        return f"{label}  ssh:{runtime['remote_host']}"
    return label


def _select_runtimes_for_config(runtimes: list[dict]) -> list[dict]:
    print('Discovered AI workers:')
    print()
    for idx, runtime in enumerate(runtimes, start=1):
        print(f'{idx}. {_config_label(runtime)}')
    print()
    print('Enter numbers to enable, or press Enter for all:')
    while True:
        try:
            raw = input()
        except EOFError:
            raw = ''
        except KeyboardInterrupt as exc:
            print()
            raise SystemExit(130) from exc
        try:
            return _selected_runtimes(runtimes, raw)
        except ValueError as exc:
            print(f'Invalid selection: {exc}')


def _debug_setup_line_output() -> None:
    print('A')
    print('B')
    print('C')


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
            print(f'     enabled workers: {", ".join(adapters)}')
        if replaced:
            print(f'     updated workers: {", ".join(replaced)}')
        unsupported = [rt['runtime_id'] for rt in selected if not rt.get('adapter_supported')]
        if unsupported:
            print(f'     discovered for later: {", ".join(unsupported)}')
        return summary
    except Exception as exc:  # noqa: BLE001
        print(f'     ✗ could not update config: {exc}')
        return {"behaviour": "failed", "adapters_added": [], "adapters_replaced": [], "registry_added": []}


# ── install / setup walkthrough ───────────────────────────────────────────
def run_setup(
    *,
    rediscover: bool = False,
    remote_host: str | None = None,
    remote_user: str | None = None,
    remote_port: int | None = None,
    ssh_identity_file: str | None = None,
    remote_working_dir: str | None = None,
    remote_path: list[str] | None = None,
    ssh_options: list[str] | None = None,
    prompt_discovery: bool = False,
) -> None:
    if not SKILL_SOURCE.exists():
        print(f'Bridge skill source not found at {SKILL_SOURCE}.')
        print('This is unusual — did the package install correctly?')
        return

    if prompt_discovery and not remote_host:
        options = _collect_discovery_options()
        remote_host = options.get('remote_host')
        remote_user = options.get('remote_user')
        remote_port = options.get('remote_port')
        ssh_identity_file = options.get('ssh_identity_file')
        remote_working_dir = options.get('remote_working_dir')
        remote_path = options.get('remote_path')
        ssh_options = options.get('ssh_options')

    if remote_host:
        print(f'Discovering AI workers over SSH on {remote_host}...')
        runtimes = discover_remote_runtimes(
            remote_host=remote_host,
            remote_user=remote_user,
            remote_port=remote_port,
            ssh_identity_file=ssh_identity_file,
            remote_working_dir=remote_working_dir,
            remote_path=remote_path,
            ssh_options=ssh_options,
        )
    else:
        runtimes = discover_local_runtimes()
    if not runtimes:
        print('Discovered AI workers:')
        print()
        print('Total found: 0')
        if remote_host:
            print()
            print('No SSH runtimes were found. Check the host, user, key, and remote PATH.')
        return

    selected = _select_runtimes_for_config(runtimes)
    if remote_host:
        print()
        print('Remote workers are ready to receive work over SSH.')
    elif _confirm('Install SynKraken bridge skill into supported selected workers?', default_yes=True):
        results = _install_bridge_skills_for_runtimes(selected)
        _print_bridge_skill_results(results)
    else:
        print()
        print('Bridge skill installation skipped.')
        print('You can run `synkraken config --install-skills` later.')

    _update_config_from_selection(
        runtimes,
        selected,
        default_behaviour='merge',
        prompt_behaviour=rediscover,
    )

    print()
    print('SynKraken is ready.')
    print()
    print('Start SynKraken:')
    print(f'  synkraken-daemon --config {DEFAULT_CONFIG_PATH}')
    print()
    print('Then open another terminal and run:')
    print('  synkraken tui')
    print()
    print('You can come back later with `synkraken config --rediscover` if your workers change.')


def run_install_skills() -> None:
    if not SKILL_SOURCE.exists():
        print(f'Bridge skill source not found at {SKILL_SOURCE}.')
        print('This is unusual — did the package install correctly?')
        return
    if not DEFAULT_CONFIG_PATH.exists():
        print(f'{DEFAULT_CONFIG_PATH.name} not found.')
        print('Run `synkraken config` first, or create a local config before installing skills.')
        return
    try:
        config = _read_config(DEFAULT_CONFIG_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f'Could not read {DEFAULT_CONFIG_PATH.name}: {exc}')
        return
    runtimes = _configured_enabled_runtimes(config)
    results = _install_bridge_skills_for_runtimes(runtimes)
    _print_bridge_skill_results(results)


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
