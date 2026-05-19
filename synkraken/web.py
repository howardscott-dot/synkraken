from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9461
DEFAULT_DAEMON_URL = "http://127.0.0.1:9460"


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SynKraken Command Deck</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">SYNKRAKEN</p>
      <h1>Command Deck</h1>
    </div>
    <div id="bridge-status" class="status">connecting…</div>
  </header>
  <main>
    <aside class="panel rooms">
      <div class="panel-head">
        <h2>Rooms</h2>
        <button id="toggle-room-form" type="button">New</button>
      </div>
      <form id="room-form" class="compact hidden">
        <label for="room-name">Create room</label>
        <input id="room-name" placeholder="general">
        <div id="room-members" class="checks"></div>
        <button type="submit">Create room</button>
      </form>
      <div id="rooms-list" class="stack"></div>
      <section class="memory-panel">
        <div class="panel-head tight">
          <h2>Room Memory</h2>
          <span id="memory-room" class="meta">No room</span>
        </div>
        <form id="memory-form" class="compact">
          <label for="memory-purpose">Purpose</label>
          <input id="memory-purpose">
          <label for="memory-objective">Objective</label>
          <input id="memory-objective">
          <label for="memory-focus">Focus</label>
          <input id="memory-focus">
          <label for="memory-rules">Rules</label>
          <textarea id="memory-rules" rows="2"></textarea>
          <label for="memory-constraints">Constraints</label>
          <textarea id="memory-constraints" rows="2"></textarea>
          <label for="memory-notes">Notes</label>
          <textarea id="memory-notes" rows="2"></textarea>
          <button type="submit">Save memory</button>
        </form>
      </section>
    </aside>
    <section class="panel transcript">
      <div class="panel-head">
        <h2 id="room-title">Select a target</h2>
        <button id="refresh-room" type="button">Refresh</button>
      </div>
      <div id="messages" class="messages empty">Choose a room to view its transcript, or an agent to send a direct message.</div>
      <form id="composer">
        <label for="message-body" id="composer-label">No target selected</label>
        <textarea id="message-body" rows="3" placeholder="Message the selected room…"></textarea>
        <div class="actions">
          <button id="send-target" type="submit">Send</button>
          <button id="broadcast" type="button">Broadcast</button>
          <button id="ask-team" type="button">Ask team</button>
        </div>
      </form>
    </section>
    <aside class="panel agents">
      <h2>Agents</h2>
      <div id="agents-list" class="stack"></div>
    </aside>
    <aside class="panel tasks">
      <h2>Tasks</h2>
      <section class="team-runs-box">
        <h2>Recent Team Runs</h2>
        <div id="team-runs-list" class="stack"></div>
      </section>
      <form id="task-form" class="compact task-form">
        <label for="task-title">Create task</label>
        <input id="task-title" placeholder="Follow up on auth issue">
        <select id="task-agent"></select>
        <select id="task-priority">
          <option value="low">low</option>
          <option value="normal" selected>normal</option>
          <option value="high">high</option>
        </select>
        <label class="inline">
          <input id="task-current-room" type="checkbox" checked>
          associate with current room
        </label>
        <button type="submit">Create task</button>
      </form>
      <div id="tasks-list" class="stack"></div>
    </aside>
  </main>
  <footer id="notice">Local command deck · backend via existing daemon API</footer>
  <script src="/app.js"></script>
</body>
</html>
"""


STYLES_CSS = """
:root {
  color-scheme: dark;
  --bg: #07131c;
  --panel: #0d1f2b;
  --panel-2: #102735;
  --line: #21475b;
  --text: #e6f6fb;
  --muted: #8fb2c0;
  --accent: #56e0d4;
  --room: #d29cff;
  --ok: #7be495;
  --warn: #ffcc66;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: radial-gradient(circle at top, #10384a, var(--bg) 48%);
  color: var(--text);
  font: 15px/1.4 system-ui, sans-serif;
}
header, footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
}
h1, h2, p { margin: 0; }
h1 { font-size: 1.4rem; }
h2 { font-size: 1rem; color: var(--accent); }
.eyebrow { color: var(--muted); letter-spacing: .18em; font-size: .72rem; }
.status { color: var(--muted); }
.status.ok { color: var(--ok); }
main {
  display: grid;
  gap: 1rem;
  grid-template-columns: 220px minmax(420px, 1fr) 220px 300px;
  padding: 0 1.25rem;
}
.panel {
  min-height: calc(100vh - 130px);
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1rem;
}
.stack { display: grid; gap: .6rem; margin-top: 1rem; }
.item {
  width: 100%;
  text-align: left;
  background: var(--panel-2);
  border: 1px solid transparent;
  color: var(--text);
  border-radius: 12px;
  padding: .75rem;
}
button.item { cursor: pointer; }
.item.active { border-color: var(--room); }
.meta { display: block; color: var(--muted); font-size: .82rem; margin-top: .18rem; }
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.panel-head.tight { margin-bottom: .5rem; }
.memory-panel {
  border-top: 1px solid var(--line);
  margin-top: 1rem;
  padding-top: 1rem;
}
.memory-panel form { border-top: 0; margin-top: .5rem; }
button {
  background: var(--panel-2);
  border: 1px solid var(--line);
  color: var(--text);
  border-radius: 10px;
  padding: .55rem .75rem;
}
button:hover { border-color: var(--accent); }
.messages {
  height: calc(100vh - 330px);
  overflow: auto;
  display: grid;
  align-content: start;
  gap: .7rem;
  padding-right: .25rem;
}
.messages.empty { color: var(--muted); }
.message {
  background: var(--panel-2);
  border-left: 3px solid var(--accent);
  border-radius: 12px;
  padding: .75rem;
}
.message.activity {
  border-left-color: var(--warn);
  color: var(--muted);
}
.message.activity.failed {
  border-left-color: #ff8a80;
  color: var(--text);
}
.message .head {
  display: flex;
  gap: .5rem;
  color: var(--muted);
  font-size: .82rem;
  margin-bottom: .35rem;
}
.message .speaker { color: var(--accent); }
form {
  border-top: 1px solid var(--line);
  margin-top: 1rem;
  padding-top: 1rem;
}
label { display: block; color: var(--muted); margin-bottom: .5rem; }
textarea {
  width: 100%;
  resize: vertical;
  background: #081720;
  border: 1px solid var(--line);
  border-radius: 12px;
  color: var(--text);
  padding: .75rem;
}
input {
  width: 100%;
  background: #081720;
  border: 1px solid var(--line);
  border-radius: 10px;
  color: var(--text);
  padding: .6rem;
}
select {
  width: 100%;
  background: #081720;
  border: 1px solid var(--line);
  border-radius: 10px;
  color: var(--text);
  padding: .6rem;
}
.compact {
  display: grid;
  gap: .6rem;
  border-bottom: 1px solid var(--line);
  margin: .75rem 0 1rem;
  padding-bottom: 1rem;
}
.hidden { display: none; }
.checks {
  display: grid;
  gap: .35rem;
  color: var(--muted);
  font-size: .88rem;
}
.checks label {
  display: flex;
  gap: .45rem;
  align-items: center;
  margin: 0;
}
.checks input {
  width: auto;
}
.typing {
  color: var(--warn);
}
.inline {
  display: flex;
  align-items: center;
  gap: .45rem;
  margin: 0;
}
.inline input { width: auto; }
.team-runs-box {
  border-bottom: 1px solid var(--line);
  margin-bottom: 1rem;
  padding-bottom: .75rem;
}
.team-run { display: grid; gap: .4rem; }
.team-run.status-awaiting_approval { border-color: var(--warn); }
.team-run.status-approved,
.team-run.status-completed { border-color: var(--ok); }
.team-run.status-rejected,
.team-run.status-failed,
.team-run.status-blocked { border-color: #ff8a80; }
.team-actions { display: flex; gap: .45rem; }
.task { display: grid; gap: .55rem; }
.task.status-blocked { border-color: #ff8a80; }
.task.status-open { border-color: var(--accent); }
.task.status-in_progress { border-color: var(--warn); }
.task.status-done { border-color: var(--ok); opacity: .8; }
.task-title { font-weight: 600; }
.task-controls { display: grid; grid-template-columns: 1fr 1fr; gap: .45rem; }
.task-details {
  border-top: 1px solid var(--line);
  padding-top: .5rem;
  color: var(--muted);
  font-size: .82rem;
}
.presence-line {
  display: flex;
  justify-content: space-between;
  gap: .5rem;
}
.presence-status { color: var(--accent); }
.presence-detail { color: var(--muted); font-size: .78rem; margin-top: .25rem; }
.message-actions { margin-top: .45rem; }
.tiny { padding: .3rem .45rem; font-size: .78rem; }
.actions { display: flex; gap: .6rem; margin-top: .65rem; }
#send-target { border-color: var(--room); }
#broadcast { border-color: var(--accent); }
footer { color: var(--muted); font-size: .85rem; }
@media (max-width: 900px) {
  main { grid-template-columns: 1fr; }
  .panel { min-height: auto; }
  .messages { height: 360px; }
}
"""


APP_JS = r"""
const state = {
  rooms: [],
  agents: [],
  tasks: [],
  teamRuns: [],
  memory: null,
  currentRoom: null,
  currentAgent: null,
  currentDiscussion: false,
  typing: new Set(),
  activeDeliveries: new Map(),
  visibleRows: [],
};
const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function setNotice(text) { $("notice").textContent = text; }
function esc(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}
function hhmmss(iso) { return iso ? iso.slice(11, 19) : ""; }
function timeAgo(iso) {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}
function presenceMarker(status) {
  return {
    working: "◐",
    idle: "○",
    online: "●",
    blocked: "✗",
    offline: "○",
    disabled: "○",
    configured: "○",
  }[status || "configured"] || "○";
}
function deliveryKey(data) {
  const target = data.delivery_target || data.adapter_id;
  return data.message_id && target ? `${data.message_id}:${target}` : null;
}
function rememberDelivery(eventName, data) {
  const key = deliveryKey(data || {});
  if (!key) return;
  const previous = state.activeDeliveries.get(key) || {};
  let status = data.status || previous.status || "thinking";
  if (eventName === "delivery.queued") status = "queued";
  if (eventName === "delivery.sent") status = "sent";
  if (eventName === "typing.started") status = "thinking";
  if (eventName === "delivery.recorded") status = data.status || (data.ok ? "replied" : "failed");
  if (eventName === "dead-letter.recorded") status = data.status || "failed";
  const now = Date.now();
  const row = {
    ...previous,
    ...data,
    adapter_id: data.adapter_id || data.delivery_target || previous.adapter_id,
    delivery_target: data.delivery_target || data.adapter_id || previous.delivery_target,
    runtime_name: data.runtime_name || previous.runtime_name || data.adapter_id || data.delivery_target,
    conversation_id: data.conversation_id || previous.conversation_id,
    original_target: data.original_target || previous.original_target,
    reply_context: data.reply_context || previous.reply_context,
    status,
    updated_at: now,
    expires_at: ["replied"].includes(status) ? now + 1500 : ["failed", "timeout"].includes(status) ? now + 300000 : null,
  };
  state.activeDeliveries.set(key, row);
}
function rememberDiscussionTurn(data) {
  const discussionId = data.discussion_id || data.conversation_id;
  const key = `discussion:${discussionId}:${data.turn}`;
  const target = data.room_name ? `room:${data.room_name}` : "discussion";
  state.activeDeliveries.set(key, {
    adapter_id: data.adapter_id,
    delivery_target: data.adapter_id,
    runtime_name: data.runtime_name || data.adapter_id,
    conversation_id: data.conversation_id,
    original_target: target,
    reply_context: target,
    status: "thinking",
    label: data.label,
    updated_at: Date.now(),
    expires_at: null,
  });
}
function completeDiscussion(data) {
  for (const row of state.activeDeliveries.values()) {
    if (row.conversation_id === data.conversation_id) row.expires_at = Date.now() + 2000;
  }
}
function pruneDeliveries() {
  const now = Date.now();
  for (const [key, row] of state.activeDeliveries.entries()) {
    if (row.expires_at && row.expires_at < now) state.activeDeliveries.delete(key);
  }
}
function currentActivityRows() {
  pruneDeliveries();
  const target = state.currentRoom ? `room:${state.currentRoom}` : state.currentDiscussion ? "discussion" : state.currentAgent;
  return [...state.activeDeliveries.values()].filter((row) =>
    row.reply_context === target ||
    row.original_target === target ||
    row.delivery_target === target ||
    row.adapter_id === target
  );
}
function activityText(row) {
  if (row.label) return row.label;
  const name = row.runtime_name || row.adapter_id || row.delivery_target || "agent";
  const phrase = ["queued", "sent", "thinking"].includes(row.status) ? "thinking…" :
    row.status === "replied" ? "replied" :
    row.status === "timeout" ? "timeout" :
    row.status === "failed" ? "failed" : "working…";
  const error = ["failed", "timeout"].includes(row.status) && (row.error || row.reason)
    ? ` · ${row.error || row.reason}` : "";
  return `${name} ${phrase}${error}`;
}
function renderMessageRows(rows, { taskButtons = false } = {}) {
  const activity = currentActivityRows();
  const byMessage = new Map();
  for (const row of activity) {
    const list = byMessage.get(row.message_id) || [];
    list.push(row);
    byMessage.set(row.message_id, list);
  }
  const html = [];
  for (const message of rows) {
    html.push(`
      <article class="message">
        <div class="head">
          <span class="speaker">${esc(message.source)}</span>
          <span>${hhmmss(message.timestamp)}</span>
        </div>
        <div>${esc(message.body)}</div>
        ${taskButtons && !(message.message_id || "").startsWith("pending:") ? `<div class="message-actions">
          <button class="tiny" type="button" data-task-message="${esc(message.message_id)}" data-task-title="${esc(message.body)}">Create task</button>
        </div>` : ""}
      </article>
    `);
    for (const row of byMessage.get(message.message_id) || []) {
      html.push(activityHtml(row));
    }
    byMessage.delete(message.message_id);
  }
  for (const rows of byMessage.values()) {
    for (const row of rows) html.push(activityHtml(row));
  }
  const box = $("messages");
  box.className = "messages";
  box.innerHTML = html.join("") || `<div class="meta">No messages yet.</div>`;
  if (taskButtons) bindMessageTaskButtons();
  box.scrollTop = box.scrollHeight;
}
function activityHtml(row) {
  const failed = ["failed", "timeout"].includes(row.status) ? " failed" : "";
  return `
    <article class="message activity${failed}">
      <div class="head">
        <span class="speaker">${esc(row.runtime_name || row.adapter_id || row.delivery_target)}</span>
        <span>${esc(row.status || "thinking")}</span>
      </div>
      <div>${esc(activityText(row))}</div>
    </article>
  `;
}

async function refreshHealth() {
  try {
    const health = await api("/health");
    $("bridge-status").textContent = health.ok ? "bridge online" : "bridge unavailable";
    $("bridge-status").className = `status ${health.ok ? "ok" : ""}`;
  } catch {
    $("bridge-status").textContent = "bridge unavailable";
    $("bridge-status").className = "status";
  }
}

async function refreshAgents() {
  const data = await api("/v1/agents");
  state.agents = data.agents || [];
  $("agents-list").innerHTML = state.agents.map((agent) => `
    <button class="item ${agent.adapter_id === state.currentAgent ? "active" : ""}" data-agent="${esc(agent.adapter_id)}">
      <span class="presence-line">
        <strong>${esc(agent.runtime_name || agent.adapter_id)}</strong>
        <span class="presence-status">${presenceMarker(agent.status)} ${esc(agent.status || "configured")}</span>
      </span>
      <span class="meta">${esc(agent.adapter_id)} · last seen ${timeAgo(agent.last_seen_at)}${state.typing.has(agent.adapter_id) ? ' · <span class="typing">typing…</span>' : ""}</span>
      <span class="presence-detail">room: ${esc(agent.current_room || "none")}</span>
      <span class="presence-detail">task: ${esc(agent.current_task_id || "none")}</span>
    </button>
  `).join("") || `<div class="meta">No agents configured.</div>`;
  $("room-members").innerHTML = state.agents.map((agent) => `
    <label>
      <input type="checkbox" value="${esc(agent.adapter_id)}">
      ${esc(agent.runtime_name || agent.adapter_id)}
    </label>
  `).join("");
  $("task-agent").innerHTML = `<option value="">unassigned</option>` + state.agents.map((agent) => `
    <option value="${esc(agent.adapter_id)}">${esc(agent.runtime_name || agent.adapter_id)}</option>
  `).join("");
  document.querySelectorAll("[data-agent]").forEach((el) => {
    el.addEventListener("click", () => selectAgent(el.dataset.agent));
  });
}

async function refreshRooms() {
  const data = await api("/v1/rooms");
  state.rooms = data.rooms || [];
  $("rooms-list").innerHTML = state.rooms.map((room) => `
    <button class="item ${room.name === state.currentRoom ? "active" : ""}" data-room="${esc(room.name)}">
      #${esc(room.name)}
      <span class="meta">${room.member_count} member${room.member_count === 1 ? "" : "s"}</span>
    </button>
  `).join("") || `<div class="meta">No rooms yet.</div>`;
  document.querySelectorAll("[data-room]").forEach((el) => {
    el.addEventListener("click", () => selectRoom(el.dataset.room));
  });
}

async function selectRoom(name) {
  state.currentRoom = name;
  state.currentAgent = null;
  state.currentDiscussion = false;
  state.visibleRows = [];
  $("room-title").textContent = `#${name}`;
  $("composer-label").textContent = `Send to #${name}`;
  $("send-target").disabled = false;
  $("message-body").placeholder = `Message #${name}…`;
  await refreshRooms();
  await refreshAgents();
  await refreshMessages();
  await refreshMemory();
  await refreshTeamRuns();
  await refreshTasks();
}

async function selectAgent(adapterId) {
  state.currentAgent = adapterId;
  state.currentRoom = null;
  state.currentDiscussion = false;
  const agent = state.agents.find((item) => item.adapter_id === adapterId);
  const label = agent?.runtime_name || adapterId;
  $("room-title").textContent = `@${label}`;
  $("composer-label").textContent = `Send directly to ${label}`;
  $("send-target").disabled = false;
  $("message-body").placeholder = `Message ${label}…`;
  $("messages").className = "messages empty";
  $("messages").textContent = "Send a direct message to start a conversation.";
  state.visibleRows = [];
  clearMemoryForm();
  await refreshRooms();
  await refreshAgents();
  await refreshTeamRuns();
  await refreshTasks();
}

function setMemoryDisabled(disabled) {
  ["memory-purpose", "memory-objective", "memory-focus", "memory-rules", "memory-constraints", "memory-notes"]
    .forEach((id) => { $(id).disabled = disabled; });
}

function fillMemoryForm(memory = {}) {
  $("memory-room").textContent = state.currentRoom ? `#${state.currentRoom}` : "No room";
  $("memory-purpose").value = memory.purpose || "";
  $("memory-objective").value = memory.objective || "";
  $("memory-focus").value = memory.current_focus || "";
  $("memory-rules").value = memory.rules || "";
  $("memory-constraints").value = memory.constraints || "";
  $("memory-notes").value = memory.notes || "";
}

function clearMemoryForm() {
  state.memory = null;
  fillMemoryForm({});
  setMemoryDisabled(true);
}

async function refreshMemory() {
  if (!state.currentRoom) {
    clearMemoryForm();
    return;
  }
  setMemoryDisabled(false);
  const memory = await api(`/v1/rooms/${encodeURIComponent(state.currentRoom)}/memory`);
  state.memory = memory;
  fillMemoryForm(memory);
}

async function saveMemory() {
  if (!state.currentRoom) return;
  const payload = {
    purpose: $("memory-purpose").value,
    objective: $("memory-objective").value,
    current_focus: $("memory-focus").value,
    rules: $("memory-rules").value,
    constraints: $("memory-constraints").value,
    notes: $("memory-notes").value,
    actor: "synkraken-web",
  };
  state.memory = await api(`/v1/rooms/${encodeURIComponent(state.currentRoom)}/memory`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  fillMemoryForm(state.memory);
  setNotice(`saved memory for #${state.currentRoom}`);
}

async function refreshMessages() {
  if (!state.currentRoom) return;
  const data = await api(`/v1/rooms/${encodeURIComponent(state.currentRoom)}/messages?limit=100`);
  const messages = data.messages || [];
  state.visibleRows = messages;
  renderMessageRows(messages, { taskButtons: true });
}

function renderConversation(data) {
  const rows = [];
  for (const message of data.messages || []) {
    rows.push({
      source: message.source,
      timestamp: message.timestamp,
      body: message.body,
    });
    for (const delivery of (data.deliveries || []).filter((item) => item.message_id === message.message_id)) {
      if (delivery.body) {
        rows.push({
          source: delivery.adapter_id,
          timestamp: delivery.created_at,
          body: delivery.body,
        });
      }
    }
  }
  state.visibleRows = rows;
  renderMessageRows(rows);
}

function bindMessageTaskButtons() {
  document.querySelectorAll("[data-task-message]").forEach((el) => {
    el.addEventListener("click", async () => {
      const title = (el.dataset.taskTitle || "").trim().slice(0, 120) || "Follow up";
      try {
        await createTask({
          title,
          source_message_id: el.dataset.taskMessage,
          room_name: state.currentRoom,
        });
      } catch (error) {
        setNotice(`task creation failed: ${error.message}`);
      }
    });
  });
}

async function refreshTasks() {
  const suffix = state.currentRoom ? `?room=${encodeURIComponent(state.currentRoom)}` : "";
  const data = await api(`/v1/tasks${suffix}`);
  state.tasks = data.tasks || [];
  $("tasks-list").innerHTML = state.tasks.map((task) => `
    <article class="item task status-${esc(task.status)}">
      <div class="task-title">${esc(task.title)}</div>
      <span class="meta">
        ${esc(task.status)} · ${esc(task.priority)}
        ${task.assigned_agent_id ? ` · ${esc(task.assigned_agent_id)}` : ""}
      </span>
      <div class="task-controls">
        <select data-task-status="${esc(task.task_id)}">
          ${["open", "in_progress", "blocked", "done"].map((status) => `<option value="${status}" ${status === task.status ? "selected" : ""}>${status}</option>`).join("")}
        </select>
        <select data-task-priority="${esc(task.task_id)}">
          ${["low", "normal", "high"].map((priority) => `<option value="${priority}" ${priority === task.priority ? "selected" : ""}>${priority}</option>`).join("")}
        </select>
      </div>
      <select data-task-agent="${esc(task.task_id)}">
        <option value="" ${task.assigned_agent_id ? "" : "selected"}>unassigned</option>
        ${state.agents.map((agent) => `<option value="${esc(agent.adapter_id)}" ${agent.adapter_id === task.assigned_agent_id ? "selected" : ""}>${esc(agent.runtime_name || agent.adapter_id)}</option>`).join("")}
      </select>
      <button class="tiny" type="button" data-task-details="${esc(task.task_id)}">Details</button>
      <div id="task-details-${esc(task.task_id)}" class="task-details hidden"></div>
    </article>
  `).join("") || `<div class="meta">No tasks${state.currentRoom ? ` for #${esc(state.currentRoom)}` : ""}.</div>`;
  document.querySelectorAll("[data-task-status]").forEach((el) => {
    el.addEventListener("change", () => updateTask(el.dataset.taskStatus, { status: el.value }));
  });
  document.querySelectorAll("[data-task-priority]").forEach((el) => {
    el.addEventListener("change", () => updateTask(el.dataset.taskPriority, { priority: el.value }));
  });
  document.querySelectorAll("[data-task-agent]").forEach((el) => {
    el.addEventListener("change", () => updateTask(el.dataset.taskAgent, { assigned_agent_id: el.value || null }));
  });
  document.querySelectorAll("[data-task-details]").forEach((el) => {
    el.addEventListener("click", () => toggleTaskDetails(el.dataset.taskDetails));
  });
}

async function refreshTeamRuns() {
  const suffix = state.currentRoom ? `?room=${encodeURIComponent(state.currentRoom)}` : "";
  const data = await api(`/v1/team-runs${suffix}`);
  state.teamRuns = data.team_runs || [];
  $("team-runs-list").innerHTML = state.teamRuns.map((run) => `
    <article class="item team-run status-${esc(run.status)}">
      <strong>${esc(run.status)}</strong>
      <span class="meta">owner: ${esc(run.owner_agent || "none")}</span>
      <span class="meta">reviewers: ${esc((run.reviewers || []).join(", ") || "none")}</span>
      <span class="meta">approval: ${run.approval_required ? esc(run.approved_by || "required") : "auto"}</span>
      <span class="meta">${esc((run.source_prompt || "").slice(0, 90))}</span>
      ${["failed", "blocked"].includes(run.status) ? `<button class="tiny" type="button" data-team-details="${esc(run.team_run_id)}">Details</button>` : ""}
      <div id="team-details-${esc(run.team_run_id)}" class="task-details hidden"></div>
      ${run.status === "awaiting_approval" ? `
        <div class="team-actions">
          <button class="tiny" type="button" data-team-approve="${esc(run.team_run_id)}">Approve</button>
          <button class="tiny" type="button" data-team-reject="${esc(run.team_run_id)}">Reject</button>
        </div>
      ` : ""}
    </article>
  `).join("") || `<div class="meta">No team runs${state.currentRoom ? ` for #${esc(state.currentRoom)}` : ""}.</div>`;
  document.querySelectorAll("[data-team-approve]").forEach((el) => {
    el.addEventListener("click", () => approveTeamRun(el.dataset.teamApprove));
  });
  document.querySelectorAll("[data-team-reject]").forEach((el) => {
    el.addEventListener("click", () => rejectTeamRun(el.dataset.teamReject));
  });
  document.querySelectorAll("[data-team-details]").forEach((el) => {
    el.addEventListener("click", () => toggleTeamRunDetails(el.dataset.teamDetails));
  });
}

async function toggleTeamRunDetails(teamRunId) {
  const box = $(`team-details-${teamRunId}`);
  if (!box.classList.contains("hidden")) {
    box.classList.add("hidden");
    return;
  }
  const run = await api(`/v1/team-runs/${encodeURIComponent(teamRunId)}`);
  const failure = run.failure_summary || {};
  const events = (run.events || []).slice(-8);
  const messages = (failure.partial_transcript || run.messages || []).slice(-8);
  box.innerHTML = `
    <div>phase: ${esc(failure.phase || "unknown")} · agent: ${esc(failure.agent || "unknown")} · elapsed: ${failure.elapsed_ms ?? "unknown"}ms</div>
    <div>reason: ${esc(failure.reason || run.status || "unknown")}</div>
    <div>events:</div>
    ${events.map((event) => `<div>• ${esc(event.event_type)} ${event.actor ? `by ${esc(event.actor)}` : ""}</div>`).join("") || "<div>• none</div>"}
    <div>partial transcript:</div>
    ${messages.map((message) => `<div>• <strong>${esc(message.source || "")}</strong>: ${esc((message.body || "").slice(0, 220))}</div>`).join("") || "<div>• none</div>"}
  `;
  box.classList.remove("hidden");
}

async function approveTeamRun(teamRunId) {
  await api(`/v1/team-runs/${encodeURIComponent(teamRunId)}/approve`, {
    method: "POST",
    body: JSON.stringify({ actor: "synkraken-web" }),
  });
  await Promise.all([refreshTeamRuns(), refreshTasks(), state.currentRoom ? refreshMessages() : Promise.resolve()]);
  setNotice("team run approved");
}

async function rejectTeamRun(teamRunId) {
  await api(`/v1/team-runs/${encodeURIComponent(teamRunId)}/reject`, {
    method: "POST",
    body: JSON.stringify({ actor: "synkraken-web" }),
  });
  await Promise.all([refreshTeamRuns(), refreshTasks(), state.currentRoom ? refreshMessages() : Promise.resolve()]);
  setNotice("team run rejected");
}

async function toggleTaskDetails(taskId) {
  const box = $(`task-details-${taskId}`);
  if (!box.classList.contains("hidden")) {
    box.classList.add("hidden");
    return;
  }
  const task = state.tasks.find((item) => item.task_id === taskId);
  const data = await api(`/v1/tasks/${encodeURIComponent(taskId)}/events`);
  const recent = (data.events || []).slice(-5);
  box.innerHTML = `
    <div>created by ${esc(task.created_by)} · ${esc(task.created_at)}</div>
    <div>updated by ${esc(task.updated_by)} · ${esc(task.updated_at)}</div>
    <div>recent events:</div>
    ${recent.map((event) => `<div>• ${esc(event.event_type)} by ${esc(event.actor)}</div>`).join("") || "<div>• none</div>"}
  `;
  box.classList.remove("hidden");
}

async function createTask(overrides = {}) {
  const title = (overrides.title ?? $("task-title").value).trim();
  if (!title) return;
  const payload = {
    title,
    status: "open",
    priority: $("task-priority").value,
    assigned_agent_id: $("task-agent").value || null,
    room_name: $("task-current-room").checked ? state.currentRoom : null,
    actor: "synkraken-web",
    ...overrides,
  };
  await api("/v1/tasks", { method: "POST", body: JSON.stringify(payload) });
  $("task-title").value = "";
  await refreshTasks();
  setNotice("task created");
}

async function updateTask(taskId, patch) {
  try {
    await api(`/v1/tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      body: JSON.stringify({ ...patch, actor: "synkraken-web" }),
    });
    await refreshTasks();
  } catch (error) {
    setNotice(`task update failed: ${error.message}`);
  }
}

function resolveSend(target, rawBody) {
  let body = rawBody.trim();
  if (!body) return { target, body };
  if (body.startsWith("@everyone --global ")) {
    return { target: "broadcast", body: body.slice("@everyone --global ".length).trim() };
  }
  if (body.startsWith("@everyone ")) {
    return {
      target: state.currentRoom ? `room:${state.currentRoom}` : "broadcast",
      body: body.slice("@everyone ".length).trim(),
    };
  }
  return { target, body };
}

function parseDiscussion(rawBody) {
  const text = rawBody.trim();
  if (!text.startsWith("/discuss ")) return null;
  const matches = [...text.slice("/discuss ".length).matchAll(/"([^"]+)"|'([^']+)'|(\S+)/g)]
    .map((match) => match[1] ?? match[2] ?? match[3]);
  let maxTurns = 4;
  let roomName = state.currentRoom;
  const values = [];
  for (let i = 0; i < matches.length; i += 1) {
    if (matches[i] === "--turns") {
      i += 1;
      maxTurns = Number.parseInt(matches[i] || "4", 10);
    } else if (matches[i] === "--room") {
      i += 1;
      roomName = (matches[i] || "").replace(/^#/, "");
    } else {
      values.push(matches[i]);
    }
  }
  if (values.length < 3) throw new Error('usage: /discuss [--turns N] [--room name] <agent1> <agent2> "topic"');
  return { agents: values.slice(0, -1), topic: values.at(-1), max_turns: maxTurns, room_name: roomName || null };
}

function parseTeam(rawBody) {
  const text = rawBody.trim();
  if (!text.startsWith("/team ")) return null;
  const matches = [...text.slice("/team ".length).matchAll(/"([^"]+)"|'([^']+)'|(\S+)/g)]
    .map((match) => match[1] ?? match[2] ?? match[3]);
  let turns = 4;
  const values = [];
  for (let i = 0; i < matches.length; i += 1) {
    if (matches[i] === "--turns") {
      i += 1;
      turns = Number.parseInt(matches[i] || "4", 10);
    } else {
      values.push(matches[i]);
    }
  }
  const question = values.join(" ").trim();
  if (!state.currentRoom) throw new Error("Team mode needs a room. Create or select a room first.");
  if (!question) throw new Error('usage: /team [--turns N] "question or task"');
  return { room_name: state.currentRoom, question, turns };
}

async function discuss(payload) {
  if (!payload.room_name) {
    state.currentRoom = null;
    state.currentAgent = null;
    state.currentDiscussion = true;
    $("room-title").textContent = "Discussion";
    $("composer-label").textContent = "Discussion complete";
  }
  state.visibleRows = [
    ...state.visibleRows,
    { source: "synkraken-web", target: payload.room_name ? `room:${payload.room_name}` : "discussion", body: `Discussion topic: ${payload.topic}`, timestamp: new Date().toISOString(), message_id: `pending-discussion:${Date.now()}` },
  ];
  renderMessageRows(state.visibleRows, { taskButtons: Boolean(state.currentRoom) });
  const result = await api("/v1/discussions", {
    method: "POST",
    body: JSON.stringify({ source: "synkraken-web", ...payload }),
  });
  $("message-body").value = "";
  setNotice(`discussion complete: ${result.status}`);
  if (payload.room_name) {
    if (state.currentRoom !== payload.room_name) await selectRoom(payload.room_name);
    else await refreshMessages();
  } else {
    const conversation = await api(`/v1/conversations/${result.conversation_id}`);
    renderConversation(conversation);
  }
}

async function askTeam(payload) {
  if (!payload.room_name) throw new Error("Team mode needs a room. Create or select a room first.");
  state.visibleRows = [
    ...state.visibleRows,
    { source: "synkraken-web", target: `room:${payload.room_name}`, body: `Team task: ${payload.question}`, timestamp: new Date().toISOString(), message_id: `pending-team:${Date.now()}` },
  ];
  renderMessageRows(state.visibleRows, { taskButtons: true });
  const result = await api("/v1/team-tasks", {
    method: "POST",
    body: JSON.stringify({ source: "synkraken-web", ...payload }),
  });
  $("message-body").value = "";
  setNotice(`team task ${result.status}: ${result.owner || "no owner"}`);
  await refreshMessages();
  await refreshTasks();
  await refreshTeamRuns();
}

async function send(target) {
  const rawBody = $("message-body").value.trim();
  if (!rawBody) return;
  const team = parseTeam(rawBody);
  if (team) {
    await askTeam(team);
    return;
  }
  const discussion = parseDiscussion(rawBody);
  if (discussion) {
    await discuss(discussion);
    return;
  }
  const resolved = resolveSend(target, rawBody);
  state.visibleRows = [
    ...state.visibleRows,
    { source: "synkraken-web", target: resolved.target, body: resolved.body, timestamp: new Date().toISOString(), message_id: `pending:${Date.now()}` },
  ];
  renderMessageRows(state.visibleRows, { taskButtons: Boolean(state.currentRoom) });
  const result = await api("/v1/messages", {
    method: "POST",
    body: JSON.stringify({ source: "synkraken-web", target: resolved.target, body: resolved.body }),
  });
  $("message-body").value = "";
  setNotice(`sent to ${resolved.target}`);
  if (state.currentRoom) await refreshMessages();
  if (state.currentAgent) {
    const conversation = await api(`/v1/conversations/${result.message.conversation_id}`);
    renderConversation(conversation);
  }
}

$("composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = state.currentRoom ? `room:${state.currentRoom}` : state.currentAgent;
  if (!target) return;
  try {
    await send(target);
  } catch (error) {
    setNotice(`send failed: ${error.message}`);
  }
});
$("broadcast").addEventListener("click", async () => {
  try {
    await send(state.currentRoom ? `room:${state.currentRoom}` : "broadcast");
  } catch (error) {
    setNotice(`broadcast failed: ${error.message}`);
  }
});
$("ask-team").addEventListener("click", async () => {
  try {
    const question = $("message-body").value.trim();
    if (!state.currentRoom) throw new Error("Team mode needs a room. Create or select a room first.");
    if (!question) return;
    await askTeam({ room_name: state.currentRoom, question, turns: 4 });
  } catch (error) {
    setNotice(`team task failed: ${error.message}`);
  }
});
$("refresh-room").addEventListener("click", refreshMessages);
$("send-target").disabled = true;
$("toggle-room-form").addEventListener("click", () => $("room-form").classList.toggle("hidden"));
$("room-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = $("room-name").value.trim().toLowerCase();
  const members = [...document.querySelectorAll("#room-members input:checked")].map((el) => el.value);
  if (!name) return;
  try {
    await api("/v1/rooms", {
      method: "POST",
      body: JSON.stringify({ name, description: "", members }),
    });
    $("room-name").value = "";
    $("room-form").classList.add("hidden");
    await refreshRooms();
    await selectRoom(name);
    setNotice(`created #${name}`);
  } catch (error) {
    setNotice(`room creation failed: ${error.message}`);
  }
});
$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await createTask();
  } catch (error) {
    setNotice(`task creation failed: ${error.message}`);
  }
});
$("memory-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await saveMemory();
  } catch (error) {
    setNotice(`memory update failed: ${error.message}`);
  }
});

async function bootstrap() {
  clearMemoryForm();
  await Promise.all([refreshHealth(), refreshAgents(), refreshRooms(), refreshTasks(), refreshTeamRuns()]);
  if (state.rooms[0]) await selectRoom(state.rooms[0].name);
  const events = new EventSource("/api/v1/events/stream");
  events.onmessage = async (event) => {
    try {
      const payload = JSON.parse(event.data);
      const data = payload.data || {};
      const adapterId = data.adapter_id;
      if (payload.event === "typing.started" && adapterId) state.typing.add(adapterId);
      if (payload.event === "typing.stopped" && adapterId) state.typing.delete(adapterId);
      if (["delivery.queued", "delivery.sent", "typing.started", "delivery.recorded", "dead-letter.recorded"].includes(payload.event)) {
        rememberDelivery(payload.event, data);
        renderMessageRows(state.visibleRows, { taskButtons: Boolean(state.currentRoom) });
      }
      if (payload.event === "discussion.turn") {
        rememberDiscussionTurn(data);
        renderMessageRows(state.visibleRows, { taskButtons: Boolean(state.currentRoom) });
      }
      if (payload.event === "discussion.completed") {
        completeDiscussion(data);
        renderMessageRows(state.visibleRows, { taskButtons: Boolean(state.currentRoom) });
      }
      if (["message.accepted", "delivery.recorded", "dead-letter.recorded", "discussion.turn", "discussion.completed"].includes(payload.event)) {
        await Promise.all([refreshRooms(), state.currentRoom ? refreshMessages() : Promise.resolve()]);
      }
      if (payload.event.startsWith("task.")) await refreshTasks();
      if (payload.event.startsWith("team.")) await refreshTeamRuns();
      if (payload.event === "room.memory.updated" && data.room === state.currentRoom) await refreshMemory();
      if (payload.event.startsWith("typing.") || payload.event === "agent.presence") await refreshAgents();
    } catch (_) {}
  };
  events.onerror = () => setNotice("event stream reconnecting…");
}
bootstrap().catch((error) => setNotice(`startup failed: ${error.message}`));
"""


class CommandDeckHandler(BaseHTTPRequestHandler):
    daemon_url = DEFAULT_DAEMON_URL

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(INDEX_HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_text(STYLES_CSS, "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_text(APP_JS, "application/javascript; charset=utf-8")
            return
        if parsed.path == "/api/v1/events/stream":
            self._proxy_sse()
            return
        if parsed.path.startswith("/api/"):
            self._proxy_json()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_json()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PATCH(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_json()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_json()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _send_text(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _daemon_target(self) -> str:
        return f"{self.daemon_url}{self.path[len('/api'):]}"

    def _proxy_json(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        req = Request(
            self._daemon_target(),
            data=body,
            method=self.command,
            headers={"Content-Type": self.headers.get("Content-Type", "application/json")},
        )
        try:
            with urlopen(req, timeout=180) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get_content_type() + "; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except URLError as exc:
            payload = json.dumps({"error": f"daemon unavailable: {exc.reason}"}).encode("utf-8")
            self.send_response(HTTPStatus.BAD_GATEWAY)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def _proxy_sse(self) -> None:
        req = Request(self._daemon_target(), headers={"Accept": "text/event-stream"})
        try:
            with urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                for chunk in resp:
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except Exception:
            return

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, daemon_url: str = DEFAULT_DAEMON_URL) -> None:
    class BoundHandler(CommandDeckHandler):
        pass

    BoundHandler.daemon_url = daemon_url.rstrip("/")
    with ThreadingHTTPServer((host, port), BoundHandler) as httpd:
        print(f"synkraken command deck listening on http://{host}:{port}")
        httpd.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SynKraken web command deck")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    serve(host=args.host, port=args.port, daemon_url=args.daemon_url)


if __name__ == "__main__":
    main()
