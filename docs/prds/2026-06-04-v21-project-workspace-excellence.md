# SynKraken v2.1 Project Workspace Excellence

## Product Decision

Projects become the centre of daily company operation.

The project workspace should feel like the place where a company outcome
lives: purpose, current focus, conversations, knowledge, produced work, team
contribution, and decisions in one calm surface.

## Problem

Projects in v2.0 aggregate existing records, but they can still feel like a
summary layer over missions, rooms, memory, proposals, and assignments.

The operator can see a project, but the project does not yet feel like a
workspace where they can spend most of the day.

## Objective

Make Projects feel closer to Notion, Linear, Apple Notes, and Craft than Jira,
Grafana, or an admin dashboard.

When the operator opens SynKraken, the first impression should be:

```text
This is where Studio Blueprint lives.
```

not:

```text
This is where my agents live.
```

## Scope

This sprint is a project experience sprint.

In scope:

- project overview narrative
- project-specific human-readable activity
- deliverables as highly visible project outputs
- inline project conversation
- inline project knowledge note creation and revision
- project team contribution language
- decision narrative language
- Home project cards that foreground active projects
- doctrine documentation for v2.1

Out of scope:

- new backend entities
- new navigation
- new dashboards
- new governance model
- new workforce model
- raw diagnostics in default project team views

## Experience Requirements

Project Overview should answer:

- What is this project?
- Why does it exist?
- What is the current focus?
- What meaningful activity happened last?
- What should the operator do next?
- What has already been produced?

Deliverables should show:

- title
- type
- status
- last updated
- owner
- open action

Conversations should be usable without leaving the project workspace.

Knowledge should be editable inline as project notes while still using the
existing governed memory path.

Team should show contribution and recommended use, not trust metrics or
runtime diagnostics.

Decisions should read as operator language:

- Homepage proposal approved
- Architecture review rejected
- Claude handoff accepted

Empty states must teach the next move.

## Acceptance Criteria

A founder can open a project and, without leaving that project workspace:

- understand the purpose and current focus
- review deliverables
- read the project conversation
- reply to the workforce
- dispatch workers through project conversation prompts
- add or revise knowledge
- understand decisions in plain language
- see worker contribution and recommended use

## Validation Plan

- Console TypeScript build
- project-centric smoke test where available
- source review for no new navigation or backend entities
- screenshot-ready local run
