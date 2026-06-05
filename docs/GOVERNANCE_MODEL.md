# Governance Model

SynKraken's governance model exists to keep execution authority visible,
bounded, and auditable.

```text
Agents propose.
Humans approve.
SynKraken executes and records.
```

## Proposal Lifecycle

Proposal statuses:

- `proposed`: a worker or operator has requested action
- `approved`: an operator has approved the proposal
- `rejected`: an operator has rejected the proposal
- `cancelled`: the proposal was withdrawn or stopped before execution
- `executed`: SynKraken recorded execution after approval
- `expired`: the proposal is no longer actionable

Typical transitions:

```text
proposed -> approved -> executed
proposed -> rejected
proposed -> cancelled
proposed -> expired
```

## Approval Model

Approval is explicit. Sensitive actions require human approval before they can
move from proposal to execution record. Governance rules classify risk and
record why approval is required.

Examples of sensitive action categories include shell, git, restart, delete,
write, replay, retry, and memory promotion.

## Execution Model

Execution is operator-controlled. In v0.1, proposal execution is simulated for
sensitive actions and recorded as a durable event. SynKraken does not grant
workers autonomous shell, git, file, restart, replay, retry, or delete
authority through proposal controls.

The simulated execution limitation is intentional. It lets SynKraken build the
authority ledger, review flow, and trace model before adding broader governed
execution.

## Risk Levels

Risk levels are deterministic labels used to explain proposal handling. They
are not an enterprise policy language or AI risk assessment. The goal is to
make approval requirements inspectable and consistent.

## Governance Events

Governance actions append events. Proposal events record proposed, approved,
rejected, cancelled, executed, expired, and related transitions. Team, goal,
decision, handoff, task, memory, and agent events follow the same audit-first
principle.

## Human-In-The-Loop Principle

SynKraken may coordinate workers after an explicit operator action, but it
must not hide loops, silently execute sensitive operations, or convert weak
runtime output into invisible state. Humans remain the authority boundary.

## Auditability

Every governance path should answer:

- what was proposed
- who proposed it
- why it required approval
- who approved, rejected, cancelled, or executed it
- what records it links to
- what happened afterward

## Future Direction

Future governed execution may add richer action adapters, stricter policy
configuration, and role-based authority. That direction must build on the same
visible proposal and event model. Future RBAC should clarify human and runtime
permissions without introducing hidden autonomous execution.

