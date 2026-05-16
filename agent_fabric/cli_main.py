from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from .branding import LOGO, NAME, TAGLINE
from .setup_mode import run_setup
from .tui import run_tui

DEFAULT_BASE = os.environ.get("AGENT_FABRIC_URL", "http://127.0.0.1:9460")


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
        print(f"{marker(enabled)} {runtime_name:<10} [{adapter_id}]  type={adapter_type}  enabled={str(enabled).lower()}")


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
        print(f"{marker(ok)} {label} [{delivery.get('adapter_id', 'unknown')}]  attempts={delivery.get('attempts', 1)}  duration_ms={delivery.get('duration_ms')}")
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


def add_base_url_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=DEFAULT_BASE, help="Base URL for agent-fabric")
    parser.add_argument("--json", action="store_true", help="Print raw JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synkraken",
        description="SYNKRAKEN is a local operator console for the agent-fabric bridge.",
        epilog=(
            "Examples:\n"
            "  synkraken tui\n"
            "  synkraken health\n"
            "  synkraken agents\n"
            "  synkraken send hermes \"Reply with exactly: HELLO\"\n"
            "  synkraken config"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_health = sub.add_parser("health", help="Check bridge health")
    add_base_url_arg(p_health)

    p_agents = sub.add_parser("agents", help="List registered adapters")
    add_base_url_arg(p_agents)

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

    sub.add_parser("config", help="Run interactive setup mode")

    return parser


def _print_no_command() -> None:
    print("SYNKRAKEN needs a command.\n")
    print("Start here:")
    print("  synkraken tui")
    print("  synkraken health")
    print("  synkraken agents")
    print("  synkraken send hermes \"Reply with exactly: HELLO\"")
    print("  synkraken config\n")
    print("For full help:")
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
    if args.command in ("tui", "config"):
        if args.command == 'config':
            print(LOGO)
            print(NAME)
            print(TAGLINE)
            print()
            run_setup()
            return
        if args.banner_only:
            print(LOGO)
            print(NAME)
            print(TAGLINE)
            print()
            return
        run_tui()
        return
    base = args.url.rstrip("/")
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
