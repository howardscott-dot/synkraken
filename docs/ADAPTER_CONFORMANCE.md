# Adapter Conformance

Adapters are thin runtime wrappers. A conforming adapter:

- extends `BaseAdapter`
- returns `AdapterReply` from `send()`
- exposes stable `health()` metadata
- uses `cli_utils.run_command` for subprocess execution, or stdlib HTTP
  clients for HTTP-backed local runtimes
- maps empty output, timeout, and runtime failure into inspectable replies
- avoids hidden state outside runtime configuration

Odysseus support is experimental. Odysseus must be installed and running
separately, must already have its internal model endpoint configured, and
requires an API token. SynKraken does not install skills into Odysseus yet.
MCP, task, and webhook integration are future work.

Before adding a runtime adapter, run the closest adapter smoke test in `scripts/` and add one if the runtime has adapter-specific behavior. General delivery behavior is covered by:

```bash
python3 scripts/adapter_conformance_smoke_test.py
python3 scripts/delivery_quality_smoke_test.py
python3 scripts/runtime_reputation_smoke_test.py
python3 scripts/operational_controls_smoke_test.py
```

The control plane records adapter behavior through deliveries, dead letters, runtime reputation, and trace/replay views. New adapters should improve those records rather than bypass them.
