#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse
import json
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://127.0.0.1:9460"
CONTROL_TIMEOUT = 20
DISCOVERY_TIMEOUT = 10
WORKFORCE_TIMEOUT = 10


def _json(url: str, payload: dict | None = None, timeout: int = 180) -> dict:
    if payload is None:
        with urlopen(url, timeout=timeout) as resp:
            return json.load(resp)
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _enabled_agents(base: str) -> list[dict]:
    payload = _json(f"{base}/v1/agents", timeout=DISCOVERY_TIMEOUT)
    rows = payload.get("agents")
    if not isinstance(rows, list):
        raise ValueError("/v1/agents response did not include an agents list")
    return [
        agent for agent in rows
        if isinstance(agent, dict) and agent.get("adapter_id") and bool(agent.get("enabled"))
    ]


def _wait_for_health(base: str, timeout_seconds: int) -> tuple[bool, dict, str]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    last_error = ""
    while time.monotonic() < deadline:
        try:
            health = _json(f"{base}/health", timeout=5)
            if health.get("ok"):
                return True, health, ""
            last_error = "health returned NOT OK"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    return False, {}, last_error


def _restart_daemon(base: str, wait_seconds: int) -> tuple[bool, str]:
    proc = subprocess.run(
        ["synkraken", "restart", "daemon", "--url", base, "--wait-seconds", str(wait_seconds)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    return proc.returncode == 0, output


_IDENTITY_MARKER_RE = re.compile(r"\b(?:ADAPTER_OK|BROADCAST_OK):\s*([^\s,.;:]+)")


def _classify_delivery(delivery: dict, expected: str | None = None, expected_agent_id: str | None = None) -> str:
    status = str(delivery.get("status") or "")
    body = delivery.get("body")
    text = "" if body is None else str(body)
    if status == "timeout":
        return "timeout"
    if status == "empty_reply" or not text.strip():
        return "empty_reply"
    if status == "failed" or not delivery.get("ok", False):
        return "failed"
    if delivery.get("quality") == "suspicious_output":
        return "unexpected_output"
    if expected is not None:
        if expected in text:
            return "ok"
        marker_ids = _IDENTITY_MARKER_RE.findall(text)
        if expected_agent_id is not None and any(agent_id != expected_agent_id for agent_id in marker_ids):
            return "wrong_identity"
        return "unexpected_output"
    return "ok"


def _send(base: str, target: str, body: str, conversation_id: str | None = None) -> dict:
    payload = {
        "source": "cli-stress",
        "target": target,
        "body": body,
        "conversation_id": conversation_id,
    }
    return _json(f"{base}/v1/messages", payload)


def _test_decision(base: str, run_id: str, agents: list[dict]) -> tuple[dict, str]:
    linked_runtime_ids = [str(agent["adapter_id"]) for agent in agents]
    result = _json(f"{base}/v1/decision/propose", {
        "id": f"cli-stress-decision-{run_id}",
        "title": "CLI stress test decision",
        "summary": "Record that the CLI stress test exercised decision creation.",
        "reason": "The repeatable stress runner verifies flight recorder APIs.",
        "proposed_by": "cli-stress",
        "linked_runtime_ids": linked_runtime_ids,
    }, timeout=CONTROL_TIMEOUT)
    decision = result.get("decision") or {}
    return result, str(decision.get("id") or decision.get("decision_id") or "")


def _test_handoff(base: str, run_id: str, agents: list[dict], decision_id: str) -> tuple[dict, str]:
    to_agent = str((agents[0] if agents else {}).get("adapter_id") or "operator")
    result = _json(f"{base}/v1/handoff", {
        "id": f"cli-stress-handoff-{run_id}",
        "from_agent": "cli-stress",
        "to_agent": to_agent,
        "summary": "CLI stress test handoff record.",
        "recommended_next_step": "Review the generated CLI stress report.",
        "linked_decision_ids": [decision_id] if decision_id else [],
    }, timeout=CONTROL_TIMEOUT)
    handoff = result.get("handoff") or {}
    return result, str(handoff.get("id") or handoff.get("handoff_id") or "")


def _markdown_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("\n", " ") for value in row) + " |")
    return lines


def _write_report(path: Path, report: dict) -> None:
    lines = [
        "# CLI Stress Test Report",
        "",
        f"- run_id: `{report['run_id']}`",
        f"- daemon: `{report['daemon_status']}`",
        f"- final: `{report['final_status']}`",
        f"- dead letters: `{report['dead_letter_count']}`",
        "",
        "## Agents Tested",
        "",
    ]
    agents = report["agents"]
    if agents:
        lines.extend(f"- `{agent['adapter_id']}` ({agent.get('runtime_name') or agent['adapter_id']})" for agent in agents)
    else:
        lines.append("- none")
    lines.extend(["", "## Direct Sends", ""])
    lines.extend(_markdown_table(
        ["agent", "classification", "status", "quality", "duration_ms", "preview"],
        report["direct_rows"],
    ))
    lines.extend(["", "## Broadcast", ""])
    lines.extend(_markdown_table(
        ["agent", "classification", "status", "quality", "duration_ms", "preview"],
        report["broadcast_rows"],
    ))
    lines.extend(["", "## Runtime Reputation", ""])
    lines.extend(_markdown_table(
        ["agent", "trust", "health", "issue"],
        report.get("reputation_rows") or [],
    ))
    lines.extend([
        "",
        "## Classification Legend",
        "",
        "- `ok`: reply included the expected identity marker for the delivery target.",
        "- `wrong_identity`: reply included `ADAPTER_OK` or `BROADCAST_OK` with a different adapter id.",
        "- `unexpected_output`: reply did not match the expected identity marker.",
        "- `empty_reply`: delivery succeeded but returned no body.",
        "- `timeout`: delivery timed out.",
        "- `failed`: delivery failed or was missing.",
        "",
        "## Control Plane",
        "",
        f"- decisions: `{report['decision_result']}`",
        f"- handoffs: `{report['handoff_result']}`",
        f"- replay: `{report['replay_result']}`",
        f"- incident: `{report['incident_result']}`",
        "",
        "## Notes",
        "",
    ])
    for note in report["notes"]:
        lines.append(f"- {note}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable SynKraken CLI stress checks.")
    parser.add_argument("--url", default=DEFAULT_BASE, help="Daemon base URL")
    parser.add_argument("--skip-restart", action="store_true", help="Do not run `synkraken restart daemon` first")
    parser.add_argument("--wait-seconds", type=int, default=15, help="Seconds to wait for daemon health")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    notes: list[str] = []

    if not args.skip_restart:
        restarted, output = _restart_daemon(base, args.wait_seconds)
        notes.append(f"restart: {'ok' if restarted else 'failed'}")
        if output:
            notes.append(f"restart output: {output[:300]}")
        if not restarted:
            report_path = ROOT / "audits" / f"cli-stress-{run_id}" / "report.md"
            _write_report(report_path, {
                "run_id": run_id,
                "daemon_status": "restart_failed",
                "final_status": "FAIL",
                "dead_letter_count": 0,
                "agents": [],
                "direct_rows": [],
                "broadcast_rows": [],
                "decision_result": "skipped",
                "handoff_result": "skipped",
                "replay_result": "skipped",
                "incident_result": "skipped",
                "notes": notes,
            })
            print(f"CLI stress test: FAIL")
            print(f"report: {report_path}")
            return 1

    healthy, health, health_error = _wait_for_health(base, args.wait_seconds)
    if not healthy:
        report_path = ROOT / "audits" / f"cli-stress-{run_id}" / "report.md"
        _write_report(report_path, {
            "run_id": run_id,
            "daemon_status": f"unhealthy: {health_error}",
            "final_status": "FAIL",
            "dead_letter_count": 0,
            "agents": [],
            "direct_rows": [],
            "broadcast_rows": [],
            "decision_result": "skipped",
            "handoff_result": "skipped",
            "replay_result": "skipped",
            "incident_result": "skipped",
            "notes": notes,
        })
        print("CLI stress test: FAIL")
        print(f"report: {report_path}")
        return 1

    final_status = "PASS"
    try:
        agents = _enabled_agents(base)
        if not agents:
            report_path = ROOT / "audits" / f"cli-stress-{run_id}" / "report.md"
            notes.append("/v1/agents returned no enabled adapter agents")
            _write_report(report_path, {
                "run_id": run_id,
                "daemon_status": "ok" if health.get("ok") else "not_ok",
                "final_status": "FAIL",
                "dead_letter_count": 0,
                "agents": [],
                "direct_rows": [],
                "broadcast_rows": [],
                "reputation_rows": [],
                "decision_result": "skipped",
                "handoff_result": "skipped",
                "replay_result": "skipped",
                "incident_result": "skipped",
                "notes": notes,
            })
            print("CLI stress test: FAIL")
            print(f"report: {report_path}")
            return 1

        direct_rows: list[list[object]] = []
        reputation_rows: list[list[object]] = []
        for agent in agents:
            agent_id = str(agent["adapter_id"])
            expected = f"ADAPTER_OK: {agent_id}"
            result = _send(base, agent_id, f"Reply exactly: {expected}")
            delivery = (result.get("deliveries") or [{}])[0]
            classification = _classify_delivery(delivery, expected=expected, expected_agent_id=agent_id)
            if classification != "ok":
                final_status = "DEGRADED"
            direct_rows.append([
                agent_id,
                classification,
                delivery.get("status", ""),
                delivery.get("quality", ""),
                delivery.get("duration_ms", ""),
                (delivery.get("body") or delivery.get("error") or "")[:80],
            ])

        broadcast_rows: list[list[object]] = []
        if agents:
            broadcast = _send(base, "broadcast", "CLI stress broadcast: reply briefly with BROADCAST_OK and your agent id.")
            deliveries = broadcast.get("deliveries") or []
            seen = set()
            for delivery in deliveries:
                agent_id = str(delivery.get("adapter_id") or delivery.get("delivery_target") or "")
                seen.add(agent_id)
                expected = f"BROADCAST_OK: {agent_id}"
                classification = _classify_delivery(delivery, expected=expected, expected_agent_id=agent_id)
                if classification != "ok":
                    final_status = "DEGRADED"
                broadcast_rows.append([
                    agent_id,
                    classification,
                    delivery.get("status", ""),
                    delivery.get("quality", ""),
                    delivery.get("duration_ms", ""),
                    (delivery.get("body") or delivery.get("error") or "")[:80],
                ])
            missing = sorted(str(agent["adapter_id"]) for agent in agents if str(agent["adapter_id"]) not in seen)
            for agent_id in missing:
                final_status = "DEGRADED"
                broadcast_rows.append([agent_id, "failed", "missing_delivery", "", "", ""])
        else:
            broadcast_rows = []

        decision_result = "failed"
        handoff_result = "failed"
        replay_result = "failed"
        incident_result = "failed"
        decision_id = ""
        handoff_id = ""
        try:
            _decision, decision_id = _test_decision(base, run_id, agents)
            decision_result = "ok" if decision_id else "failed"
        except Exception as exc:
            notes.append(f"decision error: {exc}")
        try:
            _handoff, handoff_id = _test_handoff(base, run_id, agents, decision_id)
            handoff_result = "ok" if handoff_id else "failed"
        except Exception as exc:
            notes.append(f"handoff error: {exc}")
        replay_target = handoff_id or decision_id
        if replay_target:
            try:
                replay = _json(f"{base}/v1/replay/{replay_target}", timeout=CONTROL_TIMEOUT)
                replay_result = "ok" if replay.get("kind") in {"handoff", "decision"} else "failed"
            except Exception as exc:
                notes.append(f"replay error: {exc}")
        try:
            incident = _json(f"{base}/v1/incident/latest", timeout=CONTROL_TIMEOUT)
            incident_result = "ok" if "incident" in incident else "failed"
        except Exception as exc:
            notes.append(f"incident error: {exc}")

        if any(value != "ok" for value in (decision_result, handoff_result, replay_result, incident_result)):
            final_status = "FAIL"

        try:
            dead_letter_count = int(_json(f"{base}/v1/flight", timeout=CONTROL_TIMEOUT).get("dead_letters") or 0)
        except Exception:
            dead_letter_count = len(_json(f"{base}/v1/dead-letters?limit=100", timeout=CONTROL_TIMEOUT).get("dead_letters") or [])

        try:
            workforce = _json(f"{base}/v1/workforce", timeout=WORKFORCE_TIMEOUT)
            for row in workforce.get("workforce") or []:
                reputation = row.get("reputation") or {}
                reputation_rows.append([
                    row.get("runtime_id") or row.get("adapter_id") or "",
                    reputation.get("trust_score", ""),
                    reputation.get("health_status", ""),
                    reputation.get("incident_summary") or "",
                ])
        except Exception as exc:
            notes.append(f"workforce reputation error: {exc}")

        report_path = ROOT / "audits" / f"cli-stress-{run_id}" / "report.md"
        _write_report(report_path, {
            "run_id": run_id,
            "daemon_status": "ok" if health.get("ok") else "not_ok",
            "final_status": final_status,
            "dead_letter_count": dead_letter_count,
            "agents": agents,
            "direct_rows": direct_rows,
            "broadcast_rows": broadcast_rows,
            "reputation_rows": reputation_rows,
            "decision_result": decision_result,
            "handoff_result": handoff_result,
            "replay_result": replay_result,
            "incident_result": incident_result,
            "notes": notes or ["none"],
        })
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        report_path = ROOT / "audits" / f"cli-stress-{run_id}" / "report.md"
        _write_report(report_path, {
            "run_id": run_id,
            "daemon_status": "ok",
            "final_status": "FAIL",
            "dead_letter_count": 0,
            "agents": [],
            "direct_rows": [],
            "broadcast_rows": [],
            "decision_result": "failed",
            "handoff_result": "failed",
            "replay_result": "failed",
            "incident_result": "failed",
            "notes": notes + [f"fatal error: {exc}"],
        })
        print("CLI stress test: FAIL")
        print(f"report: {report_path}")
        return 1

    print(f"CLI stress test: {final_status}")
    print(f"report: {report_path}")
    return 0 if final_status in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
