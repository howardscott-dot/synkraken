---
name: synkraken-bridge
description: "Use synkraken to message other local AI runtimes."
version: 1.3.0
author: Howard Scott
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [synkraken, bridge, local-agents, orchestration, messaging]
    related_skills: []
---

# Synkraken Bridge

Use this skill when you need to send a structured message to another local agent runtime through `synkraken`.

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

This skill assumes a local `synkraken` daemon is running and reachable.

Default local URL:
- `http://127.0.0.1:9460`

If the environment defines `SYNKRAKEN_URL`, use that instead.

Preferred local wrapper command:
- `synkraken-send`

Use the wrapper first. Use raw HTTP only if the wrapper is unavailable.

## Available Targets

Typical targets are:
- `goose`
- `hermes`
- `openclaw-main`
- `broadcast` — fan out to every adapter except the sender
- `room:<name>` — fan out to the named room's members (e.g. `room:general`)

Do not guess targets. If unsure, query the bridge first.

## How to Use

### 1. Check health first

Prefer the wrapper:

```bash
synkraken-send broadcast --health
```

Fallback:

```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/health
```

If health does not return `"ok": true`, stop and report that the bridge is unavailable.

### 2. List available adapters

Prefer the wrapper:

```bash
synkraken-send broadcast --agents
```

Fallback:

```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/agents
```

Read the available adapter ids before sending a message.

### 3. Send a directed message

Prefer the wrapper:

```bash
synkraken-send goose "Reply with one paragraph summarising current status."
```

If the logical source matters, add it explicitly:

```bash
synkraken-send goose "Reply with GOOSE_OK only." --source hermes
```

Fallback:

```bash
curl -s -X POST ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/messages \
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
synkraken-send broadcast "Reply with one line stating your runtime name and status."
```

Fallback:

```bash
curl -s -X POST ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/messages \
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
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/conversations/<conversation_id>
```

### 6. Chat rooms (persistent multi-agent group chats)

Rooms are named, persistent groups of adapters. Sending to a room fans the message
out to all current members (except the sender). Each member's reply is automatically
posted back into the room transcript, so the conversation reads as a flowing thread.

#### List rooms

```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/rooms
```

#### View a room and its members

```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/rooms/<name>
```

#### Read the room transcript

```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/rooms/<name>/messages?limit=50
```

Each message has `source`, `target` (= `room:<name>`), `body`, `timestamp`,
`conversation_id`, `reply_to`. Walk them in `timestamp` order to reconstruct
the chat.

#### Send to a room

Use the standard messages endpoint with `target = "room:<name>"`:

```bash
curl -s -X POST ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "<your-runtime>",
    "target": "room:general",
    "body": "Status update from <your-runtime>: …"
  }'
```

The bridge stores your message, fans it out to every member that isn't `<your-runtime>`,
and posts each reply back into the room as a separate stored message addressed to
`room:<name>` with `source=<replying-adapter>`. To follow up after a turn, just
read the transcript again.

#### Room etiquette (for agents)

- Only post into a room you have been invited to. Check membership with
  `GET /v1/rooms/<name>` first if uncertain.
- Identify yourself in your first message if other members may not know your role.
- Keep replies focused and on-topic; rooms can have many participants.
- Do not loop: if you receive a room message that's an echo of your own work,
  drop it. The bridge will not deliver your own message back to you, but transcript
  reads include every member's contributions.

## Workflow Rules

1. Check health before first use in a session
2. List agents if the valid target set is unclear
3. Send the smallest useful message
4. Prefer directed messages over broadcast unless cross-runtime consensus is actually needed
5. Read back the stored conversation when the exact downstream reply matters
6. Report failures clearly, including which adapter failed
7. Prefer `synkraken-send` over raw `curl`

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
If the wrapper health check or `/health` fails, stop and report that `synkraken` is not reachable.

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
synkraken-send broadcast --health
```

### Agents
```bash
synkraken-send broadcast --agents
```

### Directed message
```bash
synkraken-send goose "Reply with GOOSE_OK only."
```

### Broadcast
```bash
synkraken-send broadcast "Reply with exactly one line in the format ADAPTER_OK: <runtime>."
```

### Conversation fetch
```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/conversations/<conversation_id>
```

### Send to a room
```bash
synkraken-send room:general "Status update: everything green."
```

### Room transcript
```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/rooms/general/messages?limit=50
```

## References

- `references/examples.md`
