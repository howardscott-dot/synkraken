from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Iterable

try:
    import termios
except ImportError:  # pragma: no cover - termios is POSIX-only.
    termios = None


SUPPORTED_ADAPTER_TYPES = {"claude", "crush", "goose", "hermes", "openclaw", "google_antigravity"}
DEFAULT_SUPPORTED_MODES = ["direct", "broadcast", "room", "discussion", "team", "goal"]


@dataclass(frozen=True)
class RuntimeDefinition:
    runtime_id: str
    label: str
    runtime_type: str
    command_names: tuple[str, ...]
    capabilities: tuple[str, ...]
    cost_tier: str
    adapter_type: str
    supported_modes: tuple[str, ...]
    usage_risk: str = "medium"
    preferred_roles: tuple[str, ...] = ()
    avoid_roles: tuple[str, ...] = ()
    default_timeout_seconds: int = 120
    safe_version_args: tuple[str, ...] = ("--version",)
    safe_probe_args: tuple[tuple[str, ...], ...] = ()
    verified_command_names: tuple[str, ...] = ()
    verification_keywords: tuple[str, ...] = ()
    config_markers: tuple[str, ...] = ()
    skill_format: str = "folder"
    skill_path_template: str | None = None


RUNTIME_REGISTRY: tuple[RuntimeDefinition, ...] = (
    RuntimeDefinition(
        runtime_id="claude",
        label="Claude Code",
        runtime_type="claude",
        command_names=("claude",),
        capabilities=("coding", "review", "files", "shell"),
        cost_tier="premium",
        adapter_type="claude",
        supported_modes=tuple(DEFAULT_SUPPORTED_MODES),
        skill_path_template="{home}/.claude/skills/synkraken-bridge",
    ),
    RuntimeDefinition(
        runtime_id="codex",
        label="Codex",
        runtime_type="codex",
        command_names=("codex",),
        capabilities=("coding", "review", "files", "shell"),
        cost_tier="premium",
        adapter_type="unsupported",
        supported_modes=("direct",),
        skill_path_template="{home}/.codex/skills/synkraken-bridge",
    ),
    RuntimeDefinition(
        runtime_id="gemini",
        label="Gemini CLI",
        runtime_type="gemini",
        command_names=("gemini",),
        capabilities=("coding", "research", "review"),
        cost_tier="premium",
        adapter_type="unsupported",
        supported_modes=("direct",),
    ),
    RuntimeDefinition(
        runtime_id="goose",
        label="Goose",
        runtime_type="goose",
        command_names=("goose",),
        capabilities=("coding", "review", "files", "shell"),
        cost_tier="medium",
        adapter_type="goose",
        supported_modes=tuple(DEFAULT_SUPPORTED_MODES),
        default_timeout_seconds=90,
        skill_format="single_file",
        skill_path_template="{home}/.config/goose/skills",
    ),
    RuntimeDefinition(
        runtime_id="hermes",
        label="Hermes",
        runtime_type="hermes",
        command_names=("hermes",),
        capabilities=("coding", "review", "files", "shell"),
        cost_tier="medium",
        adapter_type="hermes",
        supported_modes=tuple(DEFAULT_SUPPORTED_MODES),
        config_markers=("{home}/.hermes",),
        skill_path_template="{home}/.hermes/skills/synkraken-bridge",
    ),
    RuntimeDefinition(
        runtime_id="openclaw-main",
        label="OpenClaw",
        runtime_type="openclaw",
        command_names=("openclaw",),
        capabilities=("coding", "review", "files", "shell"),
        cost_tier="medium",
        adapter_type="openclaw",
        supported_modes=tuple(DEFAULT_SUPPORTED_MODES),
        config_markers=("{home}/.openclaw",),
        skill_path_template="{home}/.openclaw/workspace/skills/synkraken-bridge",
    ),
    RuntimeDefinition(
        runtime_id="crush",
        label="Crush",
        runtime_type="crush",
        command_names=("crush",),
        capabilities=("coding", "review"),
        cost_tier="local",
        adapter_type="crush",
        supported_modes=tuple(DEFAULT_SUPPORTED_MODES),
        default_timeout_seconds=90,
    ),
    RuntimeDefinition(
        runtime_id="aider",
        label="Aider",
        runtime_type="aider",
        command_names=("aider",),
        capabilities=("coding", "files"),
        cost_tier="medium",
        adapter_type="unsupported",
        supported_modes=("direct",),
        usage_risk="high",
    ),
    RuntimeDefinition(
        runtime_id="google-antigravity",
        label="Google Antigravity",
        runtime_type="google_antigravity",
        command_names=(
            "agy",
            "antigravity",
            "antigravity-cli",
            "google-antigravity",
            "google-antigravity-cli",
            "ag",
        ),
        capabilities=("coding", "review", "files", "shell"),
        cost_tier="premium",
        adapter_type="google_antigravity",
        supported_modes=("direct",),
        safe_probe_args=(("--version",), ("version",), ("--help",)),
        verified_command_names=("agy",),
        verification_keywords=("antigravity", "google antigravity"),
    ),
    RuntimeDefinition(
        runtime_id="ollama",
        label="Ollama",
        runtime_type="ollama",
        command_names=("ollama",),
        capabilities=("local_model", "chat"),
        cost_tier="local",
        adapter_type="unsupported",
        supported_modes=("direct",),
    ),
    RuntimeDefinition(
        runtime_id="lm-studio",
        label="LM Studio",
        runtime_type="lm_studio",
        command_names=("lms", "lmstudio"),
        capabilities=("local_model", "chat", "local_server"),
        cost_tier="local",
        adapter_type="unsupported",
        supported_modes=("direct",),
        config_markers=("{home}/.lmstudio",),
    ),
)


def _common_binary_dirs(home: Path) -> list[Path]:
    return [
        home / ".local" / "bin",
        home / "bin",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/bin"),
        Path("/bin"),
    ]


def _nvm_node_bin_dirs(home: Path) -> list[Path]:
    versions_dir = home / ".nvm" / "versions" / "node"
    if not versions_dir.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    try:
        for version_link in versions_dir.iterdir():
            bin_dir = version_link / "bin"
            if bin_dir.is_dir():
                try:
                    weight = tuple(int(x) for x in version_link.name.lstrip("v").split(".")[:3])
                    found.append((weight, bin_dir))
                except ValueError:
                    found.append(((0, 0, 0), bin_dir))
    except OSError:
        return []
    found.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in found]


def _remote_binary_dir_words(extra_path: Iterable[str] | None = None) -> list[str]:
    words: list[str] = []
    for item in extra_path or []:
        cleaned = str(item).strip()
        if cleaned:
            words.append(shlex.quote(cleaned))
    words.extend([
        "$HOME/.local/bin",
        "$HOME/bin",
        "$HOME/.npm-global/bin",
        "$HOME/.nvm/versions/node/" + "*/bin",
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
        "/snap/bin",
    ])
    deduped: list[str] = []
    for word in words:
        if word not in deduped:
            deduped.append(word)
    return deduped


def _find_node_bin(search_path: str | None, extra_dirs: list[Path]) -> tuple[str | None, str | None]:
    node_path = shutil.which("node", path=search_path)
    if node_path:
        return node_path, str(Path(node_path).parent)
    for d in extra_dirs:
        node_candidate = d / "node"
        if node_candidate.is_file() and os.access(node_candidate, os.X_OK):
            return str(node_candidate), str(d)
    return None, None
    return [
        home / ".local" / "bin",
        home / "bin",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/bin"),
        Path("/bin"),
    ]


def _candidate_path(command_name: str, search_path: str | None, extra_dirs: Iterable[Path]) -> str | None:
    found = shutil.which(command_name, path=search_path)
    if found:
        return found
    for directory in extra_dirs:
        candidate = directory / command_name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _format_home_template(template: str, home: Path) -> str:
    return template.format(home=str(home))


def _safe_version(command_path: str, args: tuple[str, ...], timeout_seconds: float = 2.0) -> str:
    try:
        result = _run_probe_command(command_path, args, timeout_seconds)
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    output = (result.stdout or "").strip().splitlines()
    noisy = ("warning:", "panicked", "panic", "error:", "could not connect")
    for line in output:
        cleaned = line.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(item in lowered for item in noisy):
            continue
        return cleaned[:160]
    return ""


def _safe_probe_outputs(
    command_path: str,
    probe_args: tuple[tuple[str, ...], ...],
    timeout_seconds: float = 2.0,
) -> list[str]:
    outputs: list[str] = []
    for args in probe_args:
        try:
            result = _run_probe_command(command_path, args, timeout_seconds)
        except Exception:  # noqa: BLE001
            continue
        output = (result.stdout or "").strip()
        if output:
            outputs.append(output)
    return outputs


def _probe_version(outputs: Iterable[str]) -> str:
    noisy = ("warning:", "panicked", "panic", "error:", "could not connect")
    for output in outputs:
        for line in output.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if any(item in lowered for item in noisy):
                continue
            return cleaned[:160]
    return ""


def _verified_by_probe(definition: RuntimeDefinition, command_name: str | None, command_path: str) -> tuple[bool, list[str]]:
    if not definition.verification_keywords:
        return True, []

    binary_name = Path(command_path).name
    verified_names = {name.lower() for name in definition.verified_command_names}
    if binary_name.lower() in verified_names or (command_name or "").lower() in verified_names:
        return True, []

    probe_args = definition.safe_probe_args or (definition.safe_version_args,)
    outputs = _safe_probe_outputs(command_path, probe_args)
    combined = "\n".join(outputs).lower()
    for keyword in definition.verification_keywords:
        if keyword.lower() in combined:
            return True, outputs
    return False, outputs


def _marker_exists(markers: Iterable[str], home: Path) -> bool:
    for marker in markers:
        if Path(_format_home_template(marker, home)).exists():
            return True
    return False


def _save_terminal_attrs() -> list[tuple[int, list]]:
    if termios is None:
        return []
    saved: list[tuple[int, list]] = []
    seen: set[int] = set()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            fd = stream.fileno()
        except Exception:  # noqa: BLE001
            continue
        if fd in seen or not os.isatty(fd):
            continue
        try:
            saved.append((fd, termios.tcgetattr(fd)))
            seen.add(fd)
        except termios.error:
            continue
    return saved


def _restore_terminal_attrs(saved: list[tuple[int, list]]) -> None:
    if termios is None:
        return
    for fd, attrs in saved:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
        except termios.error:
            continue


def _run_probe_command(command_path: str, args: tuple[str, ...], timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    saved = _save_terminal_attrs()
    try:
        return subprocess.run(
            [command_path, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    finally:
        _restore_terminal_attrs(saved)


def _ssh_base_command(
    *,
    remote_host: str,
    remote_user: str | None = None,
    remote_port: int | None = None,
    ssh_identity_file: str | None = None,
    ssh_command: str = "ssh",
    ssh_options: Iterable[str] | None = None,
) -> list[str]:
    command = [ssh_command]
    if remote_port:
        command.extend(["-p", str(remote_port)])
    if ssh_identity_file:
        command.extend(["-i", str(Path(ssh_identity_file).expanduser())])
    command.extend(str(item) for item in (ssh_options or []))
    target = f"{remote_user}@{remote_host}" if remote_user else remote_host
    command.append(target)
    return command


def _run_remote_shell(
    shell_command: str,
    *,
    remote_host: str,
    remote_user: str | None = None,
    remote_port: int | None = None,
    ssh_identity_file: str | None = None,
    ssh_command: str = "ssh",
    ssh_options: Iterable[str] | None = None,
    timeout_seconds: float = 6.0,
) -> subprocess.CompletedProcess[str]:
    command = _ssh_base_command(
        remote_host=remote_host,
        remote_user=remote_user,
        remote_port=remote_port,
        ssh_identity_file=ssh_identity_file,
        ssh_command=ssh_command,
        ssh_options=ssh_options,
    )
    command.append(shell_command)
    return subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _remote_path_assignment(remote_path: Iterable[str] | None = None) -> str:
    parts = [str(item).strip() for item in (remote_path or []) if str(item).strip()]
    if not parts:
        return ""
    joined = ":".join(shlex.quote(item) for item in parts)
    return f"PATH={joined}:$PATH"


def _safe_remote_version(
    command_path: str,
    args: tuple[str, ...],
    *,
    remote_host: str,
    remote_user: str | None,
    remote_port: int | None,
    ssh_identity_file: str | None,
    ssh_command: str,
    ssh_options: Iterable[str],
    remote_path: Iterable[str],
    timeout_seconds: float = 4.0,
) -> str:
    prefix = _remote_path_assignment(remote_path)
    command = shlex.join([command_path, *args])
    shell_command = f"{prefix} {command}" if prefix else command
    try:
        result = _run_remote_shell(
            shell_command,
            remote_host=remote_host,
            remote_user=remote_user,
            remote_port=remote_port,
            ssh_identity_file=ssh_identity_file,
            ssh_command=ssh_command,
            ssh_options=ssh_options,
            timeout_seconds=timeout_seconds,
        )
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    return _probe_version([result.stdout or ""])


def _remote_verified_by_probe(
    definition: RuntimeDefinition,
    command_name: str,
    command_path: str,
    *,
    remote_host: str,
    remote_user: str | None,
    remote_port: int | None,
    ssh_identity_file: str | None,
    ssh_command: str,
    ssh_options: Iterable[str],
    remote_path: Iterable[str],
) -> tuple[bool, list[str]]:
    if not definition.verification_keywords:
        return True, []
    verified_names = {name.lower() for name in definition.verified_command_names}
    if Path(command_path).name.lower() in verified_names or command_name.lower() in verified_names:
        return True, []
    outputs: list[str] = []
    for args in definition.safe_probe_args or (definition.safe_version_args,):
        prefix = _remote_path_assignment(remote_path)
        command = shlex.join([command_path, *args])
        shell_command = f"{prefix} {command}" if prefix else command
        try:
            result = _run_remote_shell(
                shell_command,
                remote_host=remote_host,
                remote_user=remote_user,
                remote_port=remote_port,
                ssh_identity_file=ssh_identity_file,
                ssh_command=ssh_command,
                ssh_options=ssh_options,
                timeout_seconds=4.0,
            )
        except Exception:  # noqa: BLE001
            continue
        if result.stdout:
            outputs.append(result.stdout)
    combined = "\n".join(outputs).lower()
    for keyword in definition.verification_keywords:
        if keyword.lower() in combined:
            return True, outputs
    return False, outputs


def discover_local_runtimes(
    *,
    search_path: str | None = None,
    home: Path | None = None,
    include_version: bool = True,
    include_common_dirs: bool = True,
    include_probe_output: bool = False,
) -> list[dict]:
    """Detect locally installed AI runtimes without executing work.

    Discovery checks executable presence on PATH/common binary directories and
    selected config directory markers. The only subprocess invocation is a
    short, timeout-bound version command.
    """
    home = home or Path.home()
    extra_dirs = _common_binary_dirs(home) if include_common_dirs else []
    results: list[dict] = []

    for definition in RUNTIME_REGISTRY:
        command_path = None
        command_name = None
        for candidate in definition.command_names:
            command_path = _candidate_path(candidate, search_path, extra_dirs)
            if command_path:
                command_name = candidate
                break

        detected_by: list[str] = []
        if command_path:
            detected_by.append("path")
        if _marker_exists(definition.config_markers, home):
            detected_by.append("config")
        if not detected_by:
            continue

        probe_outputs: list[str] = []
        if command_path:
            verified, probe_outputs = _verified_by_probe(definition, command_name, command_path)
            if not verified:
                continue

        command = [command_path or command_name or definition.command_names[0]]
        adapter_supported = definition.adapter_type in SUPPORTED_ADAPTER_TYPES
        version = ""
        if include_version and command_path:
            if definition.safe_probe_args:
                version = _probe_version(probe_outputs or _safe_probe_outputs(command[0], definition.safe_probe_args))
            elif include_probe_output:
                probe_outputs = _safe_probe_outputs(command[0], (definition.safe_version_args,))
                version = _probe_version(probe_outputs)
            else:
                version = _safe_version(command[0], definition.safe_version_args)

        node_path: str | None = None
        node_bin_dir: str | None = None
        if definition.runtime_id == "crush":
            node_path, node_bin_dir = _find_node_bin(search_path, extra_dirs)
            if not node_bin_dir:
                nvm_dirs = _nvm_node_bin_dirs(home)
                for nb in nvm_dirs:
                    nb_str = str(nb)
                    if Path(nb_str, "node").is_file():
                        node_bin_dir = nb_str
                        node_path = nb_str + "/node"
                        break

        runtime = {
            "id": definition.runtime_id,
            "runtime_id": definition.runtime_id,
            "label": definition.label,
            "type": definition.runtime_type,
            "runtime_type": definition.runtime_type,
            "command": command,
            "command_path": command[0],
            "capabilities": list(definition.capabilities),
            "cost_tier": definition.cost_tier,
            "usage_risk": definition.usage_risk,
            "preferred_roles": list(definition.preferred_roles),
            "avoid_roles": list(definition.avoid_roles),
            "adapter_type": definition.adapter_type,
            "adapter_supported": adapter_supported,
            "supported_modes": list(definition.supported_modes),
            "timeout_seconds": definition.default_timeout_seconds,
            "detected": True,
            "detected_by": detected_by,
            "version": version,
        }
        if node_bin_dir:
            runtime["node_bin_dir"] = node_bin_dir
        if node_path:
            runtime["node_path"] = node_path
        if definition.skill_path_template:
            runtime["skill_path"] = _format_home_template(definition.skill_path_template, home)
            runtime["skill_format"] = definition.skill_format
        if include_probe_output:
            runtime["probe_output"] = probe_outputs
        results.append(runtime)

    return results


def discover_remote_runtimes(
    *,
    remote_host: str,
    remote_user: str | None = None,
    remote_port: int | None = None,
    ssh_identity_file: str | None = None,
    remote_working_dir: str | None = None,
    remote_path: Iterable[str] | None = None,
    ssh_command: str = "ssh",
    ssh_options: Iterable[str] | None = None,
    include_version: bool = True,
    include_probe_output: bool = False,
) -> list[dict]:
    """Detect AI runtimes on a reachable SSH host without running agent work."""
    if not remote_host:
        return []

    options = list(ssh_options or [])
    command_names = sorted({name for definition in RUNTIME_REGISTRY for name in definition.command_names})
    dirs_literal = " ".join(_remote_binary_dir_words(remote_path))
    names_literal = " ".join(shlex.quote(item) for item in command_names)
    shell = (
        f"for d in {dirs_literal}; do "
        "for expanded in $d; do "
        "[ -d \"$expanded\" ] || continue; "
        f"for c in {names_literal}; do "
        "p=\"$expanded/$c\"; "
        "[ -x \"$p\" ] && printf '%s\t%s\n' \"$c\" \"$p\"; "
        "done; "
        "done; "
        "done"
    )
    try:
        result = _run_remote_shell(
            shell,
            remote_host=remote_host,
            remote_user=remote_user,
            remote_port=remote_port,
            ssh_identity_file=ssh_identity_file,
            ssh_command=ssh_command,
            ssh_options=options,
            timeout_seconds=8.0,
        )
    except Exception:  # noqa: BLE001
        return []
    if result.returncode != 0:
        return []

    found: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        name, sep, path = line.partition("\t")
        if sep and name and path and name not in found:
            found[name] = path

    discovered_bins = sorted({str(Path(path).parent) for path in found.values()})
    adapter_remote_path = []
    for item in [*(remote_path or []), *discovered_bins]:
        cleaned = str(item).strip()
        if cleaned and cleaned not in adapter_remote_path:
            adapter_remote_path.append(cleaned)

    results: list[dict] = []
    for definition in RUNTIME_REGISTRY:
        command_name = None
        command_path = None
        for candidate in definition.command_names:
            if candidate in found:
                command_name = candidate
                command_path = found[candidate]
                break
        if not command_path or not command_name:
            continue

        probe_outputs: list[str] = []
        verified, probe_outputs = _remote_verified_by_probe(
            definition,
            command_name,
            command_path,
            remote_host=remote_host,
            remote_user=remote_user,
            remote_port=remote_port,
            ssh_identity_file=ssh_identity_file,
            ssh_command=ssh_command,
            ssh_options=options,
            remote_path=adapter_remote_path,
        )
        if not verified:
            continue

        version = ""
        if include_version:
            if definition.safe_probe_args:
                if not probe_outputs:
                    for args in definition.safe_probe_args:
                        version = _safe_remote_version(
                            command_path,
                            args,
                            remote_host=remote_host,
                            remote_user=remote_user,
                            remote_port=remote_port,
                            ssh_identity_file=ssh_identity_file,
                            ssh_command=ssh_command,
                            ssh_options=options,
                            remote_path=adapter_remote_path,
                        )
                        if version:
                            break
                else:
                    version = _probe_version(probe_outputs)
            else:
                version = _safe_remote_version(
                    command_path,
                    definition.safe_version_args,
                    remote_host=remote_host,
                    remote_user=remote_user,
                    remote_port=remote_port,
                    ssh_identity_file=ssh_identity_file,
                    ssh_command=ssh_command,
                    ssh_options=options,
                    remote_path=adapter_remote_path,
                )

        runtime = {
            "id": definition.runtime_id,
            "runtime_id": definition.runtime_id,
            "label": definition.label,
            "type": definition.runtime_type,
            "runtime_type": definition.runtime_type,
            "command": [command_path],
            "command_path": command_path,
            "capabilities": list(definition.capabilities),
            "cost_tier": definition.cost_tier,
            "usage_risk": definition.usage_risk,
            "preferred_roles": list(definition.preferred_roles),
            "avoid_roles": list(definition.avoid_roles),
            "adapter_type": definition.adapter_type,
            "adapter_supported": definition.adapter_type in SUPPORTED_ADAPTER_TYPES,
            "supported_modes": list(definition.supported_modes),
            "timeout_seconds": definition.default_timeout_seconds,
            "detected": True,
            "detected_by": ["ssh", "path"],
            "version": version,
            "remote_host": remote_host,
            "remote_user": remote_user or "",
            "remote_port": remote_port or 22,
            "remote_working_dir": remote_working_dir or "",
            "remote_path": adapter_remote_path,
            "ssh_command": ssh_command,
            "ssh_options": options,
        }
        if ssh_identity_file:
            runtime["ssh_identity_file"] = ssh_identity_file
        if definition.runtime_id == "crush":
            for bin_dir in adapter_remote_path:
                if "/.nvm/versions/node/" in bin_dir:
                    runtime["node_bin_dir"] = bin_dir
                    runtime["node_path"] = str(Path(bin_dir) / "node")
                    break
        if include_probe_output:
            runtime["probe_output"] = probe_outputs
        results.append(runtime)

    return results


def runtime_to_adapter_config(runtime: dict) -> dict:
    adapter_type = str(runtime.get("adapter_type") or runtime.get("type") or "unsupported")
    enabled = bool(runtime.get("adapter_supported", adapter_type in SUPPORTED_ADAPTER_TYPES))
    config = {
        "type": adapter_type,
        "runtime_type": runtime.get("runtime_type") or runtime.get("type") or adapter_type,
        "runtime_name": runtime.get("label") or runtime.get("runtime_id") or runtime.get("id"),
        "enabled": enabled,
        "command": list(runtime.get("command") or [runtime.get("command_path") or runtime.get("id")]),
        "timeout_seconds": int(runtime.get("timeout_seconds") or 120),
        "capabilities": list(runtime.get("capabilities") or []),
        "cost_tier": runtime.get("cost_tier") or "medium",
        "usage_risk": runtime.get("usage_risk") or "medium",
        "preferred_roles": list(runtime.get("preferred_roles") or []),
        "avoid_roles": list(runtime.get("avoid_roles") or []),
        "supported_modes": list(runtime.get("supported_modes") or []),
    }
    if runtime.get("version"):
        config["version"] = runtime["version"]
    for key in (
        "remote_host",
        "remote_user",
        "remote_port",
        "ssh_identity_file",
        "remote_working_dir",
        "remote_path",
        "ssh_command",
        "ssh_options",
    ):
        value = runtime.get(key)
        if value not in (None, "", []):
            config[key] = value
    if adapter_type == "openclaw":
        config["agent_id"] = "main"
        config["experimental"] = True
        config["message_prefix"] = "You are receiving this via synkraken. Reply directly and concisely."
    elif adapter_type == "claude":
        config["bare"] = False
        config["permission_mode"] = "bypassPermissions"
        config["output_format"] = "text"
        config["message_prefix"] = "Keep replies focused and structured."
    elif adapter_type == "goose":
        config["system"] = "You are replying through synkraken. Keep replies concise and structured."
    elif adapter_type == "crush":
        config["message_prefix"] = "Keep replies focused and concise."
        if runtime.get("node_bin_dir"):
            config["node_bin_dir"] = runtime["node_bin_dir"]
        if runtime.get("node_path"):
            config["node_path"] = runtime["node_path"]
    elif adapter_type == "hermes":
        config["system_prefix"] = "You are replying through synkraken. Keep replies concise and structured."
    return config


def runtime_to_registry_config(runtime: dict, *, enabled: bool | None = None) -> dict:
    adapter_type = str(runtime.get("adapter_type") or "unsupported")
    is_enabled = bool(runtime.get("adapter_supported", False)) if enabled is None else enabled
    item = {
        "runtime_id": runtime.get("runtime_id") or runtime.get("id"),
        "runtime_type": runtime.get("runtime_type") or runtime.get("type") or "unknown",
        "command": list(runtime.get("command") or []),
        "capabilities": list(runtime.get("capabilities") or []),
        "cost_tier": runtime.get("cost_tier") or "medium",
        "usage_risk": runtime.get("usage_risk") or "medium",
        "preferred_roles": list(runtime.get("preferred_roles") or []),
        "avoid_roles": list(runtime.get("avoid_roles") or []),
        "adapter_type": adapter_type,
        "supported_modes": list(runtime.get("supported_modes") or []),
        "enabled": is_enabled,
    }
    if runtime.get("version"):
        item["version"] = runtime["version"]
    for key in (
        "remote_host",
        "remote_user",
        "remote_port",
        "ssh_identity_file",
        "remote_working_dir",
        "remote_path",
        "ssh_command",
        "ssh_options",
    ):
        value = runtime.get(key)
        if value not in (None, "", []):
            item[key] = value
    return item


def parse_runtime_selection(runtimes: list[dict], raw: str, *, supported_only: bool = False) -> list[dict]:
    value = raw.strip().lower()
    candidates = [rt for rt in runtimes if not supported_only or rt.get("adapter_supported")]
    if not value or value == "all":
        return candidates
    if value == "none":
        return []

    parts = raw.replace(",", " ").split()
    if any(not item for item in parts):
        raise ValueError('use comma- or space-separated numbers, "all", or "none"')

    selected: list[dict] = []
    seen_indexes: set[int] = set()
    for item in parts:
        if not item.isdigit():
            raise ValueError(f'"{item}" is not a number')
        index = int(item)
        if index < 1 or index > len(runtimes):
            raise ValueError(f'{index} is outside the range 1-{len(runtimes)}')
        if index in seen_indexes:
            continue
        seen_indexes.add(index)
        runtime = runtimes[index - 1]
        if not supported_only or runtime.get("adapter_supported"):
            selected.append(runtime)
    return selected


def merge_discovered_config(
    config: dict,
    selected_runtimes: list[dict],
    *,
    behaviour: str = "merge",
) -> tuple[dict, dict]:
    behaviour = behaviour.lower()
    if behaviour not in {"merge", "replace", "skip"}:
        raise ValueError("merge behaviour must be one of: merge, replace, skip")
    if behaviour == "skip":
        return config, {"behaviour": behaviour, "adapters_added": [], "adapters_replaced": [], "registry_added": []}

    merged = dict(config)
    existing_adapters = dict(config.get("adapters") or {})
    existing_registry = dict(config.get("runtime_registry") or {})
    adapters = {} if behaviour == "replace" else existing_adapters
    registry = {} if behaviour == "replace" else existing_registry
    added: list[str] = []
    replaced: list[str] = []
    registry_added: list[str] = []

    for runtime in selected_runtimes:
        runtime_id = str(runtime.get("runtime_id") or runtime.get("id"))
        registry[runtime_id] = runtime_to_registry_config(
            runtime,
            enabled=bool(runtime.get("adapter_supported")),
        )
        registry_added.append(runtime_id)
        if not runtime.get("adapter_supported"):
            continue
        adapter_config = runtime_to_adapter_config(runtime)
        if runtime_id in adapters:
            if behaviour == "merge":
                preserved = dict(adapters[runtime_id])
                preserved.setdefault("type", adapter_config["type"])
                preserved.setdefault("runtime_type", adapter_config["runtime_type"])
                preserved.setdefault("runtime_name", adapter_config["runtime_name"])
                preserved.setdefault("command", adapter_config["command"])
                preserved.setdefault("capabilities", adapter_config["capabilities"])
                preserved.setdefault("cost_tier", adapter_config["cost_tier"])
                preserved.setdefault("supported_modes", adapter_config["supported_modes"])
                adapters[runtime_id] = preserved
            else:
                adapters[runtime_id] = adapter_config
                replaced.append(runtime_id)
        else:
            adapters[runtime_id] = adapter_config
            if behaviour == "replace" and runtime_id in existing_adapters:
                replaced.append(runtime_id)
            else:
                added.append(runtime_id)

    merged["adapters"] = adapters
    merged["runtime_registry"] = registry
    return merged, {
        "behaviour": behaviour,
        "adapters_added": added,
        "adapters_replaced": replaced,
        "registry_added": registry_added,
    }
