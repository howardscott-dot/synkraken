# Product Vision

## SynKraken in one sentence

SynKraken is the **open-source control plane for AI workforces**: a
local-first, runtime-neutral place to see, direct, govern, coordinate, and
recover work across heterogeneous AI runtimes.

## Release posture

SynKraken is not trying to become another coding agent, orchestration LLM,
chatbot, CrewAI clone, or hidden autonomous swarm. It is trying to become the
best local control plane for people who deliberately use multiple agents and
want the work to remain visible, steerable, and theirs.

## Product thesis

AI agents are becoming useful in plural. The problem is no longer only how to
run one assistant, but how to understand and steer several of them without
handing control to a remote orchestration platform.

SynKraken should make local AI workforce operation legible:

- the human remains the operator
- agents remain distinct runtimes with their own strengths
- coordination is explicit, inspectable, and durable
- the system stays small enough to trust

Users own subscriptions, API keys, costs, and runtimes. SynKraken owns
visibility, governance, coordination, and recovery.

## Product principles

### Local-first

The default operating model is one local machine, local storage, and loopback
networking. SynKraken should work without SaaS infrastructure and should keep
conversation history under the operator's control.

### Human-controlled coordination

SynKraken coordinates agents; it does not replace operator judgment. The human
chooses the room, message, task, and next action. Automation may grow later,
but the command deck must remain understandable and interruptible.

### One backend, multiple operator surfaces

The TUI and Web GUI are peers over the same backend. A message sent from either
surface should create the same stored record, delivery history, and live events.
No client should become a private fork of the product model.

### First-class work objects

The product model is broader than chat. SynKraken should treat these as durable
objects rather than incidental UI state:

- rooms
- messages
- agents
- memory
- tasks
- decisions

Rooms, messages, and agents exist today. Memory, tasks, and decisions define
the next durable layer of the command deck.

Agent presence is part of the operational agent record: it tells the operator
whether an agent is online, idle, working, blocked, offline, or disabled, and
when SynKraken last saw activity. Presence is not memory, decisions,
autonomous scheduling, or chain-of-thought.

These objects should be:

- durable enough to survive a UI session
- inspectable without special tooling
- linkable to one another
- portable across current and future client surfaces

### Heterogeneous by design

SynKraken should work with Claude Code, Goose, OpenClaw, Hermes, and future
agents through small adapters rather than forcing a single runtime choice.

### Lightweight by default

The project should continue to avoid heavy dependencies unless they buy a
clear product advantage. Small stdlib-first pieces are preferred over large
framework commitments.

## Product surfaces

### TUI

The TUI is the fast, keyboard-driven operator console. It should remain a
first-class interface for people who live in terminals.

### Web GUI

The Web GUI is the visual command deck: easier to scan, easier to share on one
screen, and a better foundation for richer work objects over time.

### Runtime communication

The runtime communication skill lets participating agents call back into
SynKraken so the system is not only a human broadcast console; it is a shared
local fabric under operator-visible governance.

## Product boundaries

SynKraken **is**:

- a local-first control plane
- a runtime-neutral management harness
- a governance layer
- a memory layer
- a coordination system
- an observability layer
- a durable record of multi-agent work

SynKraken is **not**:

- another coding agent
- an orchestration LLM
- a chatbot
- a CrewAI clone
- a hidden autonomous swarm

## Near-term product direction

Version 0.2 should establish the foundation:

1. document the product and architecture clearly
2. preserve the existing daemon and TUI
3. add the first Web Command Deck over the same backend
4. prepare the object model for memory, tasks, and decisions without rushing
   those features into an unstable design

## Success measures for v0.2

Version 0.2 succeeds if:

1. a new contributor can understand the product shape from the docs
2. the TUI and Web GUI both operate over the same backend concepts
3. an operator can see agents, rooms, and live messages at a glance
4. adding richer work objects later does not require rethinking the core model

## Later integrations

External product integrations belong later, after the local command deck has a
stable product shape and durable object model. They should integrate with
SynKraken's concepts rather than define them prematurely.

The product stack is OSS, then Packs, then Vertical products. The OSS layer
defines generic durable concepts; packs and vertical products extend them.
