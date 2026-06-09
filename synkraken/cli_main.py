from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .branding import NAME, TAGLINE, print_logo
from .discovery import RUNTIME_REGISTRY, SUPPORTED_ADAPTER_TYPES, discover_local_runtimes, discover_remote_runtimes
from .setup_mode import run_install_skills, run_setup, run_uninstall
from .runtime_service import RuntimeServiceError, format_uptime, runtime_service_for_platform
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


def delete_json(url: str) -> dict:
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        detail = str(json.loads(body).get("error") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        detail = body.strip()
    if exc.code == 404 and detail.lower().startswith("room not found:"):
        return "Room not found:" + detail.split(":", 1)[1]
    return f"HTTP error {exc.code}: {detail or exc.reason}"

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


def print_workforce(data: dict) -> None:
    print("Workforce")
    rows = data.get("workforce") or []
    if not rows:
        print()
        print("(no enabled adapter workers)")
    for row in rows:
        reputation = row.get("reputation") or {}
        print()
        print(row.get("runtime_id"))
        print(f"  status: {row.get('status') or 'unknown'}")
        print(f"  trust: {reputation.get('trust_score', 100)}")
        print(f"  health: {reputation.get('health_status', 'healthy')}")
        print(f"  cost tier: {row.get('cost_tier') or 'medium'}")
        print(f"  latest delivery: {reputation.get('latest_delivery_status') or '(none)'}")
        print(f"  latest quality: {reputation.get('latest_quality') or '(none)'}")
        print(f"  recent failures: {reputation.get('failures', 0)}")
        print(f"  recent timeouts: {reputation.get('timeouts', 0)}")
        print(f"  recent empty replies: {reputation.get('empty_replies', 0)}")
        avg = reputation.get("avg_duration_ms")
        print(f"  avg duration: {avg}ms" if avg is not None else "  avg duration: (none)")
        if reputation.get("incident_summary"):
            print(f"  issue: {reputation.get('incident_summary')}")
    inactive = data.get("available_but_inactive") or []
    print()
    print("Available but inactive:")
    if inactive:
        for item in inactive:
            print(f"- {item.get('runtime_id')} ({item.get('reason') or 'inactive'})")
    else:
        print("- (none)")


def print_workforce_health(data: dict) -> None:
    summary = data.get("summary") or {}
    print("Workforce Summary")
    print()
    for status in ("healthy", "degraded", "unstable", "failing"):
        print(f"{status}: {summary.get(status, 0)}")
    print()
    print("Top trusted:")
    for runtime_id in data.get("top_trusted") or []:
        print(f"- {runtime_id}")
    print()
    print("Most unstable:")
    unstable = data.get("most_unstable") or []
    if unstable:
        for runtime_id in unstable:
            print(f"- {runtime_id}")
    else:
        print("- (none)")
    print()
    print("Recent incidents:")
    incidents = data.get("recent_incidents") or []
    if incidents:
        for incident in incidents:
            print(f"- {incident}")
    else:
        print("- (none)")
    print()
    print("Available but inactive:")
    inactive = data.get("available_but_inactive") or []
    if inactive:
        for item in inactive:
            print(f"- {item.get('runtime_id')} ({item.get('reason') or 'inactive'})")
    else:
        print("- (none)")


def print_runtime_reputation(data: dict) -> None:
    reputation = data.get("reputation") or data
    print(f"runtime: {reputation.get('runtime_id')}")
    print(f"trust: {reputation.get('trust_score', 100)}")
    print(f"health: {reputation.get('health_status', 'healthy')}")
    print(f"total deliveries: {reputation.get('total_deliveries', 0)}")
    print(f"successful replies: {reputation.get('successful_replies', 0)}")
    print(f"empty replies: {reputation.get('empty_replies', 0)}")
    print(f"timeouts: {reputation.get('timeouts', 0)}")
    print(f"failures: {reputation.get('failures', 0)}")
    print(f"wrong identity: {reputation.get('wrong_identity', 0)}")
    print(f"suspicious outputs: {reputation.get('suspicious_outputs', 0)}")
    if reputation.get("incident_summary"):
        print(f"issue: {reputation.get('incident_summary')}")


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


def print_trace(data: dict) -> None:
    summary = data.get("summary") or {}
    print(f"Trace: {data.get('id')}")
    print(f"kind: {data.get('kind')}  outcome: {summary.get('outcome')}  failures: {summary.get('failure_count', 0)}")
    print(f"messages: {summary.get('message_count', 0)}  runtimes: {', '.join(summary.get('runtimes') or []) or '(none)'}")
    print()
    for item in data.get("timeline") or []:
        timestamp = item.get("timestamp") or "(no time)"
        actor = item.get("actor") or "system"
        target = item.get("target") or ""
        arrow = f" -> {target}" if target else ""
        print(f"{timestamp}  {item.get('event_type')}  {actor}{arrow}")
        print(f"  [{item.get('status')}] {item.get('summary')}")
    injections = data.get("memory_injections") or []
    if injections:
        print()
        print("Memory injections")
        for item in injections:
            print(f"- {item.get('message_id')}  {item.get('source')} -> {item.get('target')}")


def print_memory(data: dict) -> None:
    rows = data.get("memories", [])
    if not rows:
        print("No memory records.")
        return
    for item in rows:
        print(f"[{item.get('status')}] {item.get('memory_type')} {item.get('memory_id')}")
        print(f"  confidence: {item.get('confidence', 0)}  room: {item.get('room_name') or '(workspace)'}")
        print(f"  {item.get('content')}")
        print()


def print_proposals(data: dict) -> None:
    rows = data.get("proposals", [])
    if not rows:
        print("No proposals.")
        return
    print("Proposals")
    print()
    for item in rows:
        approval = "yes" if item.get("requires_approval") else "no"
        print(f"[{item.get('status')}] {item.get('proposal_id')}")
        print(f"  risk: {item.get('risk_level')}  type: {item.get('proposal_type')}  requires_approval: {approval}")
        print(f"  title: {item.get('title')}")
        print(f"  proposed_by: {item.get('proposed_by')}  created_at: {item.get('created_at')}")
        linked = []
        for key in ("room_id", "task_id", "goal_id"):
            if item.get(key):
                linked.append(f"{key}={item.get(key)}")
        if linked:
            print(f"  links: {', '.join(linked)}")
        if item.get("approval_reason"):
            print(f"  reason: {item.get('approval_reason')}")
        print()


def print_proposal(data: dict) -> None:
    proposal = data.get("proposal") or data
    print(f"proposal_id: {proposal.get('proposal_id')}")
    print(f"status: {proposal.get('status')}")
    print(f"type: {proposal.get('proposal_type')}")
    print(f"risk: {proposal.get('risk_level')}")
    print(f"requires_approval: {'yes' if proposal.get('requires_approval') else 'no'}")
    print(f"title: {proposal.get('title')}")
    print(f"summary: {proposal.get('summary')}")
    print(f"proposed_by: {proposal.get('proposed_by')}")
    print(f"approved_by: {proposal.get('approved_by') or '-'}")
    print(f"rejected_by: {proposal.get('rejected_by') or '-'}")
    print(f"executed_by: {proposal.get('executed_by') or '-'}")
    print(f"room_id: {proposal.get('room_id') or '-'}")
    print(f"task_id: {proposal.get('task_id') or '-'}")
    print(f"goal_id: {proposal.get('goal_id') or '-'}")
    print(f"approval_reason: {proposal.get('approval_reason')}")
    events = proposal.get("events") or data.get("events") or []
    if events:
        print()
        print("events:")
        for event in events:
            print(f"- {event.get('created_at')} {event.get('event_type')} by {event.get('actor')}")


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


def _wait_for_daemon_health(base: str, timeout_seconds: int, *, quiet: bool = False) -> bool:
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
    if not quiet:
        print(f"SynKraken did not become healthy within {timeout_seconds}s{detail}", file=sys.stderr)
    return False


def _config_path(value: str | None = None) -> Path:
    return Path(value or os.environ.get("SYNKRAKEN_CONFIG", "config.local.json")).expanduser().resolve()


def recover_runtime(base: str, wait_seconds: int = 15, *, announce: bool = True) -> bool:
    if _wait_for_daemon_health(base, 1, quiet=True):
        return True
    if announce:
        print("Daemon unavailable.")
        print("Attempting recovery...")
    try:
        service = runtime_service_for_platform()
        if not service.recover():
            if announce:
                print("Recovery failed.")
                print("Suggested action:")
                print("synkraken install")
            return False
    except RuntimeServiceError as exc:
        if announce:
            print(f"Recovery failed: {exc}")
            print("Suggested action:")
            print("synkraken install")
        return False
    healthy = _wait_for_daemon_health(base, wait_seconds, quiet=True)
    if announce:
        print("Recovery succeeded." if healthy else "Recovery failed.")
        if healthy:
            print("Status: Healthy.")
        else:
            print("Suggested action:")
            print("synkraken doctor")
    return healthy


def install_runtime(config_path: Path, base: str, wait_seconds: int) -> int:
    if not config_path.exists():
        print(f"Configuration not found: {config_path}", file=sys.stderr)
        print("Run `synkraken config` first, then `synkraken install`.", file=sys.stderr)
        return 1
    try:
        service = runtime_service_for_platform()
        print(f"Installing SynKraken for {service.platform_name}...")
        service.install(config_path)
    except RuntimeServiceError as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        return 1
    if not _wait_for_daemon_health(base, wait_seconds):
        print("Installation failed because SynKraken did not pass its health check.", file=sys.stderr)
        return 1
    print("SynKraken is installed and healthy.")
    return 0


def uninstall_runtime(*, remove_skills: bool = False) -> int:
    try:
        service = runtime_service_for_platform()
        service.uninstall()
    except RuntimeServiceError as exc:
        print(f"Uninstall failed: {exc}", file=sys.stderr)
        return 1
    print("SynKraken runtime integration removed.")
    print("Configuration, projects, knowledge, conversations, and database were preserved.")
    if remove_skills:
        run_uninstall()
    return 0


def print_runtime_status(base: str, *, raw: bool = False) -> int:
    try:
        service = runtime_service_for_platform()
        state = service.status()
    except RuntimeServiceError as exc:
        print(f"Runtime status unavailable: {exc}", file=sys.stderr)
        return 1
    health = None
    try:
        health = get_json(f"{base}/health")
    except Exception:
        pass
    payload = {
        "platform": state.platform,
        "installed": state.installed,
        "running": state.running,
        "healthy": bool(health and health.get("ok")),
        "uptime": format_uptime(health.get("started_at") if health else None),
        "url": base,
    }
    if raw:
        print(json.dumps(payload, indent=2))
    else:
        print("SynKraken Runtime")
        print()
        print(f"Platform:   {payload['platform']}")
        print(f"Service:    {'Running' if state.running else 'Stopped' if state.installed else 'Not installed'}")
        print(f"Health:     {'Healthy' if payload['healthy'] else 'Unavailable'}")
        print(f"Uptime:     {payload['uptime']}")
        print(f"Daemon URL: {base}")
    return 0 if payload["healthy"] else 1


def handle_lifecycle_command(action: str, base: str, wait_seconds: int = 15, *, raw: bool = False) -> int:
    if action == "status":
        return print_runtime_status(base, raw=raw)
    try:
        service = runtime_service_for_platform()
        state = service.status()
        if not state.installed:
            print("SynKraken is not installed.", file=sys.stderr)
            print("Run: synkraken install", file=sys.stderr)
            return 1
        getattr(service, action)()
    except RuntimeServiceError as exc:
        print(f"Could not {action} SynKraken: {exc}", file=sys.stderr)
        return 1
    if action in {"start", "restart"} and not _wait_for_daemon_health(base, wait_seconds):
        return 1
    print(f"SynKraken {'started' if action == 'start' else 'stopped' if action == 'stop' else 'restarted'}.")
    return 0


def doctor_runtime(config_path: Path, base: str) -> int:
    checks: list[tuple[str, bool, str, str]] = []
    checks.append(("Python", sys.version_info >= (3, 10), sys.version.split()[0], "Install Python 3.10 or newer."))
    try:
        service = runtime_service_for_platform()
        state = service.status()
        checks.append(("Runtime service", state.installed, "Running" if state.running else state.detail, "Run `synkraken install`."))
    except RuntimeServiceError as exc:
        checks.append(("Runtime service", False, str(exc), "Use Linux or macOS; Windows support is planned."))
    config: dict = {}
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)
        checks.append(("Config", True, str(config_path), ""))
    except Exception as exc:
        checks.append(("Config", False, str(exc), "Run `synkraken config`."))
    storage = (config.get("storage") or {}).get("sqlite_path") if config else None
    if storage:
        db_path = Path(str(storage)).expanduser()
        if not db_path.is_absolute():
            db_path = config_path.parent / db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(db_path) as connection:
                connection.execute("PRAGMA quick_check").fetchone()
            checks.append(("Database", True, str(db_path), ""))
        except Exception as exc:
            checks.append(("Database", False, str(exc), "Check database path permissions."))
    else:
        checks.append(("Database", False, "No database path configured", "Run `synkraken config`."))
    healthy = _wait_for_daemon_health(base, 1, quiet=True)
    host = str((config.get("server") or {}).get("host", "127.0.0.1"))
    port = int((config.get("server") or {}).get("port", 9460))
    port_ok = healthy
    detail = "Used by healthy SynKraken" if healthy else "Available"
    if not healthy:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind((host, port))
            port_ok = True
        except OSError as exc:
            port_ok = False
            detail = f"Unavailable: {exc}"
        finally:
            probe.close()
    checks.append(("Port", port_ok, f"{host}:{port} {detail}", "Stop the process using the configured port or change the port."))
    adapters = config.get("adapters") or {}
    enabled = [name for name, item in adapters.items() if isinstance(item, dict) and item.get("enabled", True)]
    missing_commands = []
    for name in enabled:
        command = adapters[name].get("command") or []
        executable = str(command[0]) if isinstance(command, list) and command else str(command) if command else ""
        if executable and not (Path(executable).expanduser().is_file() or shutil.which(executable)):
            missing_commands.append(name)
    providers_ok = bool(enabled) and not missing_commands
    provider_detail = f"{len(enabled)} configured"
    if missing_commands:
        provider_detail += f"; commands unavailable: {', '.join(missing_commands)}"
    checks.append(("Providers", providers_ok, provider_detail, "Run `synkraken config --rediscover`."))
    print("SynKraken Doctor")
    print()
    failed = False
    for name, ok, detail, remediation in checks:
        failed = failed or not ok
        print(f"{'OK' if ok else 'FAIL':<4} {name}: {detail}")
        if not ok and remediation:
            print(f"     Suggested action: {remediation}")
    return 1 if failed else 0


def add_lifecycle_parser(sub: argparse._SubParsersAction, action: str) -> None:
    help_text = {
        "start": "Start SynKraken",
        "stop": "Stop SynKraken",
        "restart": "Restart SynKraken",
        "status": "Show SynKraken runtime status",
    }[action]
    parser = sub.add_parser(action, help=help_text)
    parser.add_argument("target", nargs="?", choices=["daemon"], help="Optional explicit target")
    if action in {"start", "restart"}:
        parser.add_argument("--wait-seconds", type=int, default=15, help="Seconds to wait for daemon health")
    add_base_url_arg(parser)


def add_base_url_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=DEFAULT_BASE, help="Base URL for synkraken")
    parser.add_argument("--json", action="store_true", help="Print raw JSON output")


def add_remote_discovery_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--remote", metavar="HOST", help="Discover/configure runtimes over SSH on HOST")
    parser.add_argument("--remote-user", help="SSH username for --remote")
    parser.add_argument("--remote-port", type=int, default=22, help="SSH port for --remote")
    parser.add_argument("--ssh-identity-file", help="SSH private key file for --remote")
    parser.add_argument("--remote-working-dir", help="Working directory to use when running remote adapters")
    parser.add_argument("--remote-path", action="append", default=[], help="Extra remote PATH directory; repeat for multiple directories")
    parser.add_argument("--ssh-option", action="append", default=[], help="Extra ssh option; use --ssh-option=-o for option-like values")


def _remote_ssh_options(args: argparse.Namespace) -> list[str]:
    options = list(getattr(args, "ssh_option", []) or [])
    if options:
        return options
    defaults = ["-o", "BatchMode=yes"]
    if getattr(args, "ssh_identity_file", None):
        defaults.extend(["-o", "IdentitiesOnly=yes"])
    return defaults


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

    p_install = sub.add_parser("install", help="Install and start SynKraken for this platform")
    p_install.add_argument("--config", default=None, help="Configuration file path")
    p_install.add_argument("--wait-seconds", type=int, default=20, help="Seconds to wait for health validation")
    add_base_url_arg(p_install)

    for action in ("start", "stop", "restart", "status"):
        add_lifecycle_parser(sub, action)

    p_doctor = sub.add_parser("doctor", help="Check installation, runtime, database, port, config, and providers")
    p_doctor.add_argument("--config", default=None, help="Configuration file path")
    add_base_url_arg(p_doctor)

    p_health = sub.add_parser("health", help="Check bridge health")
    p_health.add_argument("scope", nargs="?", choices=["workforce"], help="Optional health scope")
    add_base_url_arg(p_health)

    p_agents = sub.add_parser("agents", help="List registered adapters")
    add_base_url_arg(p_agents)

    p_runtimes = sub.add_parser("runtimes", help="List runtime registry entries")
    add_base_url_arg(p_runtimes)

    p_runtime = sub.add_parser("runtime", help="Inspect one runtime or run runtime diagnostics")
    p_runtime.add_argument("runtime_args", nargs="+", help="Runtime id, 'doctor', or 'health <id>'")
    add_base_url_arg(p_runtime)

    p_workforce = sub.add_parser("workforce", help="Show workforce reputation and health")
    add_base_url_arg(p_workforce)

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

    p_retry = sub.add_parser("retry", help="Retry a failed delivery or dead letter")
    p_retry.add_argument("kind", choices=["delivery", "dead-letter"])
    p_retry.add_argument("id", type=int)
    add_base_url_arg(p_retry)

    p_tui = sub.add_parser("tui", help="Launch the interactive TUI")
    p_tui.add_argument('--banner-only', action='store_true', help='Print banner and exit')
    add_base_url_arg(p_tui)

    p_web = sub.add_parser("web", help="Launch the local web command deck")
    p_web.add_argument("--host", default="127.0.0.1", help="Host for the local web UI")
    p_web.add_argument("--port", type=int, default=9461, help="Port for the local web UI")
    p_web.add_argument("--daemon-url", default=DEFAULT_BASE, help="Existing synkraken daemon base URL")

    p_discover = sub.add_parser("discover", help="Discover local AI runtimes without changing config")
    p_discover.add_argument("--json", action="store_true", help="Print raw JSON output")
    p_discover.add_argument("--verbose", action="store_true", help="Print full command paths and probe output")
    add_remote_discovery_args(p_discover)

    p_config = sub.add_parser(
        "config",
        aliases=["configure"],
        help="Interactive setup: detect local or SSH runtimes, install the bridge skill, create config.local.json",
    )
    p_config.set_defaults(command="config")
    p_config.add_argument("--rediscover", action="store_true", help="Rescan runtimes and merge them into config.local.json")
    p_config.add_argument("--install-skills", action="store_true", help="Install bridge skills for configured workers")
    add_remote_discovery_args(p_config)
    p_uninstall = sub.add_parser("uninstall", help="Remove runtime integration while preserving user data")
    p_uninstall.add_argument("--remove-skills", action="store_true", help="Also run the interactive bridge-skill cleanup")

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

    p_trace = sub.add_parser("trace", help="Show an operational trace")
    p_trace.add_argument("id", help="Conversation, task, goal, decision, or handoff id")
    add_base_url_arg(p_trace)

    p_rooms = sub.add_parser("rooms", help="Create, manage, list, or inspect rooms")
    p_rooms.add_argument(
        "action",
        nargs="?",
        choices=["list", "create", "delete", "members", "add", "remove", "transcript", "send", "preset", "search", "summarize"],
        help="Room action",
    )
    p_rooms.add_argument("name", nargs="?", help="Room name")
    p_rooms.add_argument("values", nargs="*", help="Workers, message, or search query")
    p_rooms.add_argument("--preset", choices=["review", "planning", "ops"], help="Room preset")
    p_rooms.add_argument("--limit", type=int, default=50)
    add_base_url_arg(p_rooms)

    p_memory = sub.add_parser("memory", help="List or govern shared workforce memory")
    p_memory.add_argument("action", nargs="?", choices=["list", "pending", "note", "approve", "reject", "archive", "edit"], default="list")
    p_memory.add_argument("id", nargs="?", help="Memory id for approve/reject/archive")
    p_memory.add_argument("--title", default=None, help="Memory note title")
    p_memory.add_argument("--body", default=None, help="Memory note body")
    p_memory.add_argument("--content", default=None, help="Replacement memory content for edit")
    p_memory.add_argument("--type", dest="memory_type", default=None, help="Replacement memory type for edit")
    p_memory.add_argument("--scope-type", default="global", help="Memory scope type")
    p_memory.add_argument("--scope-id", default=None, help="Memory scope id")
    p_memory.add_argument("--importance", default="medium", help="Memory importance")
    p_memory.add_argument("--confidence", type=int, default=None, help="Replacement confidence for edit")
    p_memory.add_argument("--status", default=None, help="Filter by status")
    p_memory.add_argument("--room", default=None, help="Filter by room")
    p_memory.add_argument("--limit", type=int, default=50)
    add_base_url_arg(p_memory)

    p_proposals = sub.add_parser("proposals", help="List proposals")
    p_proposals.add_argument("scope", nargs="?", choices=["pending"], help="Optional proposal scope")
    p_proposals.add_argument("--status", default=None, help="Filter by status")
    p_proposals.add_argument("--room", default=None, help="Filter by room")
    p_proposals.add_argument("--limit", type=int, default=50)
    add_base_url_arg(p_proposals)

    p_proposal = sub.add_parser("proposal", help="Inspect or govern a proposal")
    p_proposal.add_argument("action", nargs="?", help="Proposal id or action: create/approve/reject/cancel/execute")
    p_proposal.add_argument("id", nargs="?", help="Proposal id for approve/reject/cancel/execute")
    p_proposal.add_argument("--type", dest="proposal_type", help="Proposal type for create")
    p_proposal.add_argument("--title", help="Proposal title for create")
    p_proposal.add_argument("--summary", default="", help="Proposal summary for create")
    p_proposal.add_argument("--details", default="", help="Proposal details for create")
    p_proposal.add_argument("--proposed-by", default="operator", help="Proposal actor")
    p_proposal.add_argument("--room", default=None, help="Linked room")
    p_proposal.add_argument("--task", default=None, help="Linked task")
    p_proposal.add_argument("--goal", default=None, help="Linked goal")
    p_proposal.add_argument("--reason", default="", help="Reject/cancel reason")
    add_base_url_arg(p_proposal)

    p_incident = sub.add_parser("incident", help="Show latest incident")
    p_incident.add_argument("action", nargs="?", choices=["latest"], default="latest", help="Show latest failure")
    add_base_url_arg(p_incident)

    return parser


def _print_no_command() -> None:
    print("SYNKRAKEN needs a command.\n")
    print("First-time setup:")
    print("  synkraken config            # configure local or SSH workers")
    print("  synkraken configure         # same as synkraken config")
    print("  synkraken install           # install and start SynKraken\n")
    print("Day-to-day:")
    print("  synkraken start             # start SynKraken")
    print("  synkraken status            # runtime and health status")
    print("  synkraken tui               # open the TUI dashboard")
    print("  synkraken web               # open the local web command deck")
    print("  synkraken health            # is the daemon ok?")
    print("  synkraken agents            # which adapters are configured?")
    print("  synkraken runtimes          # show runtime registry")
    print("  synkraken runtime doctor    # runtime diagnostics")
    print("  synkraken send hermes 'hi'  # message a single agent\n")
    print("Tear-down:")
    print("  synkraken uninstall         # remove runtime integration, preserve data\n")
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
        run_setup(
            rediscover=args.rediscover,
            remote_host=args.remote,
            remote_user=args.remote_user,
            remote_port=args.remote_port,
            ssh_identity_file=args.ssh_identity_file,
            remote_working_dir=args.remote_working_dir,
            remote_path=args.remote_path,
            ssh_options=_remote_ssh_options(args),
            prompt_discovery=not bool(args.remote),
        )
        return
    if args.command == 'discover':
        if args.remote:
            runtimes = discover_remote_runtimes(
                remote_host=args.remote,
                remote_user=args.remote_user,
                remote_port=args.remote_port,
                ssh_identity_file=args.ssh_identity_file,
                remote_working_dir=args.remote_working_dir,
                remote_path=args.remote_path,
                ssh_options=_remote_ssh_options(args),
                include_probe_output=args.verbose and not args.json,
            )
        else:
            runtimes = discover_local_runtimes(include_probe_output=args.verbose and not args.json)
        data = {"runtimes": runtimes}
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_discovery(data, verbose=args.verbose)
        return
    if args.command == 'uninstall':
        raise SystemExit(uninstall_runtime(remove_skills=args.remove_skills))
    if args.command == 'install':
        config_path = _config_path(args.config)
        if not config_path.exists() and args.config is None:
            print("No configuration found. Starting setup...")
            run_setup()
        raise SystemExit(install_runtime(config_path, args.url.rstrip("/"), args.wait_seconds))
    if args.command == 'doctor':
        raise SystemExit(doctor_runtime(_config_path(args.config), args.url.rstrip("/")))
    if args.command == 'tui':
        if args.banner_only:
            print_logo()
            print()
            return
        base = args.url.rstrip("/")
        print("Checking SynKraken runtime...")
        if not recover_runtime(base, announce=False):
            print("Starting SynKraken failed.", file=sys.stderr)
            print("Run: synkraken install", file=sys.stderr)
            raise SystemExit(1)
        print("Connected.")
        run_tui(base)
        return
    if args.command == 'web':
        if not recover_runtime(args.daemon_url.rstrip("/"), announce=False):
            print("SynKraken runtime is unavailable. Run: synkraken install", file=sys.stderr)
            raise SystemExit(1)
        serve_web(host=args.host, port=args.port, daemon_url=args.daemon_url)
        return
    base = args.url.rstrip("/")
    if args.command in {"start", "stop", "restart", "status"}:
        raise SystemExit(handle_lifecycle_command(args.command, base, getattr(args, "wait_seconds", 15), raw=args.json))
    try:
        if args.command == "health":
            if not _wait_for_daemon_health(base, 1, quiet=True) and not recover_runtime(base):
                raise SystemExit(1)
            if args.scope == "workforce":
                data = get_json(f"{base}/v1/workforce/health")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print_workforce_health(data)
                return
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
        if args.command == "workforce":
            data = get_json(f"{base}/v1/workforce")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_workforce(data)
            return
        if args.command == "runtime":
            runtime_args = list(args.runtime_args)
            if runtime_args == ["doctor"]:
                data = _runtime_doctor_data(base)
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print_runtime_doctor(data)
                return
            if len(runtime_args) == 2 and runtime_args[0] == "health":
                data = get_json(f"{base}/v1/runtime/{runtime_args[1]}/reputation")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print_runtime_reputation(data)
                return
            if len(runtime_args) != 1:
                raise ValueError("usage: synkraken runtime <id>|doctor|health <id>")
            runtime = _runtime_detail_data(base, runtime_args[0])
            if not runtime:
                raise ValueError(f"runtime not found: {runtime_args[0]}")
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
        if args.command == "retry":
            if args.kind == "delivery":
                result = post_json(f"{base}/v1/deliveries/{args.id}/retry", {"actor": "operator"})
            else:
                result = post_json(f"{base}/v1/dead-letters/{args.id}/replay", {"actor": "operator"})
            print_result(result, raw=args.json)
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
        if args.command == "trace":
            data = get_json(f"{base}/v1/trace/{args.id}")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_trace(data)
            return
        if args.command == "rooms":
            action = args.action or "list"
            name = str(args.name or "").strip().lower()
            quoted_name = urllib.parse.quote(name)
            if action == "create":
                if not name:
                    raise ValueError("usage: synkraken rooms create <name>")
                data = post_json(f"{base}/v1/rooms", {"name": name, "description": "", "members": []})
                print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else f"Room created: {name}")
                return
            if action == "delete":
                if not name:
                    raise ValueError("usage: synkraken rooms delete <name>")
                data = delete_json(f"{base}/v1/rooms/{quoted_name}")
                print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else f"Room deleted: {name}")
                return
            if action == "members":
                if not name:
                    raise ValueError("usage: synkraken rooms members <name>")
                data = get_json(f"{base}/v1/rooms/{quoted_name}/members")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    members = [str(member.get("adapter_id")) for member in data.get("members", [])]
                    print(f"{name}: {', '.join(members) if members else '(no workers)'}")
                return
            if action in {"add", "remove"}:
                if not name or not args.values:
                    raise ValueError(f"usage: synkraken rooms {action} <name> <worker...>")
                for worker in args.values:
                    worker_id = str(worker).lstrip("@").strip()
                    worker_path = urllib.parse.quote(worker_id)
                    if action == "add":
                        post_json(f"{base}/v1/rooms/{quoted_name}/members", {"adapter_id": worker_id, "actor": "operator"})
                    else:
                        delete_json(f"{base}/v1/rooms/{quoted_name}/members/{worker_path}")
                print(f"{'Added to' if action == 'add' else 'Removed from'} {name}: {', '.join(args.values)}")
                return
            if action == "transcript":
                if not name:
                    raise ValueError("usage: synkraken rooms transcript <name>")
                data = get_json(f"{base}/v1/rooms/{quoted_name}/messages?limit={args.limit}")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    messages = data.get("messages", [])
                    if not messages:
                        print(f"No messages in room: {name}")
                    for message in messages:
                        print(f"{message.get('timestamp')} {message.get('source')}: {message.get('body')}")
                return
            if action == "send":
                if not name or not args.values:
                    raise ValueError('usage: synkraken rooms send <name> "<message>"')
                body = " ".join(args.values).strip()
                data = post_json(f"{base}/v1/messages", {"source": "operator", "target": f"room:{name}", "body": body})
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    deliveries = data.get("deliveries", [])
                    failures = data.get("dead_letters", [])
                    print(f"Room dispatch: {name} targets={len(deliveries) + len(failures)} delivered={len(deliveries)} failed={len(failures)}")
                return
            if args.action == "preset":
                preset = args.preset or args.name
                if not preset:
                    raise ValueError("usage: synkraken rooms preset <name> [--preset review|planning|ops]")
                name = args.name or preset
                data = post_json(f"{base}/v1/rooms/preset", {"name": name, "preset": preset, "actor": "operator"})
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print(f"room preset applied: {data.get('preset')} -> {data.get('room', {}).get('name')}")
                return
            if args.action == "search":
                query_text = " ".join(args.values).strip()
                if not args.name or not query_text:
                    raise ValueError("usage: synkraken rooms search <room> <query>")
                query = urllib.parse.quote(query_text)
                data = get_json(f"{base}/v1/rooms/{args.name}/messages?q={query}&limit={args.limit}")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    for message in data.get("messages", []):
                        print(f"{message.get('timestamp')} {message.get('source')}: {message.get('body')}")
                return
            if args.action == "summarize":
                if not args.name:
                    raise ValueError("usage: synkraken rooms summarize <room>")
                data = post_json(f"{base}/v1/rooms/{args.name}/summary", {"actor": "operator", "limit": args.limit})
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print(data.get("summary") or "")
                return
            data = get_json(f"{base}/v1/rooms")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                for room in data.get("rooms", []):
                    print(f"{room.get('name')} members={room.get('member_count')} last={room.get('last_activity') or room.get('created_at')}")
            return
        if args.command == "memory":
            if args.action in {"list", "pending"}:
                query = [f"limit={args.limit}"]
                if args.action == "pending":
                    query.append("status=proposed")
                elif args.status:
                    query.append(f"status={urllib.parse.quote(args.status)}")
                if args.room:
                    query.append(f"room={urllib.parse.quote(args.room)}")
                data = get_json(f"{base}/v1/memory?{'&'.join(query)}")
                if args.json:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    print_memory(data)
                return
            if args.action == "note":
                if not args.title or not args.body:
                    raise ValueError("memory note requires --title and --body")
                result = post_json(f"{base}/v1/memory/operator-note", {
                    "title": args.title,
                    "body": args.body,
                    "scope_type": args.scope_type,
                    "scope_id": args.scope_id,
                    "importance": args.importance,
                    "actor": "operator",
                })
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return
            if not args.id:
                raise ValueError(f"memory id required for {args.action}")
            payload = {"actor": "operator"}
            if args.action == "edit":
                if args.content is None and args.memory_type is None and args.confidence is None:
                    raise ValueError("memory edit requires --content, --type, or --confidence")
                if args.content is not None:
                    payload["content"] = args.content
                if args.memory_type is not None:
                    payload["memory_type"] = args.memory_type
                if args.confidence is not None:
                    payload["confidence"] = args.confidence
            result = post_json(f"{base}/v1/memory/{args.id}/{args.action}", payload)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return
        if args.command == "proposals":
            if args.scope == "pending":
                data = get_json(f"{base}/v1/proposals/pending")
            else:
                query = [f"limit={args.limit}"]
                if args.status:
                    query.append(f"status={urllib.parse.quote(args.status)}")
                if args.room:
                    query.append(f"room={urllib.parse.quote(args.room)}")
                data = get_json(f"{base}/v1/proposals?{'&'.join(query)}")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_proposals(data)
            return
        if args.command == "proposal":
            action = args.action
            if action == "create":
                if not args.proposal_type or not args.title:
                    raise ValueError("proposal create requires --type and --title")
                payload = {
                    "proposal_type": args.proposal_type,
                    "title": args.title,
                    "summary": args.summary,
                    "details": args.details,
                    "proposed_by": args.proposed_by,
                    "room_id": args.room,
                    "task_id": args.task,
                    "goal_id": args.goal,
                }
                result = post_json(f"{base}/v1/proposal/create", payload)
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print_proposal(result)
                return
            if action in {"approve", "reject", "cancel", "execute"}:
                if not args.id:
                    raise ValueError(f"proposal {action} requires an id")
                payload = {"proposal_id": args.id, "actor": "operator"}
                if args.reason:
                    payload["reason"] = args.reason
                result = post_json(f"{base}/v1/proposal/{action}", payload)
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print_proposal(result)
                return
            proposal_id = action
            if not proposal_id:
                raise ValueError("usage: synkraken proposal <id>|create|approve|reject|cancel|execute")
            data = get_json(f"{base}/v1/proposal/{proposal_id}")
            if args.json:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print_proposal(data)
            return
        if args.command == "incident":
            data = get_json(f"{base}/v1/incident/latest")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return
        raise ValueError(f"Unknown command: {args.command}")
    except urllib.error.HTTPError as exc:
        print(_http_error_message(exc), file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
