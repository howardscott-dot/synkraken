from __future__ import annotations

from pathlib import Path
import json
import shutil

from .branding import LOGO, NAME, TAGLINE
from .discovery import discover_local_runtimes


SKILL_SOURCE = Path('/home/howard/agent-fabric/skills/agent-fabric-bridge')
DEFAULT_CONFIG_PATH = Path('/home/howard/agent-fabric/config.local.json')


def _copy_skill(dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SOURCE / 'SKILL.md', dst_dir / 'SKILL.md')
    ref_src = SKILL_SOURCE / 'references' / 'examples.md'
    ref_dst = dst_dir / 'references'
    ref_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ref_src, ref_dst / 'examples.md')


def run_setup() -> None:
    print(LOGO)
    print(f'{NAME} setup mode')
    print(TAGLINE)
    print()

    runtimes = discover_local_runtimes()
    if not runtimes:
        print('No supported local runtimes detected.')
        return

    print('Detected runtimes:')
    for idx, runtime in enumerate(runtimes, start=1):
        print(f"{idx}. {runtime['label']} ({runtime['type']})")
    print()
    print('Enter the numbers to enable, separated by commas. Example: 1,2,3')
    raw = input('Selection: ').strip()
    selected_indexes = {int(x.strip()) for x in raw.split(',') if x.strip().isdigit()}
    selected = [rt for idx, rt in enumerate(runtimes, start=1) if idx in selected_indexes]

    if not selected:
        print('No runtimes selected. Nothing changed.')
        return

    print()
    print('Installing bridge skill into selected runtimes...')
    for runtime in selected:
        skill_path = runtime.get('skill_path')
        if skill_path:
            _copy_skill(Path(skill_path))
            print(f"- installed skill for {runtime['label']} at {skill_path}")
        else:
            print(f"- no local skill install path for {runtime['label']}, skipped")

    if DEFAULT_CONFIG_PATH.exists():
        config = json.loads(DEFAULT_CONFIG_PATH.read_text())
    else:
        config = {'adapters': {}}

    adapter_keys = set(config.get('adapters', {}).keys())
    print()
    print('Current configured adapters:')
    for key in sorted(adapter_keys):
        print(f'- {key}')

    print()
    print('Setup complete.')
