from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .branding import NAME, TAGLINE, print_logo
from .discovery import RUNTIME_REGISTRY, SUPPORTED_ADAPTER_TYPES, discover_local_runtimes
from .setup_mode import run_install_skills, run_setup, run_uninstall
from .tui import run_tui
from .web import serve as serve_web

DEFAULT_BASE = os.environ.get("SYNKRAKEN_URL", "http://127.0.0.1:9460")


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def marker(ok: bool) -> str:
    return "●" if ok else "○"


def print_agents(data: dict) -> None:
    agents = data.get("agents", [])
    if not agents:
        print("No adapters registered.")
        return
    for agent in agents:
        adapter_id = agent.get("adapter_id", "unknown")
        adapter_type = agent.get("type", "unknown")
        runtime_name = agent.get("runtime_name", adapter_id)
        enabled = bool(agent.get("enabled", False))
        status = agent.get("status") or ("online" if enabled else "disabled")
        last_seen = agent.get("last_seen_at") or "never"
        print(f"{marker(enabled)} {runtime_name:<10} [{adapter_id}]  type={adapter_type}  status={status}  last_seen={last_seen}")


def print_health(data: dict) -> None:
    ok = bool(data.get("ok", False))
    print(f"{NAME} health: {'OK' if ok else 'NOT OK'}")
    timestamp = data.get("timestamp")
    if timestamp:
        print()
        print(f"time: {timestamp}")
    adapters = data.get("adapters", {})
    if adapters:
        print()
        for adapter_id, adapter in adapters.items():
            runtime_name = adapter.get("runtime_name", adapter_id)
            enabled = bool(adapter.get("enabled", False))
            adapter_type = adapter.get("type", "unknown")
            print(f"{marker(enabled)} {runtime_name:<10} [{adapter_id}]  type={adapter_type}  enabled={str(enabled).lower()}")


def print_discovery(data: dict, *, verbose: bool = False) -> None:
    runtimes = data.get("runtimes", [])
    if not verbose:
        print("Discovered AI workers:")
        print()
        for runtime in runtimes:
            label = runtime.get("label") or runtime.get("runtime_id") or runtime.get("id")
            if runtime.get("runtime_id") == "google-antigravity":
                label = "Antigravity"
            print(f"- {label}")
        print()
        print(f"Total found: {len(runtimes)}")
        return

    for index, runtime in enumerate(runtimes):
        if index:
            print()
        label = runtime.get("label") or runtime.get("runtime_id") or runtime.get("id")
        command = " ".join(str(item) for item in runtime.get("command") or [])
        version = runtime.get("version") or ""
        detection = ", ".join(runtime.get("detected_by") or []) or "unknown"
        capabilities = ", ".join(str(item) for item in runtime.get("capabilities") or [])
        print(label)
        print(f"  command: {command}")
        print(f"  version: {version}")
        print(f"  detection: {detection}")
        print(f"  capabilities: {capabilities}")


def _runtime_definitions() -> dict[str, object]:
    return {definition.runtime_id: definition for definition in RUNTIME_REGISTRY}


def _runtime_definition(runtime_id: str, runtime_type: str = "") -> object | None:
    definitions = _runtime_definitions()
    if runtime_id in definitions:
        return definitions[runtime_id]
    for definition in RUNTIME_REGISTRY:
        if definition.runtime_type == runtime_type:
            return definition
    return None


def _normalize_command(command: object) -> list[str]:
    if isinstance(command, str):
        return [command] if command else []
    if isinstance(command, list):
        return [str(item) for item in command if str(item)]
    return []


def _normalize_runtime(runtime_id: str, item: dict, *, source: str = "config") -> dict:
    runtime_type = str(item.get("runtime_type") or item.get("type") or item.get("runtime") or runtime_id)
    definition = _runtime_definition(runtime_id, runtime_type)
    label = str(
        item.get("runtime_name")
        or item.get("label")
        or getattr(definition, "label", "")
        or runtime_id
    )
    adapter_type = str(item.get("adapter_type") or item.get("type") or getattr(definition, "adapter_type", runtime_type))
    command = _normalize_command(item.get("command"))
    if not command and definition is not None:
        command = [getattr(definition, "command_names")[0]]
    capabilities = item.get("capabilities") or getattr(definition, "capabilities", ())
    supported_modes = item.get("supported_modes") or item.get("modes") or getattr(definition, "supported_modes", ())
    enabled = item.get("enabled", True)
    skill_path = item.get("skill_path")
    if not skill_path and definition is not None and getattr(definition, "skill_path_template", None):
        skill_path = getattr(definition, "skill_path_template").format(home=str(Path.home()))
    normalized = {
        "runtime_id": runtime_id,
        "display_name": label,
        "runtime_type": runtime_type,
        "adapter_type": adapter_type,
        "command": command,
        "capabilities": [str(value) for value in capabilities],
        "cost_tier": item.get("cost_tier") or item.get("cost_profile") or getattr(definition, "cost_tier", "medium"),
        "usage_risk": item.get("usage_risk") or getattr(definition, "usage_risk", "medium"),
        "preferred_roles": [str(value) for value in (item.get("preferred_roles") or getattr(definition, "preferred_roles", ()))],
        "avoid_roles": [str(value) for value in (item.get("avoid_roles") or getattr(definition, "avoid_roles", ()))],
        "supported_modes": [str(value) for value in supported_modes],
        "enabled": bool(enabled),
        "adapter_supported": adapter_type in SUPPORTED_ADAPTER_TYPES,
        "skill_path": str(skill_path or ""),
        "skill_format": str(item.get("skill_format") or getattr(definition, "skill_format", "")),
        "source": source,
        "version": item.get("version") or "",
        "status": item.get("status") or "",
    }
    for key in ("registered", "ok", "health", "warnings", "node_available", "node_bin_dir"):
        if key in item:
            normalized[key] = item[key]
    return normalized


def _load_runtime_config(config_path: Path | None = None) -> dict:
    path = config_path or (Path.cwd() / "config.local.json")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"runtimes": [], "source": str(path), "missing": True}
    if not isinstance(data, dict):
        return {"runtimes": [], "source": str(path), "missing": False}

    runtimes: dict[str, dict] = {}
    for runtime_id, item in (data.get("adapters") or {}).items():
        if isinstance(item, dict):
            runtimes[str(runtime_id)] = _normalize_runtime(str(runtime_id), item, source="config")
    for runtime_id, item in (data.get("runtime_registry") or {}).items():
        if isinstance(item, dict) and str(runtime_id) not in runtimes:
            runtimes[str(runtime_id)] = _normalize_runtime(str(runtime_id), item, source="config")
    return {"runtimes": [runtimes[key] for key in sorted(runtimes)], "source": str(path), "missing": False}


def _normalize_runtime_payload(data: dict) -> dict:
    runtimes = []
    for item in data.get("runtimes") or []:
        if isinstance(item, dict):
            runtime_id = str(item.get("runtime_id") or item.get("id") or item.get("adapter_id") or "")
            if runtime_id:
                runtimes.append(_normalize_runtime(runtime_id, item, source="daemon"))
    return {"runtimes": runtimes, "source": "daemon", "missing": False}


def _runtime_data(base: str) -> dict:
    try:
        return _normalize_runtime_payload(get_json(f"{base}/v1/runtimes"))
    except Exception:
        return _load_runtime_config()


def _runtime_doctor_data(base: str) -> dict:
    try:
        return _normalize_runtime_payload(get_json(f"{base}/v1/runtimes/doctor"))
    except Exception:
        return _load_runtime_config()


def _runtime_detail_data(base: str, runtime_id: str) -> dict | None:
    try:
        return _normalize_runtime(runtime_id, get_json(f"{base}/v1/runtimes/{runtime_id}"), source="daemon")
    except Exception:  # noqa: BLE001
        for runtime in _load_runtime_config().get("runtimes", []):
            if runtime.get("runtime_id") == runtime_id:
                return runtime
    return None


def _command_exists(command: list[str]) -> bool:
    if not command:
        return False
    executable = command[0]
    if os.path.isabs(executable) or os.sep in executable:
        return Path(executable).exists()
    return shutil.which(executable) is not None


def _discovered_command_exists(runtime: dict) -> bool:
    definition = _runtime_definition(runtime["runtime_id"], runtime.get("runtime_type", ""))
    if definition is None:
        return _command_exists(runtime.get("command") or [])
    return any(shutil.which(command) is not None for command in getattr(definition, "command_names"))


def _bridge_skill_status(runtime: dict) -> str:
    if not runtime.get("adapter_supported"):
        return "not applicable"
    path = runtime.get("skill_path")
    if not path:
        return "no install path"
    target = Path(path).expanduser()
    expected = target / "synkraken-bridge.md" if runtime.get("skill_format") == "single_file" else target / "SKILL.md"
    return "installed" if expected.exists() else "missing"


def print_runtimes(data: dict) -> None:
    runtimes = data.get("runtimes", [])
    print("Runtime registry:")
    if not runtimes:
        print()
        print("(no runtimes)")
        return
    for runtime in runtimes:
        adapter_supported = bool(runtime.get("adapter_supported"))
        status = "adapter" if adapter_supported else "registry-only"
        if runtime.get("status"):
            status = str(runtime["status"])
        print()
        print(f"{marker(True)} {runtime.get('display_name') or runtime.get('runtime_id')}")
        print(f"  id: {runtime.get('runtime_id')}")
        print(f"  type: {runtime.get('runtime_type')}")
        print(f"  status: {status}")
        print(f"  enabled: {str(bool(runtime.get('enabled'))).lower()}")
        print(f"  cost tier: {runtime.get('cost_tier') or 'medium'}")
        print(f"  usage risk: {runtime.get('usage_risk') or 'medium'}")
        print(f"  preferred roles: {', '.join(runtime.get('preferred_roles') or []) or '(none)'}")
        print(f"  avoid roles: {', '.join(runtime.get('avoid_roles') or []) or '(none)'}")
        if not adapter_supported:
            print("  note: adapter not implemented yet")


def print_runtime_detail(runtime: dict) -> None:
    print(f"id: {runtime.get('runtime_id')}")
    print(f"display name: {runtime.get('display_name')}")
    print(f"runtime type: {runtime.get('runtime_type')}")
    print(f"adapter type: {runtime.get('adapter_type')}")
    print(f"command: {' '.join(runtime.get('command') or []) or '(none)'}")
    print(f"capabilities: {', '.join(runtime.get('capabilities') or []) or '(none)'}")
    print(f"cost tier: {runtime.get('cost_tier') or 'unknown'}")
    print(f"usage risk: {runtime.get('usage_risk') or 'medium'}")
    print(f"preferred roles: {', '.join(runtime.get('preferred_roles') or []) or '(none)'}")
    print(f"avoid roles: {', '.join(runtime.get('avoid_roles') or []) or '(none)'}")
    print(f"enabled: {str(bool(runtime.get('enabled'))).lower()}")
    print(f"adapter-supported: {'yes' if runtime.get('adapter_supported') else 'no'}")


def print_runtime_doctor(data: dict) -> None:
    runtimes = data.get("runtimes", [])
    print("Runtime doctor:")
    if not runtimes:
        print()
        print("(no runtimes)")
        return
    for runtime in runtimes:
        adapter_supported = bool(runtime.get("adapter_supported"))
        print()
        print(runtime.get("display_name") or runtime.get("runtime_id"))
        print(f"  id: {runtime.get('runtime_id')}")
        print(f"  discovered command exists: {'yes' if _discovered_command_exists(runtime) else 'no'}")
        print(f"  configured command exists: {'yes' if _command_exists(runtime.get('command') or []) else 'no'}")
        print(f"  adapter: {'implemented' if adapter_supported else 'registry-only'}")
        print(f"  cost tier: {runtime.get('cost_tier') or 'medium'}")
        print(f"  usage risk: {runtime.get('usage_risk') or 'medium'}")
        print(f"  preferred roles: {', '.join(runtime.get('preferred_roles') or []) or '(none)'}")
        print(f"  avoid roles: {', '.join(runtime.get('avoid_roles') or []) or '(none)'}")
        if runtime.get("runtime_id") == "crush":
            node_ok = bool(runtime.get("node_available"))
            print(f"  node available to adapter: {'yes' if node_ok else 'no'}")
            if not node_ok:
                print("  hint: rerun `synkraken config --rediscover` from a shell where node is available")
        print(f"  bridge skill: {_bridge_skill_status(runtime)}")


def print_recent(data: dict) -> None:
    rows = data.get("conversations", [])
    if not rows:
        print("No recent conversations.")
        return
    print("Recent conversations")
    print()
    for idx, item in enumerate(rows, start=1):
        print(f"{idx}. {item.get('conversation_id')}")
        print(f"   route: {item.get('sample_source')} -> {item.get('sample_target')}")
        print(f"   last:  {item.get('last_timestamp')}")
        print(f"   msgs:  {item.get('message_count')}")
        print(f"   text:  {item.get('preview')}")
        print()


def print_deliveries(data: dict) -> None:
    rows = data.get("deliveries", [])
    if not rows:
        print("No recent deliveries.")
        return
    print("Recent deliveries")
    print()
    for item in rows:
        ok = bool(item.get("ok", False))
        print(f"{marker(ok)} {item.get('adapter_id')}  status={item.get('status')}  attempts={item.get('attempts')}  duration_ms={item.get('duration_ms')}")
        if item.get("error"):
            print(f"   error: {item.get('error')}")
        print(f"   when:  {item.get('created_at')}")
        print(f"   text:  {item.get('body_preview')}")
        print()


def print_dead_letters(data: dict) -> None:
    rows = data.get("dead_letters", [])
    if not rows:
        print("No dead letters.")
        return
    print("Dead letters")
    print()
    for item in rows:
        print(f"○ {item.get('adapter_id')}  reason={item.get('reason')}")
        print(f"   message_id: {item.get('message_id')}")
        print(f"   created_at: {item.get('created_at')}")
        print()


def print_result(data: dict, raw: bool) -> None:
    if raw:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    message = data.get("message", {})
    if message:
        print(f"conversation_id: {message.get('conversation_id', '')}")
        print(f"message_id: {message.get('message_id', '')}")
        print(f"route: {message.get('source', '')} -> {message.get('target', '')}")
        print()
    deliveries = data.get("deliveries", [])
    if not deliveries:
        print("No deliveries.")
    for delivery in deliveries:
        label = delivery.get('runtime_name') or delivery.get('adapter_id', 'unknown')
        ok = bool(delivery.get('ok'))
        print(f"{marker(ok)} {label} [{delivery.get('adapter_id', 'unknown')}]  status={delivery.get('status')}  attempts={delivery.get('attempts', 1)}  duration_ms={delivery.get('duration_ms')}")
        if delivery.get("quality"):
            print(f"   quality: {delivery.get('quality')}")
        if delivery.get("error"):
            print(f"   error: {delivery.get('error')}")
        body = (delivery.get("body") or "").strip()
        if body:
            print(f"   {body}")
        print()
    dead_letters = data.get("dead_letters", [])
    if dead_letters:
        print("Dead letters")
        for item in dead_letters:
            print(f"○ {item.get('adapter_id')}: {item.get('reason')}")


def _systemd_service_installed() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "cat", "synkraken.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _print_service_install_help() -> None:
    print("SynKraken user service is not installed.")
    print()
    print("Install and start it with:")
    print("  ./scripts/install-user-service.sh")
    print("  systemctl --user enable --now synkraken")


def _run_systemctl(action: str) -> int:
    command = ["systemctl", "--user", action, "synkraken"]
    if action == "status":
        command.append("--no-pager")
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        print("systemctl was not found on PATH.", file=sys.stderr)
        return 1


def _print_daemon_health(base: str) -> None:
    print()
    print(f"Daemon URL: {base}")
    try:
        data = get_json(f"{base}/health")
    except Exception as exc:  # noqa: BLE001
        print(f"Daemon health: unavailable ({exc})")
        return
    print(f"Daemon health: {'OK' if bool(data.get('ok', False)) else 'NOT OK'}")


def _wait_for_daemon_health(base: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + max(1, timeout_seconds)
    last_error = ""
    while time.monotonic() < deadline:
        try:
            data = get_json(f"{base}/health")
            if bool(data.get("ok", False)):
                return True
            last_error = "health endpoint returned NOT OK"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    detail = f" ({last_error})" if last_error else ""
    print(f"Daemon did not become healthy within {timeout_seconds}s at {base}/health{detail}", file=sys.stderr)
    return False


def handle_lifecycle_command(action: str, base: str, wait_seconds: int = 15) -> int:
    if not _systemd_service_installed():
        _print_service_install_help()
        if action == "status":
            _print_daemon_health(base)
        return 1

    returncode = _run_systemctl(action)
    if action in {"start", "restart"} and returncode == 0:
        if not _wait_for_daemon_health(base, wait_seconds):
            return 1
    if action == "status":
        _print_daemon_health(base)
    return returncode


def add_lifecycle_parser(sub: argparse._SubParsersAction, action: str) -> None:
    help_text = {
        "start": "Start the daemon via the user service",
        "stop": "Stop the daemon via the user service",
        "restart": "Restart the daemon via the user service",
        "status": "Show user-service state and daemon health",
    }[action]
    parser = sub.add_parser(action, help=help_text)
    parser.add_argument("target", nargs="?", choices=["daemon"], help="Optional explicit target")
    if action in {"start", "restart"}:
        parser.add_argument("--wait-seconds", type=int, default=15, help="Seconds to wait for daemon health")
    add_base_url_arg(parser)


def add_base_url_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=DEFAULT_BASE, help="Base URL for synkraken")
    parser.add_argument("--json", action="store_true", help="Print raw JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synkraken",
        description="SYNKRAKEN is a local operator console for the synkraken bridge.",
        epilog=(
            "Examples:\n"
            "  synkraken tui\n"
            "  synkraken start daemon\n"
            "  synkraken status\n"
            "  synkraken health\n"
            "  synkraken agents\n"
            "  synkraken runtimes\n"
            "  synkraken runtime doctor\n"
            "  synkraken send hermes \"Reply with exactly: HELLO\"\n"
            "  synkraken config"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    for action in ("start", "stop", "restart", "status"):
        add_lifecycle_parser(sub, action)

    p_health = sub.add_parser("health", help="Check bridge health")
    add_base_url_arg(p_health)

    p_agents = sub.add_parser("agents", help="List registered adapters")
    add_base_url_arg(p_agents)

    p_runtimes = sub.add_parser("runtimes", help="List runtime registry entries")
    add_base_url_arg(p_runtimes)

    p_runtime = sub.add_parser("runtime", help="Inspect one runtime or run runtime diagnostics")
    p_runtime.add_argument("runtime_id", help="Runtime id or 'doctor'")
    add_base_url_arg(p_runtime)

    p_send = sub.add_parser("send", help="Send a message through the bridge")
    p_send.add_argument("target", help="Target adapter id or 'broadcast'")
    p_send.add_argument("message", nargs="?", help="Message body. If omitted, stdin is used.")
    p_send.add_argument("--source", default="operator", help="Logical source label")
    p_send.add_argument("--subject", default=None, help="Optional subject")
    p_send.add_argument("--priority", default="normal", help="Priority label")
    p_send.add_argument("--conversation-id", default=None, help="Optional conversation id")
    add_base_url_arg(p_send)

    p_history = sub.add_parser("history", help="Fetch a stored conversation record")
    p_history.add_argument("conversation_id", help="Conversation id to fetch")
    add_base_url_arg(p_history)

    p_recent = sub.add_parser("recent", help="List recent conversations")
    p_recent.add_argument("--limit", type=int, default=10)
    add_base_url_arg(p_recent)

    p_deliveries = sub.add_parser("deliveries", help="List recent deliveries")
    p_deliveries.add_argument("--limit", type=int, default=10)
    add_base_url_arg(p_deliveries)

    p_dead = sub.add_parser("dead-letters", help="List recent dead letters")
    p_dead.add_argument("--limit", type=int, default=10)
    add_base_url_arg(p_dead)

    p_tui = sub.add_parser("tui", help="Launch the interactive TUI")
    p_tui.add_argument('--banner-only', action='store_true', help='Print banner and exit')

    p_web = sub.add_parser("web", help="Launch the local web command deck")
    p_web.add_argument("--host", default="127.0.0.1", help="Host for the local web UI")
    p_web.add_argument("--port", type=int, default=9461, help="Port for the local web UI")
    p_web.add_argument("--daemon-url", default=DEFAULT_BASE, help="Existing synkraken daemon base URL")

    p_discover = sub.add_parser("discover", help="Discover local AI runtimes without changing config")
    p_discover.add_argument("--json", action="store_true", help="Print raw JSON output")
    p_discover.add_argument("--verbose", action="store_true", help="Print full command paths and probe output")

    p_config = sub.add_parser("config", help="Interactive setup: detect runtimes, install the bridge skill, create config.local.json")
    p_config.add_argument("--rediscover", action="store_true", help="Rescan runtimes and merge them into config.local.json")
    p_config.add_argument("--install-skills", action="store_true", help="Install bridge skills for configured workers")
    sub.add_parser("uninstall", help="Interactive removal: uninstall the bridge skill from runtimes and clean up local files")

    p_decisions = sub.add_parser("decisions", help="List decisions")
    p_decisions.add_argument("--room", help="Filter by room")
    p_decisions.add_argument("--status", help="Filter by status (proposed/approved/rejected/superseded)")
    add_base_url_arg(p_decisions)

    p_decision = sub.add_parser("decision", help="Inspect a decision")
    p_decision.add_argument("decision_id", help="Decision id")
    add_base_url_arg(p_decision)

    p_approve = sub.add_parser("approve", help="Approve a decision")
    p_approve.add_argument("decision_id", help="Decision id to approve")
    add_base_url_arg(p_approve)

    p_reject_cmd = sub.add_parser("reject", help="Reject a decision")
    p_reject_cmd.add_argument("decision_id", help="Decision id to reject")
    add_base_url_arg(p_reject_cmd)

    p_handoffs = sub.add_parser("handoffs", help="List handoffs")
    p_handoffs.add_argument("--room", help="Filter by room")
    p_handoffs.add_argument("--status", help="Filter by status (pending/accepted/rejected/completed)")
    add_base_url_arg(p_handoffs)

    p_handoff = sub.add_parser("handoff", help="Create or inspect a handoff")
    p_handoff.add_argument("action", nargs="?", choices=["create", "accept", "reject", "complete"], help="Action: create, accept, reject, complete")
    p_handoff.add_argument("id", nargs="?", help="Handoff id for accept/reject/complete")
    add_base_url_arg(p_handoff)

    p_replay = sub.add_parser("replay", help="Show a replay (goal run, team run, or decision)")
    p_replay.add_argument("id", help="Replay id")
    add_base_url_arg(p_replay)

    p_incident = sub.add_parser("incident", help="Show latest incident")
    p_incident.add_argument("action", nargs="?", choices=["latest"], default="latest", help="Show latest failure")
    add_base_url_arg(p_incident)

    return parser


def _print_no_command() -> None:
    print("SYNKRAKEN needs a command.\n")
    print("First-time setup:")
    print("  synkraken config            # walks you through it\n")
    print("Day-to-day:")
    print("  synkraken start daemon      # start the user service")
    print("  synkraken status            # service state + daemon health")
    print("  synkraken tui               # open the TUI dashboard")
    print("  synkraken web               # open the local web command deck")
    print("  synkraken health            # is the daemon ok?")
    print("  synkraken agents            # which adapters are configured?")
    print("  synkraken runtimes          # show runtime registry")
    print("  synkraken runtime doctor    # runtime diagnostics")
    print("  synkraken send hermes 'hi'  # message a single agent\n")
    print("Tear-down:")
    print("  synkraken uninstall         # remove bridge skills + clean up\n")
    print("Full help:")
    print("  synkraken --help")


def main() -> None:
    parser = build_parser()
    if len(sys.argv) == 1:
        _print_no_command()
        raise SystemExit(1)
    args = parser.parse_args()
    if not getattr(args, 'command', None):
        _print_no_command()
        raise SystemExit(1)
    if args.command == 'config':
        if args.install_skills:
            run_install_skills()
            return
        run_setup(rediscover=args.rediscover)
        return
    if args.command == 'discover':
        data = {"runtimes": discover_local_runtimes(include_probe_output=args.verbose and not args.json)}
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_discovery(data, verbose=args.verbose)
        return
    if args.command == 'uninstall':
        run_uninstall()
        return
    if args.command == 'tui':
        if args.banner_only:
            print_logo()
            print()
            return
        run_tui()
        return
    if args.command == 'web':
        serve_web(host=args.host, port=args.port, daemon_url=args.daemon_url)
        return
    base = args.url.rstrip("/")
    if args.command in {"start", "stop", "restart", "status"}:
        raise SystemExit(handle_lifecycle_command(args.command, base, getattr(args, "wait_seconds", 15)))
    try:
        if args.command == "health":
            data = get_json(f"{base}/health")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_health(data)
            return
        if args.command == "agents":
            data = get_json(f"{base}/v1/agents")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_agents(data)
            return
        if args.command == "runtimes":
            data = _runtime_data(base)
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_runtimes(data)
            return
        if args.command == "runtime":
            if args.runtime_id == "doctor":
                data = _runtime_doctor_data(base)
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print_runtime_doctor(data)
                return
            runtime = _runtime_detail_data(base, args.runtime_id)
            if not runtime:
                raise ValueError(f"runtime not found: {args.runtime_id}")
            if args.json:
                print(json.dumps(runtime, indent=2, ensure_ascii=False))
            else:
                print_runtime_detail(runtime)
            return
        if args.command == "history":
            data = get_json(f"{base}/v1/conversations/{args.conversation_id}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return
        if args.command == "recent":
            data = get_json(f"{base}/v1/conversations?limit={args.limit}")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_recent(data)
            return
        if args.command == "deliveries":
            data = get_json(f"{base}/v1/deliveries?limit={args.limit}")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_deliveries(data)
            return
        if args.command == "dead-letters":
            data = get_json(f"{base}/v1/dead-letters?limit={args.limit}")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_dead_letters(data)
            return
        if args.command == "send":
            body = args.message if args.message is not None else sys.stdin.read()
            if not body.strip():
                raise ValueError("message body is empty")
            payload = {
                "source": args.source,
                "target": args.target,
                "body": body,
                "subject": args.subject,
                "priority": args.priority,
                "conversation_id": args.conversation_id,
            }
            result = post_json(f"{base}/v1/messages", payload)
            print_result(result, raw=args.json)
            return
        if args.command == "decisions":
            url = f"{base}/v1/decisions"
            if args.room:
                url += f"?room={args.room}"
                if args.status:
                    url += f"&status={args.status}"
            elif args.status:
                url += f"?status={args.status}"
            data = get_json(url)
            decisions = data.get("decisions", [])
            if not decisions:
                print("No decisions found.")
            else:
                for d in decisions:
                    print(f"[{d['status']:12}] {d['timestamp'][:10]} {d['title']}")
                    print(f"  id: {d['decision_id']}  proposed_by: {d['proposed_by']}")
                    if d.get("approved_by"):
                        print(f"  approved_by: {d['approved_by']}")
                    print()
            return
        if args.command == "decision":
            data = get_json(f"{base}/v1/decisions/{args.decision_id}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return
        if args.command == "approve":
            payload = {"actor": "operator"}
            result = post_json(f"{base}/v1/decision/{args.decision_id}/approve", payload)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        if args.command == "reject":
            payload = {"actor": "operator"}
            result = post_json(f"{base}/v1/decision/{args.decision_id}/reject", payload)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        if args.command == "handoffs":
            url = f"{base}/v1/handoffs"
            if args.room:
                url += f"?room={args.room}"
                if args.status:
                    url += f"&status={args.status}"
            elif args.status:
                url += f"?status={args.status}"
            data = get_json(url)
            handoffs = data.get("handoffs", [])
            if not handoffs:
                print("No handoffs found.")
            else:
                for h in handoffs:
                    print(f"[{h['status']:10}] {h['created_at'][:10]} {h['summary'][:60]}")
                    print(f"  from: {h['from_agent']} -> to: {h['to_agent']}  id: {h['handoff_id']}")
                    print()
            return
        if args.command == "handoff":
            if args.action == "create":
                print("Use POST /v1/handoff to create a handoff (not yet interactive in CLI)")
                return
            if args.action in ("accept", "reject", "complete"):
                payload = {"actor": "operator"}
                result = post_json(f"{base}/v1/handoff/{args.id}/{args.action}", payload)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return
            if args.id:
                data = get_json(f"{base}/v1/handoffs/{args.id}")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print("synkraken handoff [create|accept|reject|complete] [id]")
            return
        if args.command == "replay":
            data = get_json(f"{base}/v1/replay/{args.id}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return
        if args.command == "incident":
            data = get_json(f"{base}/v1/incident/latest")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return
        raise ValueError(f"Unknown command: {args.command}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP error {exc.code}: {detail}", file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
