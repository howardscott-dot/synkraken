---
name: agent-fabric-bridge
description: "Use agent-fabric to message other local AI runtimes."
version: 1.1.0
author: Howard Scott + CTO
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agent-fabric, bridge, local-agents, orchestration, messaging]
    related_skills: []
---

# Agent Fabric Bridge

Use this skill when you need to send a structured message to another local agent runtime through `agent-fabric`.

This skill is for **inter-agent messaging**, not for ordinary user replies.

## When to Use

Use this skill when:
- you need to talk to another agent runtime on the same machine
- you need to send a message to Goose, Hermes, or OpenClaw through the local bridge
- you need to broadcast one message to all connected runtimes
- you need to inspect the stored conversation thread after a routed message

Do not use this skill when:
- a normal direct reply to the user is enough
- you already have a first-class local tool for the exact runtime you need
- the task does not require cross-agent coordination

## Assumptions

This skill assumes a local `agent-fabric` daemon is running and reachable.

Default local URL:
- `http://127.0.0.1:9460`

If the environment defines `AGENT_FABRIC_URL`, use that instead.

Preferred local wrapper command:
- `agent-fabric-send`

Use the wrapper first. Use raw HTTP only if the wrapper is unavailable.

## Available Targets

Typical targets are:
- `goose`
- `hermes`
- `openclaw-main`
- `broadcast`

Do not guess targets. If unsure, query the bridge first.

## How to Use

### 1. Check health first

Prefer the wrapper:

```bash
agent-fabric-send broadcast --health
```

Fallback:

```bash
curl -s ${AGENT_FABRIC_URL:-http://127.0.0.1:9460}/health
```

If health does not return `"ok": true`, stop and report that the bridge is unavailable.

### 2. List available adapters

Prefer the wrapper:

```bash
agent-fabric-send broadcast --agents
```

Fallback:

```bash
curl -s ${AGENT_FABRIC_URL:-http://127.0.0.1:9460}/v1/agents
```

Read the available adapter ids before sending a message.

### 3. Send a directed message

Prefer the wrapper:

```bash
agent-fabric-send goose "Reply with one paragraph summarising current status."
```

If the logical source matters, add it explicitly:

```bash
agent-fabric-send goose "Reply with GOOSE_OK only." --source hermes
```

Fallback:

```bash
curl -s -X POST ${AGENT_FABRIC_URL:-http://127.0.0.1:9460}/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "<your-runtime>",
    "target": "goose",
    "body": "Reply with one paragraph summarising current status."
  }'
```

Replace `<your-runtime>` with the runtime you are acting from if known. If not known, use a generic source label such as `operator` or `bridge-client`.

### 4. Broadcast to all runtimes

Prefer the wrapper:

```bash
agent-fabric-send broadcast "Reply with one line stating your runtime name and status."
```

Fallback:

```bash
curl -s -X POST ${AGENT_FABRIC_URL:-http://127.0.0.1:9460}/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "<your-runtime>",
    "target": "broadcast",
    "body": "Reply with one line stating your runtime name and status."
  }'
```

### 5. Inspect the stored conversation

The wrapper prints `conversation_id` in its response summary.

If you need the full stored thread, use raw HTTP:

```bash
curl -s ${AGENT_FABRIC_URL:-http://127.0.0.1:9460}/v1/conversations/<conversation_id>
```

## Workflow Rules

1. Check health before first use in a session
2. List agents if the valid target set is unclear
3. Send the smallest useful message
4. Prefer directed messages over broadcast unless cross-runtime consensus is actually needed
5. Read back the stored conversation when the exact downstream reply matters
6. Report failures clearly, including which adapter failed
7. Prefer `agent-fabric-send` over raw `curl`

## Response Handling

When reading the bridge response:
- `message` is the normalized fabric message
- `deliveries` contains one record per target adapter
- each delivery includes:
  - `adapter_id`
  - `ok`
  - `body`
  - `error`
  - `duration_ms`

Treat `ok: false` as a failed delivery.

If one adapter fails and others succeed, report the partial success clearly.

## Good Patterns

### Ask one runtime for a narrow answer
Good:
- "Reply with current status in one sentence only"
- "Return only YES or NO"
- "Summarise the last failure in 3 bullets"

### Broadcast only when comparison is useful
Good:
- compare runtime identity
- compare health/status
- ask each runtime for its own view

Bad:
- sending long unfocused prompts to all runtimes
- using broadcast when a single target would do

## Failure Modes

### Bridge unavailable
If the wrapper health check or `/health` fails, stop and report that `agent-fabric` is not reachable.

### Unknown target
If the target adapter does not exist, list agents first and then retry with a valid id.

### Partial delivery failure
If one adapter fails in a broadcast, report:
- which adapters succeeded
- which adapter failed
- the returned error

### No shell tool available
If your runtime cannot execute shell or HTTP requests, state that you cannot use the bridge from this runtime without a first-class bridge tool.

## Quick Reference

### Health
```bash
agent-fabric-send broadcast --health
```

### Agents
```bash
agent-fabric-send broadcast --agents
```

### Directed message
```bash
agent-fabric-send goose "Reply with GOOSE_OK only."
```

### Broadcast
```bash
agent-fabric-send broadcast "Reply with exactly one line in the format ADAPTER_OK: <runtime>."
```

### Conversation fetch
```bash
curl -s ${AGENT_FABRIC_URL:-http://127.0.0.1:9460}/v1/conversations/<conversation_id>
```

## References

- `references/examples.md`
