from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:9460"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send messages through agent-fabric")
    parser.add_argument("target", help="Target adapter id or 'broadcast'")
    parser.add_argument("message", nargs="?", help="Message body. If omitted, stdin is used.")
    parser.add_argument("--source", default="operator", help="Logical source label")
    parser.add_argument("--subject", default=None, help="Optional subject")
    parser.add_argument("--priority", default="normal", help="Priority label")
    parser.add_argument("--conversation-id", default=None, help="Optional conversation id")
    parser.add_argument("--url", default=os.environ.get("AGENT_FABRIC_URL", DEFAULT_BASE), help="Base URL for agent-fabric")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON response")
    parser.add_argument("--health", action="store_true", help="Check bridge health and exit")
    parser.add_argument("--agents", action="store_true", help="List bridge adapters and exit")
    return parser


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


def print_agents(data: dict) -> None:
    agents = data.get("agents", [])
    for agent in agents:
        adapter_id = agent.get("adapter_id", "unknown")
        adapter_type = agent.get("type", "unknown")
        enabled = agent.get("enabled", False)
        print(f"{adapter_id}\t{adapter_type}\tenabled={enabled}")


def print_result(data: dict, raw: bool) -> None:
    if raw:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    message = data.get("message", {})
    print(f"conversation_id: {message.get('conversation_id', '')}")
    print(f"message_id: {message.get('message_id', '')}")
    deliveries = data.get("deliveries", [])
    if not deliveries:
        print("no deliveries")
    for delivery in deliveries:
        print(f"--- {delivery.get('adapter_id', 'unknown')} ---")
        print(f"ok: {delivery.get('ok')}")
        if delivery.get("error"):
            print(f"error: {delivery.get('error')}")
        body = (delivery.get("body") or "").strip()
        print(body)
    dead_letters = data.get("dead_letters", [])
    if dead_letters:
        print("dead_letters:")
        for item in dead_letters:
            print(json.dumps(item, ensure_ascii=False))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    base = args.url.rstrip("/")
    try:
        if args.health:
            print(json.dumps(get_json(f"{base}/health"), indent=2, ensure_ascii=False))
            return
        if args.agents:
            print_agents(get_json(f"{base}/v1/agents"))
            return
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
        print_result(result, raw=args.raw)
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
