# Synkraken Bridge Examples

## Example 1: Ask Goose a direct question

```bash
synkraken-send goose "Reply with one sentence describing your active role." --source hermes
```

## Example 2: Ask Hermes a direct question

```bash
synkraken-send hermes "Reply with HERMES_OK only." --source goose
```

## Example 3: Ask OpenClaw to respond

```bash
synkraken-send openclaw "Reply with OPENCLAW_OK only." --source operator
```

## Example 4: Broadcast to all runtimes

```bash
synkraken-send broadcast "Reply with exactly one line in the format ADAPTER_OK: <runtime>." --source operator
```

## Example 5: Read a stored conversation

If the wrapper prints:

```text
conversation_id: 1234-abcd
```

then fetch the full thread:

```bash
curl -s ${SYNKRAKEN_URL:-http://127.0.0.1:9460}/v1/conversations/1234-abcd
```
