# Native bot engine

The working architecture and phased plan is maintained in
[Google Docs](https://docs.google.com/document/d/1NMZOO7PhYKQ7YCpjHgwrDfK4Q6eURpfdfAHTBLy73Ns/edit).

## Architecture

The existing daemon, SQLite, HTTP/SSE, runtime adapters, rooms, tasks, CLI/TUI
and advanced Command Deck are retained. The default web workspace is a bot
roster and conversation surface; `/deck` preserves advanced legacy workflows.
The retired Tauri console remains retired.

Two explicit execution routes share durable bot identity and conversation:

- `BotProfile -> provider_id + model -> native BotEngine -> tools -> model`
- `BotProfile -> runtime_id -> existing CLI/HTTP adapter`

A bot owns its UUID, role, instructions, operator notes, conversation, permitted
tools and allowed delegates. Rebinding preserves identity and history. Providers
are separate connections; different bots can use different providers concurrently.
No automatic provider fallback or silent model substitution occurs.

Native transport support currently covers OpenAI-compatible Chat Completions
and Anthropic Messages, including tool calls/results and usage reporting.
OpenAI, compatible gateways and compatible local servers can use the first
transport; a provider with a different protocol needs an additional adapter.
This is extensible provider neutrality, not a claim that every vendor/model
supports this contract. Models must support the requested tool schema. Responses
API, native Gemini API, OAuth subscriptions and streaming tokens are not yet
implemented. Existing Hermes/OpenClaw/Odysseus adapters remain available.

## Conversation-first product contract

The default interface is chat with a compact bot roster and contextual cards.
There are no provider, task or bot-creation dashboards in the primary flow.
The optional right-hand drawer contains Progress, Browser and Bot profile.
Basic profile edits are display name, short label and guidance; labels are
metadata and never become persona instructions. SynKraken uses original assets,
copy and styling. Grokbot supplies interaction references, not copied branding.

`Synkraken setup` and fresh installs create a native configuration, preserve
existing configuration, start the daemon and open the setup conversation.
The operator chooses a provider and types the exact default model ID. The first
bot has empty job, instructions and notes, no installed skills and only host
workspace-management actions. No default persona is inserted. A shared runtime contract requires evidence for current facts and exposes a capability-request action to every bot; approval cards grant access separately.
The host can supply structured receipts after a card is completed. New bots
created through chat inherit the default provider/model and start without tools
or invented instructions unless the user requests instructions.

The entry bot can list/create bots, propose configuration changes, request
provider connections and request secure input. Configuration changes appear as
reviewable cards and apply only when the operator accepts. Existing custom
provider endpoints remain supported through the API; the initial connection
cards cover OpenRouter, OpenAI, Anthropic and Ollama. Existing adapters and
advanced `/deck` workflows remain available.

## Sign-in and encrypted input

OpenRouter uses its documented PKCE flow: a host-generated S256 verifier,
a provider authorization link, then a one-time code entered into a secure card.
The verifier stays in memory, expires after ten minutes and is consumed once.
Changing setup invalidates the flow. This is OAuth with a code handoff, not an
automatic redirect callback. Other provider cards use API keys or local access;
there is no claim of universal subscription OAuth support.

Keys and username/password card values use AES-256-GCM with fresh nonces and
credential-reference associated data. The master key lives in a supported OS
keychain; an explicitly supplied `SYNKRAKEN_VAULT_KEY` may be used by a host
secret manager. No plaintext-keyring or local key-file fallback is permitted.
Encrypted entries use 0600 files in a 0700 directory. Legacy plaintext provider
keys migrate to the vault on first use. Model messages, transcripts, run events
and normal API responses receive only card status/reference, never submitted
secret values. Saving a generic login card does not sign in to an external app.

The encrypted export contains ciphertext only. Cloud synchronization, cloud
account identity, key recovery and multi-device key wrapping are not connected.
Moving a vault requires preserving its original master key through a separate
secure channel. The master-key account is associated with the vault location.
Remote provider redirects remain blocked; remote endpoints require HTTPS.

## Built-in browser

The optional `browser` extra uses Playwright Chromium. The standard installer
installs it and its browser binary. Source installations can run
`pip install -e '.[browser]'` then `python -m playwright install chromium`.
Each bot receives a separate context, cookies and page, up to four open browser
contexts. Sessions are currently in memory and are not restored on restart.
Browser child processes receive a reduced environment and enable Chromium's
sandbox. This is application isolation, not a complete network/OS sandbox.

Tools open/read pages, click observed element references, fill non-secret text
and scroll. A new origin requires an access card. Other origins and private
addresses are blocked by request routing; cross-origin resources may therefore
need explicit additional access. Tests may explicitly configure a local fixture
origin through `engine.browser_test_origins`. This setting is for trusted test
configuration and is empty by default. Network-level egress enforcement is still
needed before treating this as a hostile multi-tenant browser boundary.

The drawer shows actual browser screenshots and accepts operator navigation,
preview clicks and scrolling. Taking over is rejected while the bot is working.
Password filling, authenticated service handoff, pop-up tabs, downloads and
persistent browser sessions are not implemented. Browser observations are
untrusted page data. The model must have explicit browser tool permissions;
a blank bot does not silently receive browser access.

## Chat APIs

`GET /v1/workspace` reads setup/default state. `POST /v1/workspace/setup`
selects provider/model and completes initialization idempotently. OAuth start
and finish use `/v1/workspace/oauth/start` and `/finish`. Inline cards resolve
through `POST /v1/chat-cards/{id}`. Existing bot PATCH handles basic profile
edits including `label`. `GET /v1/bots/{id}/browser` reads the last screenshot;
POST performs operator browser actions. Host/token gates remain in force;
workspace writes require JSON and the web proxy rejects cross-origin writes.

## Native execution and persistence

The engine performs up to 16 model/tool iterations per bot turn. A root run and
all delegated children share a five-minute deadline, 24 model requests, 48 tool
calls and 64,000 reported tokens. Each request has a bounded response size and
at most a 60-second timeout. Output requests are capped at 4,096 tokens. These
are execution limits, not price estimates or a strict monetary spending cap.

Available tools are bot-scoped memory read/write, workspace listing/read/write,
portable skill listing/read, permitted teammate listing and bounded delegation.
Memory holds at most 32 named entries of 2,000 characters each. Operator notes
and bounded recent history are included in prompts; learned memory is retrieved
explicitly through the memory tool. File paths are confined to each bot's
workspace and checked against traversal/symlink escape. No shell or
unrestricted host-file tool is exposed. Browser tools are separately granted. This is not an OS sandbox.

Skills are read from configured `engine.skill_roots`, defaulting to the repo
skills directory. Reading a SKILL.md does not install tools or execute arbitrary
instructions. Existing runtime-managed skills remain the runtime's concern.
MCP transport/catalog integration is the next capability slice, not implemented
by the native engine yet.

Delegation requires both the delegate tool and an explicit target allowlist.
Children have separate tasks, runs, bot memory and conversations; parent run IDs
record the chain. Cycles and excessive depth are rejected. Child results return
to the requesting model. Shared cancellation and budgets cover the whole tree.

Additive SQLite tables store providers, runs, run events and bot memory alongside
bot profiles and profile snapshots. Each turn creates an existing task, message
and delivery; failures remain visible with dead letters. Native model/tool events
include actual route, tool result and usage. Historical runtime data is retained.

## API and background runs

- `GET/POST /v1/providers`, `PATCH /v1/providers/{id}` and
  `POST /v1/providers/{id}/probe` manage and test connections.
- `GET/POST /v1/bots`, `GET/PATCH /v1/bots/{id}` manage profiles.
  Native fields include `provider_id`, `model`, `tools`, `delegate_to`.
- `POST /v1/bots/{id}/runs` accepts `body` and optional `request_key`, persists
  the run and queues background execution. A repeated key/body returns the same
  run; reuse for a different body is rejected.
- `GET /v1/bot-runs/{id}` returns the run and event history.
  `POST /v1/bot-runs/{id}/cancel` requests cooperative cancellation.
- `GET /v1/bots/{id}/conversation` returns conversation, runs, latest run events
  and saved memory. The original synchronous `/messages` route remains supported.

A four-worker executor accepts at most 16 active/queued top-level bot turns.
One turn per bot is allowed; profile edits while active are rejected. Closing the
browser does not stop the worker. Cancellation prevents subsequent steps after
an in-flight provider call returns; it cannot undo completed tool writes or
provider charges. Interrupted jobs are marked interrupted on restart, not
silently replayed. There are no distributed leases or automatic recovery yet.
The browser uses durable request keys, polls while visible and exposes stop,
actual run steps and failure states. Existing Host/token API gates remain.

## Remaining scope

MCP client/server compatibility, bot membership in shared channels, authenticated
external messaging, routines, richer context retrieval, streaming and explicit
retry/recovery are subsequent slices. Channels currently show existing runtime
rooms and their fan-out semantics. No external service is impersonated as a
connected channel. Odysseus remains an experimental HTTP leaf adapter; its
separate source and internal session/MCP behavior have not been verified.

## Verification

The expanded suite passes 72 tests. Browser checks verify setup/OAuth-card
rendering, chat-driven bot creation, blank conversations, encrypted synthetic
input, profile changes and a real browser navigation/click on an isolated fixture.
The standard smoke and full live integration checks pass against two simulated
legacy adapters. Live OAuth account authorization and paid inference remain
unverified. No live account credentials were used in these checks.


Provider contract tests use real HTTP with scripted local OpenAI-compatible and
Anthropic servers. They cover tool round-trips, cross-provider delegation,
memory/workspace boundaries, permissions, shared budgets, cancellation,
idempotency, malformed responses, credentials and restart interruption.
Regression tests cover retained runtime bots, profile persistence, rebinding,
API security and both web routes. Browser checks cover connection setup/model
discovery, native bot creation, asynchronous send and persisted tool activity.
No authenticated cloud inference has been tested: no provider keys or running
local model server were available. The served workspace is ready to configure;
scripted test state is kept separate from the clean native workspace.

### Reference review: chat, identity and Mac setup (14 September 2026)

The supplied Grokbot and workplace-agent screenshots are interaction references, not source assets. SynKraken retains the conversation-first entry point and an initially unassigned bot. Original kraken, ray and diver vector characters have six selectable colours; appearance persists independently of instructions, provider and model. The roster now uses compact conversation rows. Basic appearance/name/guidance controls remain in the optional right panel.

The composer’s capability card lists browser, memory, files, portable skills, delegation and model connections. It reflects existing tool permissions and lists skills discovered on the host. Selecting an entry prepares a chat request to the workspace bot; it neither sends the message nor grants permissions automatically. Existing model-generated approval cards apply changes. MCP and external app plugins are explicitly unavailable in this build; the catalog must not imply otherwise. Custom uploaded avatars remain future work.

`packaging/macos/build.sh OUTPUT_DIRECTORY` builds a native AppKit/WKWebView `.app` and a DMG with an Applications shortcut. Build prerequisites are Xcode command-line tools, the project virtual environment with PyInstaller and the browser extra. The app bundles Python, cryptography/keyring, Playwright and Chromium headless shell. It starts its own engine on ephemeral loopback ports, gives the internal API a fresh token, stores state in `~/Library/Application Support/SynKraken`, and locks that database against duplicate processes. It does not import or alter existing CLI installations or their databases. Opening external links uses the system browser. Closing the app requests cancellation and shuts down after the current operation finishes; this is not yet an always-running background agent service.

The package is ad-hoc signed for development on the build machine's architecture, not Developer ID signed or notarized. The generated icon and UI characters are original vector artwork. First launch proceeds directly to provider/model setup in chat. OpenRouter currently offers PKCE with a manually pasted one-time code; other remote presets use secure API-key cards. Automatic authorization return, all-provider OAuth, background scheduling, production signing and cloud synchronization are not implemented by this slice.

### Provider shortlist and authentication status

The primary setup choices are OpenRouter, Anthropic, OpenAI, Grok and MiniMax. Local Ollama remains under a secondary disclosure. MiniMax uses `https://api.minimax.io/anthropic/v1/messages` with encrypted API-key storage and the existing Anthropic-format tool loop, including preserved thinking blocks. Its model card offers M3, M2.7 and M2.5 while allowing another model ID. Grok's optional API-key path uses `https://api.x.ai/v1`. MiniMax international keys are expected; regional endpoints need a separately configured provider.

Howard's requested authentication target is account OAuth for Anthropic, OpenAI and Grok. This is still outstanding, not fulfilled by the optional API-key presets. The UI says so explicitly. Integrate the documented Claude Agent SDK, Codex app-server and Grok Build account-authentication paths with refresh, cancellation and native SynKraken tool permissions; do not copy tokens into generic API-key fields or silently substitute separately billed API access. OpenRouter's existing PKCE implementation is retained.

Official references reviewed on 14 September 2026: https://platform.minimax.io/docs/api-reference/text-anthropic-api ; https://learn.chatgpt.com/docs/auth ; https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan ; https://docs.x.ai/build/enterprise . Account authorization and live inference remain untested without the user's provider credentials.


## Reuse audit and runtime delegation — September 2026

Native bots can now delegate to explicitly allowed runtime-backed bots through
`BotService.send` and the existing `AgentFabric.dispatch` path. The old native-only
check was preventing use of the retained Hermes, OpenClaw and Odysseus adapters.
Dispatch, delivery records, task tracking, conversation context and adapter error
handling remain authoritative; this does not introduce a second runtime executor.
The parent keeps its selected provider. Runtime workers use their own configured
provider and permissions; no runtime is installed or silently selected.

Runtime handoffs consume the shared call budget and record parent/child run IDs.
An external runtime's internal model calls cannot be counted by this engine, and
its configured timeout still governs an in-flight adapter call. Cancellation is
observed when it returns, rather than immediately terminating that runtime.

The local Odysseus implementation is an experimental HTTP client for a separately
running service, not a bundled search/browser implementation. Existing runtime
capability labels are discovery hints, not proof of live web access. The current
preview has no configured external adapters. Native browser capabilities remain
available through approval cards, using the already implemented browser manager.

Validation: 84 automated tests passed, plus the retained smoke and live integration
checks against isolated simulated adapters. A live MiniMax/Scout run opened and
read National Rail in the native browser, but did not complete its journey planner.
This is not yet a verified end-to-end train-times capability. Access-card requests
now pause the model loop immediately rather than allowing speculative follow-up
answers while permission is pending.

## Bot creation receipts — September 2026

A live MiniMax turn claimed a personal-assistant bot had been created, including
an invented UUID, without invoking create_bot. The sidebar correctly reflected
the two actual database records. The host now receives the current saved roster
after conversation history. Detected unsupported creation claims trigger one
corrective model turn, then a visible failure if repeated. This English-language
claim check is a backstop, not a general proof system for arbitrary model prose.
Successful create_bot receipts are checked against storage and the final creation
confirmation is rendered from those records, without invented capabilities/IDs.
Regression coverage includes false success, repeated false success, real creation
after correction, and authoritative roster context. 87 tests pass.
