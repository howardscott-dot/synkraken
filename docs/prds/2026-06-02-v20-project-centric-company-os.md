# SynKraken v2.0 Project-Centric Company OS

## Product Decision

SynKraken is now a Company Operating System powered by an AI Workforce.

The operator-facing model is:

- projects
- conversations
- knowledge
- deliverables
- decisions

The implementation model still includes missions, outcomes, assignments,
memory, proposals, traces, incidents, and workforce records. Those remain
available, but they move behind a project-centric operating model and an
Advanced inspection area.

## Problem

The Console has become architecturally powerful but still asks operators to
think in implementation objects. Missions, outcomes, assignments, proposals,
memory items, and traces are useful records, but they should not be the daily
navigation model.

The operator wants to open a project, talk to workers, store project
knowledge, review outputs, and make decisions.

## Information Architecture

Primary navigation:

- Home
- Projects
- Conversations
- Knowledge
- Workforce
- Advanced

Advanced contains:

- Governance
- Assignments
- Outcomes
- Missions
- Traces
- Canvas
- Incidents
- Runtime Diagnostics
- Proposal Internals
- Dead Letters
- Memory Internals

## Project Model

Project is the operator-facing workspace.

In v2.0, projects are a deterministic view and creation surface over existing
SynKraken records. A project may aggregate:

- missions as strategic containers
- outcomes as deliverables/results
- assignments as implementation ownership
- conversations as project communication
- knowledge as governed memory
- proposals and handoffs as decisions
- traces and incidents as advanced evidence

Project fields:

- project_id
- title
- purpose
- status
- room_id
- mission_id
- outcome_ids
- assignment_ids
- knowledge_ids
- worker_ids
- created_at
- updated_at

For this sprint, the Console may derive projects from missions and locally
created project records while preserving existing daemon-owned data.

## Existing Capability Mapping

Existing SynKraken capabilities remain intact and move into project-facing
surfaces:

- Missions appear as projects when daemon mission records exist.
- Outcomes appear as project deliverables and project status evidence.
- Assignments appear as open deliverables, worker focus, and team activity.
- Rooms appear as project conversations.
- Shared Workforce Memory appears as project Knowledge.
- Proposals appear as project Decisions and project Deliverables when they
  are visible outputs.
- Handoffs appear as recent project handoffs in Decisions.
- Traces remain available from Advanced and replay links.
- Incidents and dead letters remain available from Advanced.
- Runtime health, trust, and diagnostics remain available from Workforce and
  Advanced, but are not the default project team language.

## Home

Home becomes Company Briefing.

It must answer:

- What happened?
- What needs me?
- What should I do next?

The briefing is deterministic and derived from daemon records. It must not use
AI-generated summaries.

## Projects

Projects are the centre of the product.

Project detail tabs:

- Overview
- Conversations
- Knowledge
- Deliverables
- Team
- Decisions

Overview shows purpose, current status, recent activity, recommended next
actions, open deliverables, and workers involved. It avoids governance and
implementation jargon.

Conversations is the default working surface for a project.

Knowledge hides memory implementation details.

Deliverables is a new first-class surface for visible project outputs such as
PRD, Research, Proposal, Architecture, Code Review, Article, Specification,
and Report.

Team shows workers involved, current focus, recent contribution, and status.
Raw health/trust metrics move to Advanced.

Decisions shows pending decisions, approved decisions, rejected decisions, and
recent handoffs using human-facing language.

## Screens Changed

- Home: reframed as Company Briefing.
- Projects: new primary workspace with project creation and project detail
  tabs.
- Conversations: remains a top-level place to talk to the workforce, and is
  also embedded as the default project working surface.
- Knowledge: replaces Memory as the operator-facing daily surface.
- Workforce: keeps worker availability and current work visible while moving
  raw runtime detail to Advanced.
- Advanced: contains governance, work internals, traces, canvas, incidents,
  runtime diagnostics, proposal internals, dead letters, memory internals, and
  settings.

## New IA

Primary navigation:

1. Home
2. Projects
3. Conversations
4. Knowledge
5. Workforce
6. Advanced

Project workspace tabs:

1. Overview
2. Conversations
3. Knowledge
4. Deliverables
5. Team
6. Decisions

## Empty State Doctrine

Every empty state must teach.

Bad:

No records.

Good:

No active projects.

Create a project to organise workforce activity.

## Out Of Scope

- Removing missions, outcomes, assignments, proposals, traces, incidents, or
  memory
- Replacing governance endpoints
- AI-written project summaries
- Cloud collaboration, user accounts, RBAC, or SaaS project management
- Hiding audit trails from Advanced

## Acceptance Criteria

A new operator can:

- create a project
- open a project workspace
- talk to workers
- store knowledge
- review deliverables
- make decisions
- use 80 percent of daily operation without opening Advanced

## Validation Plan

- Console build
- v2.0 source-level smoke test
- context audit
- Python compile
- diff whitespace check
