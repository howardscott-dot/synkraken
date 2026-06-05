# Console v0.95 Workforce Operations PRD

## Objective

Make SynKraken Console usable as the primary daily operating surface for
talking to and operating an AI workforce. An operator should be able to create
or open a room, add workers, message the room or individual workers, see
replies and delivery failures, continue the conversation, and clean up rooms
where daemon APIs allow it without opening the TUI.

## Problem

Console can observe missions, outcomes, activity, rooms, incidents, and
governance, but the original SynKraken operating loop still lives mostly in
the TUI and Web Command Deck. Operators can inspect rooms in Console, but room
creation, membership management, worker messaging, delivery summaries, empty
reply handling, failures, and transcript continuation are not yet strong
enough for all-day use.

## User Workflow

1. Open Console and use Workforce Operations as the practical operator home.
2. Create or open a room.
3. Add one worker or all workers to the room.
4. Send a room note, `@everyone`, or `@worker-id` message.
5. Watch the transcript update with operator messages, worker replies, empty
   replies, failures, timeouts, duration, attempts, and delivery summaries.
6. Continue the room conversation from the same screen.
7. Inspect room presence, recent activity, linked mission, linked outcome, and
   pending attention before choosing the next action.
8. Delete or remove individual members when available through daemon APIs.

## Gap Analysis Matrix

| Capability | CLI | TUI | API | Console Before v0.95 |
|---|---|---|---|---|
| Create room | partial through Web/TUI-era APIs, not primary CLI | `/room create` | `POST /v1/rooms` | gap |
| Delete room | not primary CLI | `/room delete` | `DELETE /v1/rooms/{name}` | gap |
| List rooms | `synkraken rooms` | `/rooms` | `GET /v1/rooms` | present |
| View room | not primary CLI | `/open #room`, `/room enter` | `GET /v1/rooms/{name}` | present |
| View room members | limited | `/room members` | `GET /v1/rooms/{name}` | present |
| Add worker to room | not primary CLI | `/room add` | `POST /v1/rooms/{name}/members` | partial |
| Remove worker from room | not primary CLI | `/room remove` | `DELETE /v1/rooms/{name}/members/{adapter}` | partial |
| Add all workers | not primary CLI | `/room add all` loops members | no bulk endpoint | gap |
| Remove all workers | no | no bulk command | no bulk endpoint | unavailable |
| Send message to room | `synkraken send room:name` if target used | plain text in room or `#room` | `POST /v1/messages` target `room:name` | partial |
| Send `@everyone` | `synkraken send broadcast` | `@everyone` | `POST /v1/messages` target room/broadcast | gap |
| Send `@worker-id` | `synkraken send worker` | `@worker-id` | `POST /v1/messages` target worker with room context | gap |
| View delivery results | `synkraken deliveries` | send result panel | dispatch response / `/v1/deliveries` | gap |
| View room history | limited | room transcript | `GET /v1/rooms/{name}/messages` | present |
| Continue conversation | direct send commands | in-room composer | dispatch with conversation/room context | partial |
| View recent broadcasts | recent/deliveries | transcript/result panel | messages/deliveries | gap |
| View empty replies | deliveries | transcript/result panel | delivery status `empty_reply` | gap |
| View failed replies | deliveries/dead letters | transcript/result panel | delivery status/dead letters | gap |
| View timeouts | deliveries/dead letters | transcript/result panel | delivery status/dead letters | gap |
| View room activity | limited | rooms view | `GET /v1/rooms`, room messages | present |
| View room mission/outcome context | no | no | room read model | present |
| Create room preset if available | no | `/room preset` | `POST /v1/rooms/preset` | gap |
| Search room history if available | no | `/room search` | `GET /v1/rooms/{name}/messages?q=` | gap |
| Summarise room if available | no | `/room summarize` | `POST /v1/rooms/{name}/summary` | gap |

## Screens And Components Affected

- Console Rooms screen becomes a Workforce Operations surface.
- Room transcript becomes a proper chat timeline.
- Room members panel gains create, add, remove, add all, refresh, delete, and
  unavailable rename/remove-all actions.
- Delivery panel renders dispatch summaries and delivery rows in
  human-readable form.
- Command palette gains room operation commands.
- Canvas Room nodes gain operational controls for chat, broadcast, members,
  and latest replies.
- Console API client gains wrappers around existing daemon room/message APIs.

## APIs Used Or Changed

Used existing daemon APIs:

- `GET /v1/rooms`
- `POST /v1/rooms`
- `DELETE /v1/rooms/{name}`
- `GET /v1/rooms/{name}`
- `POST /v1/rooms/{name}/members`
- `DELETE /v1/rooms/{name}/members/{adapter_id}`
- `GET /v1/rooms/{name}/messages`
- `GET /v1/rooms/{name}/messages?q=...`
- `POST /v1/rooms/{name}/messages`
- `POST /v1/rooms/{name}/summary`
- `POST /v1/rooms/preset`
- `POST /v1/messages`

No daemon write model or architecture change is required.

API gaps:

- No room rename endpoint.
- No bulk remove-all-members endpoint.
- No dedicated recent broadcasts endpoint.

## Files Expected To Change

- `apps/console/src/App.tsx`
- `apps/console/src/lib/api.ts`
- `apps/console/src/styles.css`
- `apps/console/README.md`
- `docs/UI_CONSOLE_DOCTRINE.md`
- `docs/OPERATOR_GUIDE.md`
- `docs/PRODUCT_DOCTRINE.md`
- `CHANGELOG.md`
- `scripts/console_v095_workforce_operations_smoke_test.py`

## Acceptance Criteria

- Console can create a room.
- Console can delete a room when the daemon API exists.
- Console clearly marks rename and remove-all as unavailable daemon gaps.
- Console can add one worker and add all workers to a room.
- Console can remove one worker from a room.
- Console can open a room transcript and continue the conversation.
- Console can record a plain room note.
- Console can send `@everyone` to room members.
- Console can send `@worker-id` with room context so the exchange appears in
  the room timeline.
- Console shows delivery summary and delivery rows with target, status,
  duration, attempts, preview, failures, timeouts, empty replies, blocked
  states, and suspicious output where present.
- Console shows room presence, recent activity, last message, last broadcast,
  linked mission, and linked outcome.
- Console command palette includes the required room operation commands.
- Room canvas nodes expose useful operational controls without overbuilding the
  canvas.
- Mission and Outcome screens remain routable.

## Test Plan

- `npm run build` from `apps/console`
- `python3 scripts/console_v095_workforce_operations_smoke_test.py`
- `python3 scripts/console_v08_live_operations_smoke_test.py`
- `python3 scripts/console_v09_mission_control_smoke_test.py`
- `python3 scripts/console_v10_outcome_governance_smoke_test.py`
- `python3 scripts/context_audit.py`
- `python3 -m compileall synkraken scripts`
- `git diff --check`

## Out Of Scope

- new mission or outcome features
- autonomy
- scheduling
- planning
- project management
- new entities
- new read models
- new adapters
- runtime scoring changes
- SSE or WebSocket work
- RBAC
- auth
- real shell execution
- AI-generated summaries
