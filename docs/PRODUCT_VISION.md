# Product Vision

SynKraken is an open-source Company Operating System powered by an AI
Workforce.

It exists because AI work is becoming multi-worker. Operators increasingly use
more than one model, CLI, coding assistant, and local runtime. Each tool can be
useful alone, but real work needs shared context, durable authority, visible
handoffs, traceable failures, and a way to decide which worker should be
trusted with which work.

## Why Governance Matters

AI workers can draft plans, inspect code, propose changes, review outputs, and
summarize incidents. They can also fail silently, hallucinate confidence, drift
from instructions, emit empty replies, time out, or propose actions that should
not run without review.

Governance is the difference between using AI as a chat window and operating
AI as a workforce. SynKraken treats proposals, approvals, decisions, handoffs,
memory, failures, and runtime quality as first-class operational records.

## Why Chat Is Insufficient

Chat is a good interaction primitive, but not a complete operating model.
Persistent AI work needs:

- rooms with durable transcripts
- visible worker participation
- decisions and handoffs that survive the chat scrollback
- approval records for sensitive actions
- replayable traces after something fails
- trust and health signals for each runtime
- recovery paths for dead letters and timeouts

SynKraken keeps chat where it is useful, then surrounds it with operational
state.

## Why Persistent Operational Systems Matter

AI work often fails later than the initial prompt. A response may be empty. A
runtime may identify as the wrong worker. A proposal may need review. A room
may need memory of a decision made yesterday. A team run may block halfway
through.

If that state lives only in terminals, it disappears. SynKraken stores the
operational trail in SQLite and exposes it through daemon APIs and operator
surfaces.

## Why Workforce Management Matters

Different runtimes have different strengths, costs, permissions, speed, and
failure modes. SynKraken does not assume all workers are equal. Runtime
reputation and workforce health make observed reliability visible without
turning it into opaque AI scoring.

The operator remains in charge of which runtimes are enabled and how they are
used.

## Why Auditability Matters

AI work should be inspectable after the fact. SynKraken's flight recorder and
trace views reconstruct what happened from messages, deliveries, dead letters,
decisions, handoffs, proposals, tasks, goals, and memory events. This is
necessary for debugging, trust, governance, and recovery.

## Why Human Approval Matters

SynKraken's authority doctrine is:

```text
Agents propose.
Humans approve.
SynKraken executes and records.
```

In the current governance model, execution records are simulated for sensitive
proposal actions. That limitation is deliberate. SynKraken is building the
authority ledger before expanding governed execution.

## Direction

Over the next several years SynKraken should become the open-source operating
layer for company work powered by AI workforces:

- project-centric company workspaces that gather conversations, knowledge,
  deliverables, team activity, and decisions
- richer spatial operations over workers, rooms, proposals, traces, incidents,
  decisions, and handoffs
- better runtime reputation and historical inspection
- deeper room, memory, decision, and handoff workflows
- stronger packaging for local operators
- governed execution extensions under explicit human approval
- optional product integrations that preserve the local-first control-plane
  model

The future SynKraken experience is a project-centric company workspace where
operators can create projects, talk to workers, store knowledge, review
deliverables, and make decisions, with technical operations available in
Advanced when inspection is needed.
