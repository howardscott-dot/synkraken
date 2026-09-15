# Security Policy

## Reporting a Vulnerability

Please report security issues privately by opening a
[GitHub security advisory](https://github.com/howardscott-dot/synkraken/security/advisories/new)
rather than a public issue. We aim to acknowledge reports within a few days.

## Threat Model

SynKraken is a **local-first, single-operator control plane**. Its default and
supported deployment is a daemon bound to `127.0.0.1`, driven by one trusted
operator on the same machine. Understand these properties before exposing it
more widely:

- **The daemon drives code-executing AI runtimes.** Adapters invoke external
  CLIs (Claude Code, Goose, etc.), and some runtimes are configured with
  permissions bypassed (e.g. `permission_mode: bypassPermissions`,
  `--dangerously-skip-permissions`). Anyone who can send requests to the daemon
  can drive those runtimes. **Reaching the API is a path to code execution on
  the host.**
- **Message bodies are untrusted.** Prompt content delivered to a runtime can
  attempt prompt injection. Governance (proposals, approvals, memory review)
  distinguishes *statuses*, not authenticated *principals* — treat approvals as
  advisory unless you have enabled authentication and separated operator from
  agent credentials.

## Hardening Controls

The daemon and web deck ship with these controls enabled by default:

- **Loopback bind by default** (`server.host: 127.0.0.1`). The daemon warns and,
  for a routable bind, requires a token (see below).
- **Host-header validation** on loopback binds, defeating DNS-rebinding attacks
  from a malicious web page in the operator's browser.
- **Request-body size cap** and clamped query limits to bound memory/CPU.
- **Content-Security-Policy** and `X-Content-Type-Options` on the web deck; the
  deck escapes all agent-authored output before rendering.
- **Subprocess isolation**: runtimes run in their own process group and are
  killed as a tree on timeout; captured output is size-capped and stripped of
  terminal control sequences before printing.

## Enabling Authentication

To require a shared secret on every request (recommended for any non-loopback
or multi-user scenario):

```json
{ "server": { "host": "127.0.0.1", "port": 9460, "auth_token": "<long-random-string>" } }
```

Or set the `SYNKRAKEN_TOKEN` environment variable (it also configures the CLI,
TUI, and web deck to send the token). Generate a token with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

When a token is set, every request must present `Authorization: Bearer <token>`.

## Recommendations for Wider Deployment

The current model targets single-operator localhost use. Before exposing
SynKraken to multiple users or an untrusted network, additionally:

- Put the daemon behind a reverse proxy with TLS and real authentication.
- Run each runtime under a dedicated low-privilege user or in a container/VM.
- Scope each adapter's environment so runtimes do not inherit unrelated API keys.
- Bind approvals to authenticated identities so proposers cannot self-approve.
