# Product Doctrine

SynKraken is an open-source Company Operating System powered by an AI
Workforce. This doctrine is the philosophical source of truth for how
SynKraken should behave as it grows.

The product can add surfaces, adapters, workflows, and integrations, but these
principles define the operating model.

## 1. Truth Over Polish

SynKraken must expose failures, weak outputs, incidents, degraded workers,
timeouts, empty replies, suspicious output, and dead letters.

Why it exists:

AI work is useful only when the operator can see where it is weak. A clean
interface that hides broken deliveries, unreliable runtimes, or empty replies
creates false confidence.

Encourages:

- showing failed and timed-out deliveries plainly
- preserving empty replies as `[empty reply]`
- surfacing degraded, unstable, and failing health states
- making incidents and dead letters visible operational objects
- keeping raw evidence available behind operator-friendly summaries

Discourages:

- smoothing failures into generic success states
- hiding weak output because it looks bad
- replacing observable state with fake health
- inventing telemetry to make the product feel complete

## 1.1. Calm Truth

Truth over polish does not mean panic. SynKraken should expose real failures
without exaggerating their urgency.

Why it exists:

Operators need to know what happened, what matters now, and what can wait. A
runtime with empty replies should stay visible, but it should not look like a
system-wide emergency unless active work is blocked.

Encourages:

- separating raw daemon health from operator-facing display severity
- reserving red for daemon offline, blocked work, critical execution failure,
  and active incidents affecting current work
- using amber for degraded, unreliable, or noisy-but-nonblocking workers
- keeping raw health, incidents, dead letters, and JSON evidence available
- providing plain-English impact and suggested next actions

Discourages:

- turning every `failing` runtime into a critical visual alarm
- hiding raw health or weak output to make the Console look calmer
- using dramatic language when the operator can safely ignore an issue
- treating historical dead letters as active emergencies by default

## 1.2. Calm Operations

An operator console should reduce cognitive load, not amplify it.

Why it exists:

Operators need a surface that helps them decide what to do next. Dense
telemetry, equal-weight panels, overused accent color, raw JSON-first
delivery output, and page-growing chat all make the operator work harder.
SynKraken should keep evidence visible while presenting the daily operating
loop as readable, bounded, and action-oriented.

Encourages:

- clear hierarchy between primary actions, secondary actions, dangerous
  actions, and disabled unavailable actions
- worker status language that answers whether a worker can be used now, what
  is wrong, what the impact is, and what to do next
- fixed-height operational workspaces where chat, members, and side context
  scroll independently
- human-readable delivery summaries before raw technical details
- calmer surfaces that reserve cyan for primary action and selected state

Discourages:

- wall-of-boxes dashboards where every panel has equal visual weight
- making every runtime warning look urgent
- allowing transcripts or member lists to push controls below the fold
- using red for nonblocking reliability issues
- raw JSON as the default operator experience

## 1.3. Operator First Interface

The Console should speak in goals, decisions, and next actions before exposing
system objects.

Why it exists:

SynKraken stores rooms, messages, activity, traces, missions, outcomes,
assignments, memory, proposals, incidents, and handoffs. Those objects matter,
but a first-time operator should not have to understand the database model
before knowing what needs attention, where to talk to the workforce, what work
is active, what the workforce remembers, and what needs approval.

Encourages:

- Home as the default operational briefing
- Rooms as the primary communication surface
- Work as one coherent area for missions, outcomes, and assignments
- Workforce Memory framed as what the workforce remembers
- Governance framed as what needs approval
- raw technical details behind drawers, details, and inspectors
- premium native-app restraint: system typography, whitespace, soft surfaces,
  Apple blue for primary actions, amber for attention, and red only for
  critical or destructive states

Discourages:

- starting the operator in raw objects, tables, traces, or canvas
- equal-weight dashboards where everything looks urgent
- debug-console language as the default copy
- exposing raw JSON or daemon fields before explaining operator impact
- adding more screens when a calmer grouped surface would answer the question

## 1.4. Living Workforce UX

SynKraken should feel like managing a team, not operating a monitoring
console.

Why it exists:

The architecture can persist rooms, messages, traces, assignments, missions,
outcomes, knowledge, proposals, incidents, and handoffs. But the operator's
mental model is not "inspect read models." It is "talk to the workforce, move
work forward, approve decisions, and inspect diagnostics only when needed."

Encourages:

- Conversation first, work second, governance third, diagnostics last
- Home as a deterministic chief-of-staff briefing
- Conversations as the centre of the product experience
- Knowledge as operator language for governed workforce memory
- Worker cards that describe availability, current work, watch items, and
  recommended action
- Governance as an inbox of judgement items
- Timeline-first activity
- one Spotlight-style Search across workers, conversations, work, knowledge,
  governance, incidents, and traces

Discourages:

- administrative-dashboard language
- table-first screens for primary workflows
- exposing storage architecture as the information architecture
- using Canvas as a primary workflow
- AI-written summaries in the briefing
- diagnostics competing with conversation and work

## 1.5. Project-Centric Company OS

The operator-facing model is projects, conversations, knowledge, deliverables,
and decisions.

Why it exists:

Missions, outcomes, assignments, memory items, proposals, traces, incidents,
and runtime diagnostics are important implementation and governance records,
but they are not how an operator thinks about company work. Operators think in
projects: a workspace with a purpose, conversations, knowledge, outputs,
people, and decisions.

Encourages:

- Projects as the centre of daily operation
- project detail tabs for Overview, Conversations, Knowledge, Deliverables,
  Team, and Decisions
- project workspaces that feel like the place a company outcome lives, with
  purpose, current focus, latest activity, next action, notes, outputs,
  conversation, contributors, and decisions in one surface
- deliverables as hero objects rather than buried implementation evidence
- human-readable project activity and decision language
- deterministic project assistance that tells the operator what happened,
  what needs attention, and what to do next without AI generation
- a project Inbox that aggregates deliverables, decisions, activity,
  knowledge, assignments, and handoffs in operator language
- Deliverables as visible project outputs such as PRDs, research, proposals,
  architecture, code reviews, articles, specifications, and reports
- Decisions as the human-facing version of governance
- Advanced as the place for assignments, outcomes, missions, traces, canvas,
  incidents, runtime diagnostics, proposal internals, dead letters, and memory
  internals
- empty states that teach what to do next

Discourages:

- forcing operators to open Advanced for daily work
- primary navigation based on internal entities
- governance jargon in project workspaces
- trust scores, runtime metrics, and health percentages in project team views
- hiding or deleting existing audit/governance capabilities

## 2. Human Approval Over Autonomy

Agents propose. Humans approve. Governance comes before execution.

Why it exists:

AI workers can suggest useful actions, but sensitive execution requires human
authority. SynKraken should make the authority boundary durable and visible
before expanding what it can execute.

Encourages:

- proposals for sensitive actions
- explicit approve, reject, cancel, and execute records
- deterministic risk and approval explanations
- durable governance events
- clear simulation boundaries for v0.1 execution

Discourages:

- permissionless worker execution
- hidden background action after a suggestion
- treating approval as a UI detail rather than an authority boundary
- implying real shell, git, file, restart, retry, replay, or delete execution
  when the current model records simulated execution

## 3. Visibility Over Magic

Operators should understand what happened.

Why it exists:

AI systems often fail in ways that are hard to diagnose. SynKraken should make
work inspectable through messages, deliveries, traces, proposal events,
handoffs, decisions, memory events, and incidents.

Encourages:

- readable status transitions
- linked records between objects
- visible room transcripts
- inspectable proposal, task, goal, decision, and handoff events
- UI surfaces that explain state instead of hiding it behind animation

Discourages:

- magical autonomous flows with no trail
- opaque scoring without evidence
- hidden agent-to-agent loops
- UI polish that obscures why something happened

## 3.0.1. Visible Memory

Shared memory must be inspectable, governable, and traceable.

Workers can lose context, but hidden long-term memory creates false
confidence. SynKraken should remember only through durable records the
operator can see and govern.

Visible Memory encourages operator-created approved notes, explicit proposed,
approved, rejected, and archived states, bounded approved-memory injection
with memory ids, scoped memory, and audit events. It discourages hidden
memory, automatic trusted promotion, opaque RAG/vector memory as the product
model, cloud memory, and AI-generated rewriting without operator visibility.

## 3.1. Presence Over Raw Checks

A workforce operating system should show what workers are doing, not only
whether they passed health checks.

Why it exists:

Health and reputation are useful, but operators also need to know who is
available, who is active, who is idle, who needs attention, and what happened
recently.

Encourages:

- deriving presence from durable daemon records
- showing last useful action beside raw health
- explaining current room, task, proposal, or trace context when available
- distinguishing needs-attention workers from blocked or critical incidents
- keeping presence deterministic and inspectable

Discourages:

- replacing presence with AI-generated summaries
- treating raw health checks as the whole workforce story
- implying autonomous scheduling or availability that SynKraken does not own

## 3.1.1. Operations Before Observability

If an operator cannot act from the Console, the Console has failed.

Why it exists:

SynKraken began as a way to talk to and operate an AI workforce. Dashboards,
read models, and governance surfaces matter only if the operator can also use
the workforce: create rooms, add workers, send messages, see replies, inspect
delivery failures, and continue the conversation.

Encourages:

- Console room operations that use daemon APIs rather than bypassing the
  daemon
- Slack/Discord-like room chat for AI workers
- visible delivery summaries with replied, empty reply, timeout, failed,
  blocked, and suspicious-output states
- explicit unavailable actions when daemon APIs do not exist
- practical quick actions for room creation, broadcast, membership, and chat

Discourages:

- observation-only Console screens for core daily workflows
- raw JSON as the default delivery experience
- hidden direct adapter calls from the UI
- faking unavailable daemon capabilities such as room rename or bulk remove
- adding autonomy, scheduling, planning, or project management to compensate
  for missing operator controls

## 3.2. Missions Over Project Management

SynKraken organises AI work through missions: governance containers around
meaningful outcomes.

Why it exists:

Operators need to know which outcomes are progressing, blocked, in review, or
complete without turning SynKraken into Jira, Trello, Asana, a kanban board, or
a scheduling system. A mission links workers, rooms, traces, proposals,
incidents, and outcomes so the work can be governed and inspected.

Encourages:

- mission read models that connect workers, rooms, traces, incidents, and
  proposals
- concise mission summaries for active, blocked, review, and completed work
- mission-scoped activity filtering
- mission nodes on the spatial canvas where relationships have evidence
- outcome and risk fields that make governance state visible

Discourages:

- project-management entities such as epics, sprints, kanban columns, gantt
  charts, due dates, estimates, or scheduling workflows
- workload-specific product entities
- treating missions as tasks, tickets, projects, or plans
- client-invented progress or AI-generated status summaries

## 3.3. Outcomes Over Activity

Outcomes are the primary success object.

Why it exists:

Workers produce activity, but activity is infrastructure. The operator cares
whether the desired result was achieved. Outcome Governance keeps SynKraken
focused on value: completed, in-progress, review, blocked, and cancelled
results linked to missions, evidence, proposals, incidents, workers, and
traces.

Encourages:

- outcome read models linked to missions
- mission progress derived from completed outcomes over total outcomes
- outcome-scoped activity, worker, proposal, incident, and trace context
- outcome confidence and evidence counts from deterministic records
- Console hierarchy that makes outcomes more important than raw worker chatter
- operational briefings that summarize the state of the work before the state
  of the agents

Discourages:

- measuring success by message volume or worker busyness
- AI-generated progress claims without evidence
- converting outcomes into tasks, tickets, schedules, kanban cards, or gantt
  milestones
- hiding blocked outcomes behind healthy worker activity

## 3.4. Accountability Before Automation

An AI workforce is not defined by how many workers exist. It is defined by
whether ownership is visible.

Why it exists:

Workers can reply in rooms without becoming a workforce. Assignments make
accountability explicit: one owner, many contributors, clear status, visible
blockers, review, completion, and handoffs. This preserves SynKraken as an
operating system for work without turning it into project management software.

Encourages:

- explicit assignment ownership by one worker
- contributor visibility without diluting accountability
- operator-initiated status changes, handoffs, escalation, review, and
  completion records
- handoff timelines that show who transferred work, who received it, why, and
  what context moved
- room, workforce, mission, outcome, activity, trace, proposal, and canvas
  surfaces that expose ownership and blockers quickly

Discourages:

- automatic reassignment, automatic handoff, or automatic escalation
- treating assignments as tasks, tickets, schedules, kanban cards, or project
  plans
- hiding ownership inside chat transcripts
- measuring workforce value by message volume or number of workers
- adding workflow automation engines to compensate for unclear accountability

## 4. Replayability Over Memory

Recorded evidence beats hidden context.

Why it exists:

Memory can help future prompts, but replayable evidence is what lets an
operator debug, recover, audit, and trust the system. SynKraken should prefer
durable records over invisible context.

Encourages:

- flight recorder replay
- operational trace views
- append-only events
- persisted messages, deliveries, dead letters, decisions, handoffs, tasks,
  goals, proposals, and memory markers
- bounded, labelled memory injection

Discourages:

- hidden memory that changes behavior without inspection
- relying on model recollection as the source of truth
- unbounded context stuffing
- treating memory as a substitute for audit trails

## 5. Relationships Over Lists

Objects should become connected operational entities.

Why it exists:

AI work is relational. A proposal may come from a runtime, link to a room,
depend on a decision, produce a handoff, and explain an incident. Lists alone
force the operator to reconstruct those links manually.

Encourages:

- daemon-backed relationship records
- evidence-backed relationship lines in the canvas
- inspector jumps between related objects
- traces that connect messages, deliveries, failures, and governance records
- object models that link rooms, workers, proposals, tasks, goals, decisions,
  handoffs, incidents, and dead letters

Discourages:

- isolated screens that cannot explain context
- client-invented production graph edges
- duplicating relationship logic separately in each UI
- treating records as unrelated rows when durable links exist

## 6. Workspaces Over Screens

The future of SynKraken is spatial operations.

Why it exists:

Operators do not only consume dashboards; they work through connected
situations. Incidents, proposals, runtime health, rooms, and traces need to be
kept in view together.

Encourages:

- spatial canvas workflows
- movable nodes for daemon objects
- local layout persistence
- presets for common operating contexts
- inspector-driven drilldown from a workspace

Discourages:

- reducing every workflow to a fixed table or card list
- moving business state into layout state
- decorative canvas effects without operational value
- fake graph density

## 7. Operators Over Users

SynKraken is an operating system, not a chatbot.

Why it exists:

The person using SynKraken is not merely chatting with a model. They are
directing work, managing runtime reliability, approving authority, reviewing
incidents, and recovering failures.

Encourages:

- operator-first language
- dense, inspectable controls
- explicit status, authority, and recovery surfaces
- practical workflows for rooms, proposals, traces, and incidents

Discourages:

- consumer chatbot framing
- hiding operational complexity behind vague friendliness
- treating the operator as a passive recipient of AI output
- optimizing only for first-message delight

## 8. Governance Before Scale

Scaling unsafe automation is not success.

Why it exists:

More agents, longer loops, and broader execution rights are liabilities unless
the system can govern them. SynKraken should make authority, audit, and
recovery strong before making automation larger.

Encourages:

- bounded discussions, team tasks, and goal runs
- explicit approval modes
- traceability requirements before execution expansion
- conservative defaults
- failure states that stop work visibly

Discourages:

- unbounded agent swarms
- background scheduling without operator command
- scaling hidden autonomy because it demos well
- adding execution power before governance is inspectable

## 9. Heterogeneous Workforce

Workers may come from many runtimes and vendors.

Why it exists:

Operators choose different tools for cost, quality, speed, policy, and local
preference. SynKraken should manage the workforce around those tools without
collapsing into one provider's assumptions.

Encourages:

- leaf adapters
- runtime discovery
- generic worker surfaces
- fallback presentation for unknown adapter ids
- reputation derived from observed behavior rather than vendor identity

Discourages:

- hardcoded fixed worker slots
- provider-specific product assumptions in core concepts
- hiding unsupported runtimes from discovery inventory
- assuming all workers are equally reliable or equally costly

## 10. Local First

The operator owns the control plane.

Why it exists:

AI workforce operation includes transcripts, decisions, failures, memory, and
authority records. The default product should keep that operational state under
operator control.

Encourages:

- loopback daemon APIs
- SQLite as the local source of truth
- operator-owned config and runtime credentials
- local Console, TUI, Web, and CLI surfaces
- clear boundaries around subscriptions, API keys, and runtime costs

Discourages:

- cloud-first assumptions
- hidden remote state
- implying SynKraken pays runtime costs or owns provider accounts
- storing private project context in shipped defaults
