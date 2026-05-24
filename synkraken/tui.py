from __future__ import annotations

import curses
import json
import re
import shlex
import signal
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .branding import (
    BANNER_HEIGHT,
    KRAKEN_COL,
    KRAKEN_HEIGHT,
    KRAKEN_ROW_XTERM256,
    KRAKEN_WIDTH,
    LOGO_KRAKEN_FADE_INDEX,
    LOGO_ROW_XTERM256,
    LOGO_WORDMARK_FADE_INDEX,
    NAME,
    TAGLINE,
    WORDMARK_COL,
    _KRAKEN_ROWS,
    _WORDMARK_ROWS,
)
from .preferences import load_preferences, save_preferences

# Curses colour pairs:
#   30..36  → wordmark vertical fade (one per row + tagline)
#   40..47  → kraken sigil vertical fade (one per row)
_WORDMARK_PAIR_OFFSET = 30
_KRAKEN_PAIR_OFFSET   = 40


DEFAULT_BASE = 'http://127.0.0.1:9460'

# ── colour pair indices (semantic names) ───────────────────────────────────
C_RED        = 1
C_TEAL       = 2   # surface ocean
C_BLUE       = 3   # mid ocean
C_NAVY       = 4   # deep ocean
C_MUTED      = 5   # grey-blue chrome
C_BRIGHT     = 6   # bright aqua accent
C_OK         = 7
C_WARN       = 8
C_TYPING     = 9
C_GOOSE_D    = 10
C_GOOSE_L    = 11
C_HERMES_D   = 12
C_HERMES_L   = 13
C_OPENCLAW_D = 14
C_OPENCLAW_L = 15
C_OPERATOR_D = 16
C_OPERATOR_L = 17
C_ROOM       = 18
C_CLAUDE_D   = 19
C_CLAUDE_L   = 20
C_CRUSH_D    = 21
C_CRUSH_L    = 22

# ── box-drawing ────────────────────────────────────────────────────────────
BOX = dict(tl='╭', tr='╮', bl='╰', br='╯', h='─', v='│')

# ── commands & filters ─────────────────────────────────────────────────────
COMMANDS = [
    '/dashboard', '/events', '/conversations', '/deadletters', '/adapters',
    '/rooms', '/room', '/tasks', '/compose', '/send', '/broadcast', '/history',
    '/open', '/discuss', '/team', '/team-runs', '/team-run', '/approve', '/reject',
    '/goal', '/goals', '/goal-run', '/cancel-goal',
    '/runtimes', '/runtime', '/workspace', '/flight',
    '/decisions', '/decision', '/handoffs', '/handoff', '/replay', '/incident',
    '/filter', '/help', '/status', '/health', '/agents', '/tail', '/transcript',
    '/save-transcript',
    '/presence', '/agent', '/profiles', '/memory', '/clear', '/refresh', '/quit',
]
ROOM_SUBCOMMANDS = ['create', 'delete', 'enter', 'leave', 'add', 'remove', 'members', 'kick', 'list']
EVENT_FILTERS = {
    'all', 'message.accepted', 'delivery.recorded', 'dead-letter.recorded',
    'delivery.queued', 'delivery.sent', 'typing.started', 'typing.stopped',
    'stream-error',
}

# ── SIGINT (double-tap to quit) ────────────────────────────────────────────
_SIGINT_STATE = {'count': 0, 'last': 0.0}


def _install_sigint_handler():
    previous = signal.getsignal(signal.SIGINT)

    def _handler(signum, frame):
        now = time.time()
        if now - _SIGINT_STATE['last'] > 2.0:
            _SIGINT_STATE['count'] = 1
        else:
            _SIGINT_STATE['count'] += 1
        _SIGINT_STATE['last'] = now
        if _SIGINT_STATE['count'] >= 2:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handler)
    return previous


def _restore_sigint_handler(previous):
    signal.signal(signal.SIGINT, previous)


# ── HTTP helpers ───────────────────────────────────────────────────────────
def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        # Surface the daemon's error body — without this every 4xx/5xx looks
        # like a bare "HTTP Error 400" and you can't tell what went wrong.
        body = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(body).get('error', body)
        except Exception:
            detail = body or str(exc)
        raise RuntimeError(f'HTTP {exc.code}: {detail}') from None


def _put_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(body).get('error', body)
        except Exception:
            detail = body or str(exc)
        raise RuntimeError(f'HTTP {exc.code}: {detail}') from None


def _delete(url: str) -> dict:
    req = urllib.request.Request(url, method='DELETE')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


# ── SSE event stream ───────────────────────────────────────────────────────
class EventStreamWorker:
    def __init__(self, base: str, max_events: int = 200) -> None:
        self.base = base
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self.running = False
        self.thread: threading.Thread | None = None
        self.typing: dict[str, float] = {}
        self.typing_names: dict[str, str] = {}
        self.delivery_activity: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False

    def _prune_typing(self):
        now = time.time()
        for k in [k for k, v in self.typing.items() if now - v > 10]:
            self.typing.pop(k, None)
            self.typing_names.pop(k, None)

    def _prune_delivery_activity(self):
        now = time.time()
        for k, row in list(self.delivery_activity.items()):
            expires_at = row.get('expires_at')
            if expires_at is not None and now > float(expires_at):
                self.delivery_activity.pop(k, None)

    def get_typing_names(self) -> list[str]:
        with self._lock:
            self._prune_typing()
            return [self.typing_names[k] for k in self.typing.keys() if k in self.typing_names]

    def get_typing_ids(self) -> set[str]:
        with self._lock:
            self._prune_typing()
            return set(self.typing.keys())

    def get_delivery_activity(self, target: str | None = None,
                              conversation_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            self._prune_delivery_activity()
            rows = list(self.delivery_activity.values())
        if not target and not conversation_id:
            return rows
        filtered = []
        for row in rows:
            if conversation_id and row.get('conversation_id') == conversation_id:
                filtered.append(row)
                continue
            if target and (
                row.get('reply_context') == target
                or row.get('original_target') == target
                or row.get('delivery_target') == target
                or row.get('adapter_id') == target
            ):
                filtered.append(row)
        return filtered

    def _note_event(self, obj: dict[str, Any]) -> None:
        event = obj.get('event')
        data = obj.get('data', {}) or {}
        adapter_id = data.get('adapter_id')
        runtime_name = data.get('runtime_name') or adapter_id
        with self._lock:
            delivery_target = data.get('delivery_target') or adapter_id
            message_id = data.get('message_id')
            if event == 'discussion.turn':
                discussion_id = data.get('discussion_id') or data.get('conversation_id')
                turn = data.get('turn')
                key = f'discussion:{discussion_id}:{turn}'
                target = f"room:{data.get('room_name')}" if data.get('room_name') else 'discussion'
                self.delivery_activity[key] = {
                    'key': key,
                    'adapter_id': str(adapter_id or data.get('adapter_id') or ''),
                    'runtime_name': str(runtime_name or data.get('adapter_id') or ''),
                    'delivery_target': str(data.get('adapter_id') or ''),
                    'message_id': key,
                    'conversation_id': data.get('conversation_id'),
                    'original_target': target,
                    'reply_context': target,
                    'status': 'thinking',
                    'label': data.get('label'),
                    'updated_at': time.time(),
                    'expires_at': None,
                }
            elif event == 'discussion.completed':
                conversation_id = data.get('conversation_id')
                for row in self.delivery_activity.values():
                    if row.get('conversation_id') == conversation_id:
                        row['expires_at'] = time.time() + 2
            if message_id and delivery_target:
                key = f'{message_id}:{delivery_target}'
                if event in ('delivery.queued', 'delivery.sent', 'typing.started',
                             'delivery.recorded', 'dead-letter.recorded'):
                    status = str(data.get('status') or '')
                    if event == 'delivery.queued':
                        status = 'queued'
                    elif event == 'delivery.sent':
                        status = 'sent'
                    elif event == 'typing.started':
                        status = 'thinking'
                    elif event == 'dead-letter.recorded':
                        status = str(data.get('status') or 'failed')
                    elif event == 'delivery.recorded':
                        status = str(data.get('status') or ('replied' if data.get('ok') else 'failed'))
                    row = self.delivery_activity.get(key, {})
                    row.update({
                        'key': key,
                        'adapter_id': str(adapter_id or delivery_target),
                        'runtime_name': str(runtime_name or delivery_target),
                        'delivery_target': str(delivery_target),
                        'message_id': str(message_id),
                        'conversation_id': data.get('conversation_id') or row.get('conversation_id'),
                        'original_target': data.get('original_target') or row.get('original_target'),
                        'reply_context': data.get('reply_context') or row.get('reply_context'),
                        'status': status,
                        'attempts': data.get('attempts') or row.get('attempts'),
                        'error': data.get('error') or data.get('reason') or row.get('error'),
                        'body_preview': data.get('body_preview') or row.get('body_preview'),
                        'updated_at': time.time(),
                    })
                    if status == 'replied':
                        row['expires_at'] = time.time() + 1.5
                    elif status in ('failed', 'timeout'):
                        row['expires_at'] = time.time() + 300
                    else:
                        row['expires_at'] = None
                    self.delivery_activity[key] = row
            if event == 'typing.started' and adapter_id:
                self.typing[adapter_id] = time.time()
                self.typing_names[adapter_id] = str(runtime_name)
            elif event == 'typing.stopped' and adapter_id:
                self.typing.pop(adapter_id, None)
                self.typing_names.pop(adapter_id, None)

    def _run(self) -> None:
        url = f'{self.base}/v1/events/stream'
        while self.running:
            try:
                req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    for raw in resp:
                        if not self.running:
                            break
                        line = raw.decode('utf-8', errors='replace').strip()
                        if line.startswith('data: '):
                            payload = line[6:]
                            try:
                                obj = json.loads(payload)
                                self._note_event(obj)
                                self.events.appendleft(obj)
                            except Exception:
                                self.events.appendleft({'event': 'raw', 'data': {'preview': payload[:180]}})
            except Exception as exc:  # noqa: BLE001
                self.events.appendleft({'event': 'stream-error', 'data': {'error': str(exc)}})
                time.sleep(2)


# ── dashboard fetch ────────────────────────────────────────────────────────
def _fetch_dashboard(base: str) -> dict:
    out = {
        'health': _get_json(f'{base}/health'),
        'agents': _get_json(f'{base}/v1/agents'),
        'recent': _get_json(f'{base}/v1/conversations?limit=10'),
        'deliveries': _get_json(f'{base}/v1/deliveries?limit=10'),
        'dead_letters': _get_json(f'{base}/v1/dead-letters?limit=10'),
    }
    try:
        out['rooms'] = _get_json(f'{base}/v1/rooms')
    except Exception:
        out['rooms'] = {'rooms': []}
    try:
        out['tasks'] = _get_json(f'{base}/v1/tasks')
    except Exception:
        out['tasks'] = {'tasks': []}
    try:
        out['flight'] = _get_json(f'{base}/v1/flight')
    except Exception:
        out['flight'] = {}
    return out


# ── helpers ────────────────────────────────────────────────────────────────
def _health_marker(ok: bool) -> str:
    return '●' if ok else '○'


_AGENT_COLOR_PAIRS = {
    'goose':    (C_GOOSE_D, C_GOOSE_L),
    'hermes':   (C_HERMES_D, C_HERMES_L),
    'openclaw': (C_OPENCLAW_D, C_OPENCLAW_L),
    'claude':   (C_CLAUDE_D, C_CLAUDE_L),
    'crush':    (C_CRUSH_D, C_CRUSH_L),
}


def _agent_color(adapter_id: str) -> tuple[int, int]:
    aid = (adapter_id or '').lower()
    if aid in ('operator', 'synkraken-tui', ''):
        return C_OPERATOR_D, C_OPERATOR_L
    norm = aid.replace('-main', '').replace('-', '')
    for key, (d, l) in _AGENT_COLOR_PAIRS.items():
        if key in norm:
            return d, l
    return C_BLUE, C_TEAL


def _runtime_label(agent: dict) -> str:
    return agent.get('runtime_name', agent.get('adapter_id', 'unknown'))


def _presence_marker(status: str) -> str:
    return {
        'working': '◐',
        'idle': '○',
        'online': '●',
        'blocked': '✗',
        'offline': '○',
        'disabled': '○',
        'configured': '○',
    }.get(status or 'configured', '○')


def _agent_presence_line(agent: dict) -> str:
    status = str(agent.get('status') or ('online' if agent.get('enabled') else 'disabled'))
    last_seen = _time_ago(agent.get('last_seen_at')) if agent.get('last_seen_at') else 'never'
    return f"{agent.get('adapter_id', ''):<14} {_presence_marker(status)} {status:<10} {last_seen:>5}"


def _agent_ids(data: dict) -> list[str]:
    return [a.get('adapter_id', '') for a in data.get('agents', {}).get('agents', [])]


def _mention_alias_map(data: dict) -> dict[str, str]:
    aliases: dict[str, str] = {'everyone': 'broadcast', 'all': 'broadcast'}
    for agent in data.get('agents', {}).get('agents', []):
        aid = str(agent.get('adapter_id', '')).strip()
        rn = str(agent.get('runtime_name', aid)).strip()
        if aid:
            aliases[aid.lower()] = aid
        if rn:
            aliases[rn.lower()] = aid
        if aid == 'openclaw-main':
            aliases.setdefault('openclaw', aid)
            aliases.setdefault('main', aid)
    return aliases


def _resolve_target(target: str) -> str:
    lowered = target.strip().lower()
    aliases = {
        'openclaw': 'openclaw-main', 'main': 'openclaw-main',
        'hermes': 'hermes', 'goose': 'goose', 'broadcast': 'broadcast',
    }
    return aliases.get(lowered, target)


def _time_ago(iso_str: str | None) -> str:
    if not iso_str:
        return ''
    try:
        when = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        delta = datetime.now(timezone.utc) - when
        sec = int(delta.total_seconds())
        if sec < 0:
            return 'now'
        if sec < 60:
            return f'{sec}s'
        if sec < 3600:
            return f'{sec // 60}m'
        if sec < 86400:
            return f'{sec // 3600}h'
        return f'{sec // 86400}d'
    except Exception:
        return ''


def _hhmmss(iso_str: str | None) -> str:
    if not iso_str:
        return ''
    return iso_str[11:19]


def _wrap(text: str, width: int) -> list[str]:
    if width <= 0:
        return [text]
    text = text.replace('\r', '')
    out: list[str] = []
    for paragraph in text.split('\n'):
        if not paragraph.strip():
            out.append('')
            continue
        cur = ''
        for word in paragraph.split():
            if not cur:
                cur = word
            elif len(cur) + 1 + len(word) <= width:
                cur += ' ' + word
            else:
                out.append(cur)
                cur = word
        if cur:
            out.append(cur)
    return out or ['']


# ── safe primitives ────────────────────────────────────────────────────────
def _safe_addstr(stdscr, y: int, x: int, text: str, width: int,
                 color: int | None = None, attr: int = 0) -> None:
    if width <= 0:
        return
    try:
        a = (curses.color_pair(color) if color is not None else 0) | attr
        stdscr.addnstr(y, x, text, width, a)
    except curses.error:
        pass


# ── panel chrome ───────────────────────────────────────────────────────────
def _draw_panel(stdscr, y: int, x: int, w: int, h: int,
                title: str | None = None, color: int = C_MUTED) -> None:
    if w < 4 or h < 2:
        return
    if title:
        title_segment = f"{BOX['h']} {title} "
        fill = BOX['h'] * max(0, w - 2 - len(title_segment))
        head = BOX['tl'] + title_segment + fill + BOX['tr']
    else:
        head = BOX['tl'] + BOX['h'] * (w - 2) + BOX['tr']
    foot = BOX['bl'] + BOX['h'] * (w - 2) + BOX['br']
    _safe_addstr(stdscr, y, x, head, w, color)
    _safe_addstr(stdscr, y + h - 1, x, foot, w, color)
    for yy in range(y + 1, y + h - 1):
        _safe_addstr(stdscr, yy, x,         BOX['v'], 1, color)
        _safe_addstr(stdscr, yy, x + w - 1, BOX['v'], 1, color)


def _panel_lines(stdscr, y: int, x: int, w: int, h: int,
                 lines: list[tuple], inner_pad: int = 2) -> None:
    inner_x = x + inner_pad
    inner_w = w - 2 * inner_pad
    inner_y = y + 1
    inner_h = h - 2
    for i, item in enumerate(lines):
        if i >= inner_h:
            break
        if isinstance(item, tuple):
            if len(item) == 2:
                text, color = item
                attr = 0
            else:
                text, color, attr = item
        else:
            text, color, attr = item, None, 0
        _safe_addstr(stdscr, inner_y + i, inner_x, text, inner_w, color, attr)


# ── header (kraken sigil + SYNKRAKEN wordmark) ────────────────────────────
def _draw_header(stdscr, w: int) -> int:
    """Render the kraken sigil + SYNKRAKEN wordmark with per-row colour fades.

    Kraken and wordmark are positioned side-by-side and each row gets its
    own colour pair drawn separately so they can fade independently — using
    a single addstr per row with embedded ANSI escapes would just print the
    escapes literally (curses doesn't interpret them).
    """
    max_y = stdscr.getmaxyx()[0]
    for i in range(BANNER_HEIGHT):
        if i >= max_y:
            break

        # Kraken sigil
        k_idx = LOGO_KRAKEN_FADE_INDEX[i]
        if k_idx >= 0:
            k_text = _KRAKEN_ROWS[k_idx]
            k_attr = curses.color_pair(_KRAKEN_PAIR_OFFSET + k_idx)
            if k_idx <= 1:
                k_attr |= curses.A_BOLD       # head crown gets the glow
            elif k_idx >= 6:
                k_attr |= curses.A_DIM        # tentacle tips fade to abyss
            _safe_addstr(stdscr, i, KRAKEN_COL, k_text,
                         min(KRAKEN_WIDTH, max(0, w - KRAKEN_COL)), None, k_attr)

        # Wordmark (rows 0-5) or tagline (row 6) — but no wordmark on row 7
        m_idx = LOGO_WORDMARK_FADE_INDEX[i]
        if m_idx >= 0:
            if m_idx < 6:
                m_text = _WORDMARK_ROWS[m_idx]
            else:
                m_text = TAGLINE
            m_attr = curses.color_pair(_WORDMARK_PAIR_OFFSET + m_idx)
            if m_idx == 0 or m_idx == 6:
                m_attr |= curses.A_BOLD
            elif m_idx >= 4:
                m_attr |= curses.A_DIM
            _safe_addstr(stdscr, i, WORDMARK_COL, m_text,
                         max(0, w - WORDMARK_COL - 1), None, m_attr)

    return BANNER_HEIGHT


# ── dashboard view ─────────────────────────────────────────────────────────
def _view_dashboard(stdscr, data, state, typing_ids, top, h, w):
    avail_h = h - top - 4  # leave room for hint, status bar, prompt
    # Three rows: 40% top (bridge | targets), 28% middle (latest replies),
    # 32% bottom (recent conversations).
    top_h = max(8, (avail_h * 40) // 100)
    mid_h = max(5, (avail_h * 28) // 100)
    bot_h = max(5, avail_h - top_h - mid_h)
    col_w = w // 2
    left_w = col_w
    right_w = w - col_w

    # ── top-left: BRIDGE STATUS ────────────────────────────────────────
    health = data.get('health', {})
    ok = bool(health.get('ok'))
    title_color = C_OK if ok else C_RED
    _draw_panel(stdscr, top, 0, left_w, top_h, title=f"BRIDGE {_health_marker(ok)}", color=title_color)

    lines: list[tuple] = []
    if ok:
        lines.append(('● healthy', C_OK, curses.A_BOLD))
    else:
        lines.append(('○ offline — check daemon', C_RED, curses.A_BOLD))
    started = health.get('started_at') or ''
    if started:
        lines.append((f'  started {_time_ago(started)} ago', C_MUTED, curses.A_DIM))
    lines.append(('', None, 0))
    lines.append(('agents', C_MUTED, curses.A_BOLD))
    for a in data.get('agents', {}).get('agents', []):
        aid = a.get('adapter_id', '')
        status = str(a.get('status') or ('online' if a.get('enabled') else 'disabled'))
        d, _ = _agent_color(aid)
        typing_now = aid in typing_ids
        marker = '◐' if typing_now else _presence_marker(status)
        suffix = '  typing…' if typing_now else ''
        ago = _time_ago(a.get('last_seen_at')) if a.get('last_seen_at') else 'never'
        line = f"  {aid:<12} {marker} {status:<9} {ago:>5}{suffix}"
        attr = curses.A_BOLD if typing_now else 0
        lines.append((line, d, attr))
    _panel_lines(stdscr, top, 0, left_w, top_h, lines)

    # ── top-right: CHAT TARGETS (dynamic) ───────────────────────────────
    _draw_panel(stdscr, top, left_w, right_w, top_h, title='CHAT TARGETS')
    target_lines: list[tuple] = [
        ('type @name (or @everyone) to chat', C_MUTED, curses.A_DIM),
        ('', None, 0),
    ]
    for a in data.get('agents', {}).get('agents', []):
        aid = a.get('adapter_id', '')
        rn = _runtime_label(a)
        d, _ = _agent_color(aid)
        mention = f"@{rn.lower()}"
        target_lines.append((f"  {mention:<14}→  {rn}", d, 0))
    target_lines.append((f"  {'@everyone':<14}→  broadcast", C_BRIGHT, curses.A_BOLD))
    flight = data.get('flight') or {}
    if flight:
        target_lines.append(('', None, 0))
        target_lines.append(('flight', C_MUTED, curses.A_BOLD))
        target_lines.append((f"  agents online   {flight.get('agents_online', 0)}/{flight.get('agents_total', 0)}", C_BRIGHT, 0))
        target_lines.append((f"  active goals    {flight.get('active_goals', 0)}", C_BRIGHT, 0))
        target_lines.append((f"  blocked goals   {flight.get('blocked_goals', 0)}", C_RED if flight.get('blocked_goals') else C_MUTED, 0))
        target_lines.append((f"  token risk      {flight.get('token_risk', 'low')}", C_WARN if flight.get('token_risk') != 'low' else C_OK, 0))
        target_lines.append((f"  dead letters    {flight.get('dead_letters', 0)}", C_RED if flight.get('dead_letters') else C_MUTED, 0))
        target_lines.append((f"  pending reviews {flight.get('pending_reviews', 0)}", C_WARN if flight.get('pending_reviews') else C_MUTED, 0))
    rooms = data.get('rooms', {}).get('rooms', [])
    if rooms:
        target_lines.append(('', None, 0))
        target_lines.append(('rooms', C_MUTED, curses.A_BOLD))
        for r in rooms[:5]:
            name = r.get('name', '')
            mc = r.get('member_count', 0)
            target_lines.append((f"  #{name:<13}→  {mc} member{'s' if mc != 1 else ''}", C_ROOM, 0))
    _panel_lines(stdscr, top, left_w, right_w, top_h, target_lines)

    # ── middle: LATEST REPLIES (full width) ─────────────────────────────
    mid_y = top + top_h
    _draw_panel(stdscr, mid_y, 0, w, mid_h, title='LATEST REPLIES  ·  inbox', color=C_BRIGHT)
    reply_lines: list[tuple] = []
    inner_w = w - 4
    deliveries = data.get('deliveries', {}).get('deliveries', [])
    if not deliveries:
        reply_lines.append(('(no replies yet — send something with @<agent> or #<room>)',
                            C_MUTED, curses.A_DIM))
    else:
        for d in deliveries[:max(0, mid_h - 2)]:
            aid = d.get('adapter_id', '')
            ok = bool(d.get('ok'))
            preview = (d.get('body_preview', '') or '').replace('\n', ' ').strip()
            ago = _time_ago(d.get('created_at'))
            d_color, l_color = _agent_color(aid)
            marker = '✓' if ok else '✗'
            head = f"  {marker} {aid:>12}  "
            tail = f"  {ago:>4} ago"
            avail = max(10, inner_w - len(head) - len(tail))
            if len(preview) > avail:
                preview = preview[:avail - 1] + '…'
            reply_lines.append((head + preview.ljust(avail) + tail,
                                d_color if ok else C_RED, 0))
    _panel_lines(stdscr, mid_y, 0, w, mid_h, reply_lines)

    # ── bottom: RECENT CONVERSATIONS (full width) ───────────────────────
    bot_y = mid_y + mid_h
    _draw_panel(stdscr, bot_y, 0, w, bot_h, title='RECENT CONVERSATIONS')
    conv_lines: list[tuple] = []
    conversations = data.get('recent', {}).get('conversations', [])
    if not conversations:
        conv_lines.append(('(no conversations yet — say something like @goose hello)', C_MUTED, curses.A_DIM))
    else:
        for idx, c in enumerate(conversations[:max(0, bot_h - 3)], start=1):
            src = c.get('sample_source', '') or ''
            tgt = c.get('sample_target', '') or ''
            preview = (c.get('preview', '') or '').replace('\n', ' ').strip()
            ago = _time_ago(c.get('last_timestamp'))
            src_d, _ = _agent_color(src)
            head = f"  {idx:>2}.  {src:>10} → {tgt:<16}  "
            tail = f"  {ago:>4} ago"
            avail = max(10, inner_w - len(head) - len(tail))
            if len(preview) > avail:
                preview = preview[:avail - 1] + '…'
            conv_lines.append((head + preview.ljust(avail) + tail, src_d, 0))
        conv_lines.append(('', None, 0))
        conv_lines.append(('  /open <n> to view in chat view  •  /rooms to manage chat rooms',
                           C_MUTED, curses.A_DIM))
    _panel_lines(stdscr, bot_y, 0, w, bot_h, conv_lines)


# ── events view ────────────────────────────────────────────────────────────
def _format_event(event: dict[str, Any]) -> tuple[str, int]:
    etype = event.get('event', 'event')
    d = event.get('data', {}) or {}
    ts = _hhmmss(event.get('timestamp', ''))
    if etype == 'message.accepted':
        src = d.get('source', '')
        src_d, _ = _agent_color(src)
        cid = (d.get('conversation_id', '') or '')[:12]
        return (f"  {ts}  → {src} → {d.get('target')}  [{cid}]", src_d)
    if etype == 'delivery.recorded':
        aid = d.get('adapter_id', '')
        ok = bool(d.get('ok'))
        marker = '✓' if ok else '✗'
        preview = (d.get('body_preview', '') or '').replace('\n', ' ')[:80]
        c, _ = _agent_color(aid)
        return (f"  {ts}  {marker} {aid:<14} {preview}", c if ok else C_RED)
    if etype == 'dead-letter.recorded':
        return (f"  {ts}  ✗ {d.get('adapter_id')} — {d.get('reason', '')[:60]}", C_RED)
    if etype == 'typing.started':
        aid = d.get('adapter_id', '')
        _, l = _agent_color(aid)
        return (f"  {ts}  … {d.get('runtime_name', aid)} typing", l)
    if etype == 'typing.stopped':
        aid = d.get('adapter_id', '')
        return (f"  {ts}  · {d.get('runtime_name', aid)} idle", C_MUTED)
    if etype == 'stream-error':
        return (f"  {ts}  ! stream error: {d.get('error', '')[:60]}", C_RED)
    preview = json.dumps(d, ensure_ascii=False)[:80]
    return (f"  {ts}  {etype:<24} {preview}", C_MUTED)


def _view_events(stdscr, events, state, top, h, w):
    avail_h = h - top - 4
    title = f"LIVE EVENTS   filter: {state['event_filter']}"
    _draw_panel(stdscr, top, 0, w, avail_h, title=title)
    filtered = events if state['event_filter'] == 'all' \
        else [e for e in events if e.get('event') == state['event_filter']]
    if not filtered:
        _panel_lines(stdscr, top, 0, w, avail_h,
                     [('(waiting for events…)', C_MUTED, curses.A_DIM)])
        return
    lines = [(line, color, 0) for line, color in
             (_format_event(e) for e in filtered[:avail_h - 2])]
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


# ── conversations list view ───────────────────────────────────────────────
def _view_conversations(stdscr, data, top, h, w):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title='CONVERSATIONS')
    lines: list[tuple] = []
    conversations = data.get('recent', {}).get('conversations', [])
    if not conversations:
        lines.append(('(none yet)', C_MUTED, curses.A_DIM))
    else:
        max_rows = (avail_h - 2) // 3
        for idx, c in enumerate(conversations[:max_rows], start=1):
            src = c.get('sample_source', '') or ''
            tgt = c.get('sample_target', '') or ''
            preview = (c.get('preview', '') or '').replace('\n', ' ').strip()[:120]
            ago = _time_ago(c.get('last_timestamp'))
            cid = c.get('conversation_id', '') or ''
            src_d, _ = _agent_color(src)
            lines.append((f"  {idx:>2}. {src} → {tgt}    {ago:>4} ago    [{cid[:12]}]", src_d, curses.A_BOLD))
            lines.append((f"       {preview}", None, curses.A_DIM))
            lines.append(('', None, 0))
        lines.append((f'  /open <n>  open conversation n as chat', C_MUTED, curses.A_DIM))
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


# ── chat bubble rendering ─────────────────────────────────────────────────
def _chat_bubble(speaker: str, body: str, ts: str,
                 header_color: int, body_color: int,
                 *, align: str, max_w: int) -> list[tuple]:
    body = (body or '').strip()
    if not body:
        body = '(empty)'
    # Choose a target body width: roughly 60% of available, minimum 24.
    target_w = max(24, min(int(max_w * 0.65), max_w - 4))
    wrapped = _wrap(body, target_w)
    bw = max(max(len(w) for w in wrapped), len(speaker) + 6, len(ts) + 4) + 4
    bw = min(bw, max_w)
    inner = bw - 2  # space inside the side borders

    out: list[tuple] = []
    pad = (max_w - bw) if align == 'right' else 0
    indent = ' ' * pad
    header_inner = f' {speaker} '
    ts_inner = f' {ts} ' if ts else ''
    middle = BOX['h'] * max(0, inner - len(header_inner) - len(ts_inner))
    head = BOX['tl'] + header_inner + middle + ts_inner + BOX['tr']
    foot = BOX['bl'] + BOX['h'] * inner + BOX['br']
    out.append((indent + head, header_color, curses.A_BOLD))
    for line in wrapped:
        if align == 'right':
            content = line.rjust(inner - 2)
        else:
            content = line.ljust(inner - 2)
        out.append((indent + BOX['v'] + ' ' + content + ' ' + BOX['v'], body_color, 0))
    out.append((indent + foot, header_color, 0))
    return out


def _activity_row(row: dict[str, Any], *, max_w: int) -> tuple:
    aid = row.get('runtime_name') or row.get('adapter_id') or row.get('delivery_target') or 'agent'
    status = str(row.get('status') or 'thinking')
    phrases = {
        'queued': 'thinking…',
        'sent': 'thinking…',
        'thinking': 'thinking…',
        'replied': 'replied',
        'failed': 'failed',
        'timeout': 'timeout',
    }
    phrase = phrases.get(status, 'working…')
    extra = ''
    if status in ('failed', 'timeout') and row.get('error'):
        extra = f"  {str(row.get('error'))[:80]}"
    line = f"  {row.get('label') or f'{aid} {phrase}'}"
    line += f"  [{status}]"
    line += extra
    color = C_RED if status in ('failed', 'timeout') else C_TYPING
    return (line[:max_w], color, curses.A_DIM if status not in ('failed', 'timeout') else curses.A_BOLD)


def _chat_lines(result: dict, w: int) -> list[tuple]:
    """Build the full rendered chat transcript. Source = left, replies = right."""
    msgs = result.get('messages', [])
    deliveries = result.get('deliveries', [])
    activity_rows = result.get('activity', [])
    dels_by_mid: dict[str, list[dict]] = {}
    for d in deliveries:
        dels_by_mid.setdefault(d.get('message_id'), []).append(d)
    activity_by_mid: dict[str, list[dict]] = {}
    for row in activity_rows:
        activity_by_mid.setdefault(row.get('message_id'), []).append(row)

    inner_w = w - 6
    lines: list[tuple] = []
    if not msgs and not activity_rows:
        lines.append(('(no messages yet)', C_MUTED, curses.A_DIM))
    else:
        for m in msgs:
            src = m.get('source', '') or ''
            body = m.get('body', '') or ''
            ts = _hhmmss(m.get('timestamp', ''))
            d_color, l_color = _agent_color(src)
            align = 'right' if src in ('operator', 'synkraken-tui') else 'left'
            lines.extend(_chat_bubble(src or 'operator', body, ts,
                                       d_color, l_color,
                                       align=align, max_w=inner_w))
            # Per-message deliveries (only show when this view came from
            # /history of a non-room conversation — replies in rooms are
            # already saved as separate messages by the fabric).
            for d in dels_by_mid.get(m.get('message_id'), []):
                aid = d.get('adapter_id', '')
                rep = (d.get('body') or '').strip()
                if not rep:
                    continue
                d_c, l_c = _agent_color(aid)
                rts = _hhmmss(d.get('created_at'))
                lines.extend(_chat_bubble(aid, rep, rts, d_c, l_c,
                                           align='right' if align == 'left' else 'left',
                                           max_w=inner_w))
            for row in activity_by_mid.pop(m.get('message_id'), []):
                lines.append(_activity_row(row, max_w=inner_w))
            lines.append(('', None, 0))

        for rows in activity_by_mid.values():
            for row in rows:
                lines.append(_activity_row(row, max_w=inner_w))
    return lines


def _line_text(item: tuple | str) -> str:
    if isinstance(item, tuple):
        return str(item[0])
    return str(item)


def _visible_transcript_slice(lines: list[tuple], viewport_h: int, scroll_offset: int) -> tuple[list[tuple], int, int]:
    visible_h = max(1, viewport_h)
    max_offset = max(0, len(lines) - visible_h)
    offset = min(max(0, scroll_offset), max_offset)
    start = max(0, len(lines) - visible_h - offset)
    end = min(len(lines), start + visible_h)
    return lines[start:end], start, offset


def _transcript_key(state: dict) -> str:
    if state.get('chat_target'):
        return str(state['chat_target'])
    if state.get('current_room'):
        return f"room:{state['current_room']}"
    result = state.get('command_result')
    if result:
        data = result[1] if isinstance(result, tuple) and len(result) > 1 else {}
        cid = data.get('conversation_id') if isinstance(data, dict) else None
        if cid:
            return str(cid)
    return 'chat'


def _transcript_state(state: dict) -> dict:
    transcripts = state.setdefault('transcripts', {})
    key = _transcript_key(state)
    return transcripts.setdefault(key, {'scroll_offset': 0, 'search': None, 'line_count': 0})


def _reset_transcript_view(state: dict) -> None:
    _transcript_state(state)['scroll_offset'] = 0


def _scroll_transcript(state: dict, amount: int, total_lines: int, viewport_h: int) -> None:
    ts = _transcript_state(state)
    max_offset = max(0, total_lines - max(1, viewport_h))
    ts['scroll_offset'] = min(max(0, int(ts.get('scroll_offset') or 0) + amount), max_offset)


def _jump_transcript(state: dict, live: bool, total_lines: int, viewport_h: int) -> None:
    ts = _transcript_state(state)
    ts['scroll_offset'] = 0 if live else max(0, total_lines - max(1, viewport_h))


def _sync_transcript_line_count(ts: dict, line_count: int) -> None:
    previous_count = int(ts.get('line_count') or 0)
    current_offset = int(ts.get('scroll_offset') or 0)
    if current_offset and line_count > previous_count:
        ts['scroll_offset'] = current_offset + (line_count - previous_count)
    ts['line_count'] = line_count


def _search_transcript(state: dict, lines: list[tuple], term: str, *, backwards: bool = False) -> bool:
    needle = term.strip().lower()
    if not needle:
        return False
    haystack = [_line_text(line).lower() for line in lines]
    matches = [idx for idx, line in enumerate(haystack) if needle in line]
    if not matches:
        _transcript_state(state)['search'] = {'term': term, 'matches': [], 'index': -1}
        return False
    search = _transcript_state(state).get('search') or {}
    current_index = int(search.get('index', -1)) if search.get('term') == term else -1
    if backwards:
        next_index = current_index - 1 if current_index > 0 else len(matches) - 1
    else:
        next_index = current_index + 1 if current_index + 1 < len(matches) else 0
    _transcript_state(state)['search'] = {'term': term, 'matches': matches, 'index': next_index}
    viewport_h = max(1, int(state.get('last_chat_viewport_h') or 1))
    target = matches[next_index]
    bottom_start = max(0, len(lines) - viewport_h)
    start = min(target, bottom_start)
    _transcript_state(state)['scroll_offset'] = max(0, bottom_start - start)
    return True


def _repeat_search_transcript(state: dict, lines: list[tuple], *, backwards: bool = False) -> bool:
    search = _transcript_state(state).get('search') or {}
    term = search.get('term')
    if not term:
        return False
    return _search_transcript(state, lines, str(term), backwards=backwards)


def _format_transcript_messages(label: str, result: dict) -> str:
    lines = [f"Transcript: {label}", ""]
    for msg in result.get('messages', []):
        ts = msg.get('timestamp') or ''
        source = msg.get('source') or 'unknown'
        target = msg.get('target') or ''
        body = str(msg.get('body') or '').rstrip()
        header = f"[{ts}] {source} -> {target}".rstrip()
        lines.append(header)
        lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _safe_export_name(label: str) -> str:
    value = label.strip().lower().lstrip('#') or 'transcript'
    value = re.sub(r'[^a-z0-9._-]+', '-', value).strip('-')
    if not value.startswith('room-') and not value.startswith('run-') and value != 'transcript':
        value = f'room-{value}'
    return value or 'transcript'


def _save_current_transcript(state: dict) -> Path:
    if state.get('view') != 'chat' or not state.get('command_result'):
        raise RuntimeError('open a room or conversation transcript first')
    label, result = state['command_result']
    export_dir = Path('exports')
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d')
    path = export_dir / f"{_safe_export_name(str(label))}-{stamp}.txt"
    path.write_text(_format_transcript_messages(str(label), result), encoding='utf-8')
    return path


def _transcript_mode_lines(state: dict, base: str) -> list[str]:
    lines = [
        'transcript mode',
        '',
        'navigation',
        '  Up/Down, PgUp/PgDn, Home/End',
        '  /tail                 jump live',
        '  /search-term          search current transcript',
        '  n / N                 next / previous match',
        '',
        'current transcript',
    ]
    if state.get('current_room'):
        lines.append(f"  room history          /open #{state['current_room']}")
    if state.get('chat_target'):
        lines.append(f"  target                {state['chat_target']}")
    if state.get('last_team_run_id'):
        run_id = state['last_team_run_id']
        lines.extend([
            '',
            'last team run',
            f"  view                  /team-run {run_id}",
            f"  export                /save-transcript",
            f"  review                /team-run {run_id}",
        ])
    try:
        suffix = f"?room={state['current_room']}&limit=5" if state.get('current_room') else "?limit=5"
        runs = _get_json(f'{base}/v1/team-runs{suffix}').get('team_runs', [])
    except Exception:
        runs = []
    if runs:
        lines.extend(['', 'team runs'])
        for run in runs:
            lines.append(
                f"  {run.get('team_run_id')}  {run.get('status')}  "
                f"owner={run.get('owner_agent') or '(none)'}  room=#{run.get('room_name')}"
            )
    lines.extend(['', 'filters', f"  event filter          {state.get('event_filter', 'all')}"])
    return lines


def _view_chat(stdscr, result, state, top, h, w, *, label: str = 'CONVERSATION'):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title=f'CHAT  •  {label}')
    lines = _chat_lines(result, w)
    viewport_h = max(1, avail_h - 2)
    state['last_chat_total_lines'] = len(lines)
    state['last_chat_viewport_h'] = viewport_h
    ts = _transcript_state(state)
    _sync_transcript_line_count(ts, len(lines))
    visible, start, offset = _visible_transcript_slice(lines, viewport_h, int(ts.get('scroll_offset') or 0))

    if offset:
        indicator = [
            (f"[Viewing history: {start} lines above]", C_WARN, curses.A_BOLD),
            ("Press End to return live", C_MUTED, curses.A_DIM),
        ]
        visible = indicator + visible[:max(0, viewport_h - len(indicator))]
    _panel_lines(stdscr, top, 0, w, avail_h, visible)


# ── deadletters view ──────────────────────────────────────────────────────
def _view_deadletters(stdscr, data, top, h, w):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title='DEAD LETTERS', color=C_RED)
    items = data.get('dead_letters', {}).get('dead_letters', [])
    if not items:
        _panel_lines(stdscr, top, 0, w, avail_h, [('(none — all deliveries acknowledged)', C_OK, 0)])
        return
    lines: list[tuple] = []
    for it in items[:avail_h - 2]:
        aid = it.get('adapter_id', '')
        reason = (it.get('reason') or '')[:100]
        ago = _time_ago(it.get('created_at'))
        lines.append((f"  ✗ {aid:<14} {reason:<60}  {ago:>4} ago", C_RED, 0))
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


# ── adapters view ─────────────────────────────────────────────────────────
def _view_adapters(stdscr, data, top, h, w):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title='ADAPTERS')
    lines: list[tuple] = []
    for a in data.get('agents', {}).get('agents', []):
        aid = a.get('adapter_id', '')
        rn = _runtime_label(a)
        status = str(a.get('status') or ('online' if a.get('enabled') else 'disabled'))
        atype = a.get('type', '')
        d, _ = _agent_color(aid)
        marker = _presence_marker(status)
        ago = _time_ago(a.get('last_seen_at')) if a.get('last_seen_at') else 'never'
        lines.append((f"  {rn:<14}  {marker} {status:<10} {ago:>5}  [{aid}] type={atype:<10}",
                      d, curses.A_BOLD if status in ('online', 'idle', 'working') else 0))
    if not lines:
        lines = [('(no adapters configured)', C_MUTED, curses.A_DIM)]
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


# ── rooms list view ───────────────────────────────────────────────────────
def _view_rooms(stdscr, data, state, top, h, w):
    avail_h = h - top - 4
    current = state.get('current_room')
    title = 'ROOMS' + (f'   ●  in {current}' if current else '')
    _draw_panel(stdscr, top, 0, w, avail_h, title=title, color=C_ROOM)
    rooms = data.get('rooms', {}).get('rooms', [])
    lines: list[tuple] = []
    if not rooms:
        lines.append(('no rooms yet', C_MUTED, curses.A_DIM)
        )
        lines.append(('', None, 0))
        lines.append(('create one:', C_TEAL, curses.A_BOLD))
        lines.append(('  /room create general goose hermes openclaw-main', None, 0))
        lines.append(('', None, 0))
        lines.append(('then enter to chat:', C_TEAL, curses.A_BOLD))
        lines.append(('  /room enter general', None, 0))
        lines.append(('  hi all, what are you working on?', None, curses.A_DIM))
        lines.append(('  /room leave', None, curses.A_DIM))
    else:
        for idx, r in enumerate(rooms[:avail_h - 2], start=1):
            name = r.get('name', '')
            mc = r.get('member_count', 0)
            desc = r.get('description', '') or ''
            last = r.get('last_activity') or r.get('created_at')
            ago = _time_ago(last)
            here = '  ← here' if current == name else ''
            attr = curses.A_BOLD if current == name else 0
            lines.append((f"  {idx:>2}. #{name:<14}  {mc} members  {ago:>4} ago{here}", C_ROOM, attr))
            if desc:
                lines.append((f"      {desc[:90]}", None, curses.A_DIM))
        lines.append(('', None, 0))
        lines.append(('  /room enter <name>   enter a room', C_MUTED, curses.A_DIM))
        lines.append(('  /open #<name>         view room transcript', C_MUTED, curses.A_DIM))
        lines.append(('  /room leave           exit the current room', C_MUTED, curses.A_DIM))
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


# ── help view ─────────────────────────────────────────────────────────────
def _view_help(stdscr, top, h, w):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title='HELP')
    HELP = [
        (f'{NAME} — {TAGLINE}', C_BRIGHT, curses.A_BOLD),
        ('', None, 0),
        ('CHAT', C_TEAL, curses.A_BOLD),
        ('  @goose hello                    direct message goose', None, 0),
        ('  @hermes @openclaw please confer send to multiple agents', None, 0),
        ('  @everyone status?               current room if entered; otherwise global', None, 0),
        ('  @everyone --global status?      explicit global broadcast', None, 0),
        ('  #room hi all                    send to a specific room', None, 0),
        ('  (in a room) plain text          messages go to the current room', None, 0),
        ('  /discuss goose hermes "topic"   bounded agent discussion', None, 0),
        ('  /discuss --turns 4 --room ops goose hermes "topic"', None, 0),
        ('  /team "task"                    room team task mode', None, 0),
        ('  /team --turns 4 "task"          bounded room team task mode', None, 0),
        ('  /goal "goal"                    bounded room goal mode', None, 0),
        ('  /goal --threshold 80 --rounds 3 "goal"', None, 0),
        ('  /goals                          recent goal runs', None, 0),
        ('  /goal-run <id>                  inspect one goal run', None, 0),
        ('  /cancel-goal <id>               cancel a running goal', None, 0),
        ('  /decisions                      recent decision records', None, 0),
        ('  /decision latest                inspect latest decision', None, 0),
        ('  /decision <id>                  inspect one decision', None, 0),
        ('  /team-runs                      recent team runs', None, 0),
        ('  /team-run <id>                  inspect one team run', None, 0),
        ('  /approve <id>                   approve a decision or pending team run', None, 0),
        ('  /reject <id>                    reject a decision or pending team run', None, 0),
        ('  /save-transcript                export current room/chat transcript', None, 0),
        ('  /tail                           jump current transcript back to live', None, 0),
        ('  /transcript                     transcript mode: runs, history, filters', None, 0),
        ('', None, 0),
        ('ROOMS', C_TEAL, curses.A_BOLD),
        ('  /rooms                          list rooms', None, 0),
        ('  /room create <name> [members…] create a room (members = adapter ids)', None, 0),
        ('  /room delete <name>             remove a room', None, 0),
        ('  /room enter <name>              enter a room (next plain text → room)', None, 0),
        ('  /room leave                     exit the current room', None, 0),
        ('  /room add <name> <adapter>      add a member', None, 0),
        ('  /room remove <name> <adapter>   remove a member', None, 0),
        ('  /memory                         list shared memory', None, 0),
        ('  /memory pending                 proposed shared memories', None, 0),
        ('  /memory approved                approved shared memories', None, 0),
        ('  /memory propose fact "..."      propose peer-reviewed memory', None, 0),
        ('  /memory budget                  show injection budget', None, 0),
        ('  /memory edit                    legacy current room memory editor', None, 0),
        ('', None, 0),
        ('VIEWS', C_TEAL, curses.A_BOLD),
        ('  /status                         daemon URL, health, agents, view/filter', None, 0),
        ('  /health                         raw daemon health summary', None, 0),
        ('  /agents                         configured / registered agents', None, 0),
        ('  /presence                       agent operational presence', None, 0),
        ('  /agent <id>                     agent status and recent events', None, 0),
        ('  /agent profile <id>             agent profile fields', None, 0),
        ('  /profiles                       list agent profiles', None, 0),
        ('  /runtimes                       list runtime registry', None, 0),
        ('  /runtime doctor                 runtime registry diagnostics', None, 0),
        ('  /runtime <id>                   inspect runtime', None, 0),
        ('  /workspace init|load|export     manage workspace pack', None, 0),
        ('  /workspace list                 list workspace packs', None, 0),
        ('  /flight                         live control-plane status', None, 0),
        ('  /tasks                          recent / open tasks', None, 0),
        ('  /dashboard                      overview (default)', None, 0),
        ('  /events                         live event stream', None, 0),
        ('  /conversations                  recent conversation list', None, 0),
        ('  /open <n>                       open conversation n as chat', None, 0),
        ('  /open #<room>                   open a room transcript', None, 0),
        ('  /history <conversation_id>      open by id', None, 0),
        ('  /adapters                       configured adapters', None, 0),
        ('  /deadletters                    failed deliveries', None, 0),
        ('', None, 0),
        ('FILTERING', C_TEAL, curses.A_BOLD),
        ('  /filter <type>                  filter events: ' + ', '.join(sorted(EVENT_FILTERS)), None, 0),
        ('', None, 0),
        ('CONTROLS', C_TEAL, curses.A_BOLD),
        ('  /clear                          clear local command output', None, 0),
        ('  TAB                             autocomplete commands & mentions', None, 0),
        ('  Up/Down PgUp/PgDn Home/End      scroll chat history / jump live', None, 0),
        ('  /term, n, N                     search chat transcript', None, 0),
        ('  Enter                           submit', None, 0),
        ('  Ctrl-C  ×2                      quit (within 2 seconds)', None, 0),
        ('  /quit                           leave the TUI', None, 0),
    ]
    _panel_lines(stdscr, top, 0, w, avail_h, HELP)


def _view_local_output(stdscr, label: str, lines: list[str], top, h, w):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title=label.upper())
    rendered: list[tuple] = []
    for line in lines:
        rendered.extend((chunk, None, 0) for chunk in (_wrap(line, max(10, w - 6)) or ['']))
    _panel_lines(stdscr, top, 0, w, avail_h, rendered or [('(no output)', C_MUTED, curses.A_DIM)])


def _format_memory_lines(memory: dict) -> list[str]:
    fields = [
        ("room", memory.get("room") or memory.get("room_name")),
        ("purpose", memory.get("purpose")),
        ("objective", memory.get("objective")),
        ("focus", memory.get("current_focus")),
        ("rules", memory.get("rules")),
        ("constraints", memory.get("constraints")),
        ("notes", memory.get("notes")),
        ("updated", memory.get("updated_at")),
        ("updated by", memory.get("updated_by")),
    ]
    return [f"{label:<11} {value or '(empty)'}" for label, value in fields]


def _format_shared_memory_summary(memory: dict) -> str:
    room = f" room=#{memory.get('room_name')}" if memory.get('room_name') else ""
    confidence = memory.get('confidence')
    return (
        f"{memory.get('memory_id')}  {memory.get('status')}  {memory.get('memory_type')}  "
        f"conf={confidence}{room}  {str(memory.get('content') or '')[:100]}"
    )


def _format_shared_memory_lines(memory: dict) -> list[str]:
    fields = [
        ("memory", memory.get("memory_id")),
        ("status", memory.get("status")),
        ("type", memory.get("memory_type")),
        ("confidence", memory.get("confidence")),
        ("room", memory.get("room_name") or "(global)"),
        ("workspace", memory.get("workspace") or "(global)"),
        ("created by", memory.get("created_by")),
        ("reviewed by", memory.get("reviewed_by")),
        ("review", memory.get("review_result")),
        ("reason", memory.get("review_reason")),
        ("approved by", memory.get("approved_by")),
        ("use count", memory.get("use_count")),
        ("last used", memory.get("last_used_at")),
    ]
    lines = [f"{label:<12} {value if value not in (None, '') else '(empty)'}" for label, value in fields]
    lines.extend(["", "content", str(memory.get("content") or "")])
    events = memory.get("events") or []
    if events:
        lines.extend(["", "events"])
        for event in events[-12:]:
            lines.append(f"  {event.get('created_at')}  {event.get('event_type')}  {event.get('actor') or ''}")
    return lines


def _memory_command_lines(cmd: str, base: str, state: dict) -> tuple[str, list[str]]:
    def room_suffix() -> str:
        return f"&room={state['current_room']}" if state.get('current_room') else ""

    if cmd in {'/memory', '/memory pending', '/memory approved', '/memory rejected'}:
        status_map = {
            '/memory pending': 'proposed',
            '/memory approved': 'peer_approved',
            '/memory rejected': 'rejected',
        }
        status = status_map.get(cmd)
        query = f"?limit=50{room_suffix()}"
        if status:
            query = f"?status={status}&limit=50{room_suffix()}"
        memories = _get_json(f"{base}/v1/memory{query}").get("memories", [])
        label = "shared memory" if not status else f"shared memory {status}"
        return (label, [_format_shared_memory_summary(item) for item in memories] or ["(no memories)"])
    if cmd.startswith('/memory propose '):
        try:
            parts = shlex.split(cmd[len('/memory propose '):])
        except ValueError as exc:
            return ('memory', [f'parse error: {exc}'])
        if len(parts) < 2:
            return ('memory', ['usage: /memory propose <type> "content"'])
        memory_type = parts[0]
        content = ' '.join(parts[1:])
        payload = {
            "memory_type": memory_type,
            "content": content,
            "created_by": "synkraken-tui",
        }
        if state.get('current_room'):
            payload["room_name"] = state['current_room']
        result = _post_json(f"{base}/v1/memory/propose", payload)
        memory = result.get("memory") or {}
        return ('memory proposed', _format_shared_memory_lines(memory))
    if cmd.startswith('/memory review '):
        parts = cmd.split(' ', 2)
        if len(parts) < 3 or not parts[2].strip():
            return ('memory review', ['usage: /memory review <id>'])
        result = _post_json(f"{base}/v1/memory/{parts[2].strip()}/review", {'actor': 'synkraken-tui'})
        return ('memory review', _format_shared_memory_lines(result.get("memory") or {}))
    if cmd.startswith('/memory approve ') or cmd.startswith('/memory reject ') or cmd.startswith('/memory archive '):
        parts = cmd.split()
        if len(parts) < 3:
            return ('memory', [f'usage: {parts[0]} {parts[1]} <id>'])
        action = parts[1]
        result = _post_json(f"{base}/v1/memory/{parts[2]}/{action}", {'actor': 'synkraken-tui'})
        return (f'memory {action}', _format_shared_memory_lines(result.get("memory") or {}))
    if cmd.startswith('/memory search '):
        try:
            parts = shlex.split(cmd[len('/memory search '):])
        except ValueError as exc:
            return ('memory search', [f'parse error: {exc}'])
        query = ' '.join(parts).strip()
        if not query:
            return ('memory search', ['usage: /memory search "query"'])
        memories = _get_json(f"{base}/v1/memory/search?q={urllib.parse.quote(query)}").get("memories", [])
        return ('memory search', [_format_shared_memory_summary(item) for item in memories] or ["(no matches)"])
    if cmd == '/memory budget':
        suffix = f"?room={state['current_room']}" if state.get('current_room') else ""
        budget = _get_json(f"{base}/v1/memory/budget{suffix}")
        lines = [
            f"approved memories       {budget.get('approved_memories')}",
            f"injected max items      {budget.get('injected_max_items')}",
            f"injected max chars      {budget.get('injected_max_chars')}",
            f"max memory chars        {budget.get('max_memory_chars')}",
            f"min confidence          {budget.get('min_confidence')}",
            f"estimated chars         {budget.get('estimated_chars')}",
            f"estimated tokens        {budget.get('estimated_tokens')}",
            "",
            "selected",
        ]
        lines.extend(_format_shared_memory_summary(item) for item in budget.get("selected", []))
        return ('memory budget', lines)
    if cmd.startswith('/memory show '):
        memory_id = cmd.split(' ', 2)[2].strip()
        if not memory_id:
            return ('memory show', ['usage: /memory show <id>'])
        return ('memory show', _format_shared_memory_lines(_get_json(f"{base}/v1/memory/{memory_id}")))

    room = state.get('current_room')
    if not room:
        return ('memory', ['usage: /memory [pending|approved|rejected|propose|review|approve|reject|archive|search|budget|show]'])
    path = f"{base}/v1/rooms/{room}/memory"
    if cmd == '/memory':
        return (f'#{room} memory', _format_memory_lines(_get_json(path)))
    if cmd == '/memory edit':
        memory = _get_json(path)
        lines = _format_memory_lines(memory)
        lines.extend([
            '',
            'set with:',
            '  /memory set purpose "..."',
            '  /memory set objective "..."',
            '  /memory set focus "..."',
            '  /memory set rules "..."',
            '  /memory set constraints "..."',
            '  /memory set notes "..."',
        ])
        return (f'#{room} memory', lines)
    if cmd.startswith('/memory set '):
        try:
            parts = shlex.split(cmd[len('/memory set '):])
        except ValueError as exc:
            return ('memory', [f'parse error: {exc}'])
        if len(parts) < 2:
            return ('memory', ['usage: /memory set <purpose|objective|focus|rules|constraints|notes> "value"'])
        aliases = {'focus': 'current_focus'}
        field = aliases.get(parts[0], parts[0])
        if field not in {'purpose', 'objective', 'current_focus', 'rules', 'constraints', 'notes'}:
            return ('memory', [f'unknown memory field: {parts[0]}'])
        value = ' '.join(parts[1:])
        memory = _put_json(path, {field: value, 'actor': 'synkraken-tui'})
        return (f'#{room} memory', _format_memory_lines(memory))
    return ('memory', ['usage: /memory [edit|set <field> "value"]'])


def _format_team_run_lines(run: dict) -> list[str]:
    lines = [
        f"team run      {run.get('team_run_id')}",
        f"room          {run.get('room_name')}",
        f"status        {run.get('status')}",
        f"owner         {run.get('owner_agent') or '(none)'}",
        f"reviewers     {', '.join(run.get('reviewers') or []) or '(none)'}",
        f"participants  {', '.join(run.get('participants') or []) or '(none)'}",
        f"approval      {'required' if run.get('approval_required') else 'auto'}",
        f"approved by   {run.get('approved_by') or '(none)'}",
        f"started       {run.get('started_at')}",
        f"completed     {run.get('completed_at') or '(pending)'}",
        f"prompt        {run.get('source_prompt') or ''}",
    ]
    if run.get('final_report'):
        lines.extend(['', 'final report'])
        lines.extend(str(run.get('final_report')).splitlines())
    failure = run.get('failure_summary') or {}
    if failure:
        lines.extend([
            '',
            'failure summary',
            f"  phase    {failure.get('phase') or '(unknown)'}",
            f"  agent    {failure.get('agent') or '(unknown)'}",
            f"  elapsed  {failure.get('elapsed_ms') if failure.get('elapsed_ms') is not None else '(unknown)'}ms",
            f"  reason   {failure.get('reason') or '(none)'}",
        ])
    events = run.get('events') or []
    if events:
        lines.extend(['', 'events'])
        for event in events[-12:]:
            detail = f"  {event.get('detail')}" if event.get('detail') else ''
            lines.append(f"  {event.get('created_at')}  {event.get('event_type')}  {event.get('actor') or ''}{detail}")
    messages = run.get('messages') or (failure.get('partial_transcript') if failure else []) or []
    if messages:
        lines.extend(['', 'partial transcript'])
        for message in messages[-12:]:
            body = str(message.get('body') or '').replace('\n', ' / ')
            lines.append(f"  {message.get('source')}: {body[:160]}")
    return lines


def _team_governance_command_lines(cmd: str, base: str, state: dict) -> tuple[str, list[str]] | None:
    if cmd == '/team-runs':
        suffix = f"?room={state['current_room']}" if state.get('current_room') else ""
        runs = _get_json(f'{base}/v1/team-runs{suffix}').get('team_runs', [])
        if not runs:
            return ('team runs', ['(no team runs)'])
        return ('team runs', [
            f"{run.get('team_run_id')}  {run.get('status')}  "
            f"owner={run.get('owner_agent') or '(none)'}  room=#{run.get('room_name')}  "
            f"approval={'required' if run.get('approval_required') else 'auto'}"
            for run in runs
        ])
    if cmd.startswith('/team-run '):
        team_run_id = cmd.split(' ', 1)[1].strip()
        if not team_run_id:
            return ('team run', ['usage: /team-run <id>'])
        return ('team run', _format_team_run_lines(_get_json(f'{base}/v1/team-runs/{team_run_id}')))
    if cmd == '/team-run':
        return ('team run', ['usage: /team-run <id>'])
    return None


def _format_goal_run_lines(run: dict) -> list[str]:
    lines = [
        f"goal run       {run.get('goal_run_id')}",
        f"room           {run.get('room_name')}",
        f"status         {run.get('status')}",
        f"round          {run.get('current_round')}/{run.get('max_rounds')}",
        f"score          {run.get('latest_score')}/{run.get('threshold')}",
        f"owner          {run.get('owner_agent') or '(none)'}",
        f"reviewers      {', '.join(run.get('reviewers') or []) or '(none)'}",
        f"token police   {run.get('token_police_agent') or '(none)'}",
        f"guardrail      {run.get('guardrail_agent') or '(none)'}",
        f"context chars   {run.get('estimated_context_chars')}/{run.get('token_budget_chars')}",
        f"guardrail stat {run.get('guardrail_status') or '(none)'}",
        f"task           {run.get('linked_task_id') or '(none)'}",
        f"started        {run.get('started_at')}",
        f"completed      {run.get('completed_at') or '(pending)'}",
        f"goal           {run.get('source_goal') or ''}",
    ]
    if run.get('success_criteria'):
        lines.extend(['', 'success criteria'])
        lines.extend(str(run.get('success_criteria')).splitlines()[:20])
    if run.get('final_report'):
        lines.extend(['', 'final report'])
        lines.extend(str(run.get('final_report')).splitlines())
    events = run.get('events') or []
    if events:
        lines.extend(['', 'events'])
        for event in events[-16:]:
            detail = f"  {event.get('details')}" if event.get('details') else ''
            lines.append(f"  {event.get('created_at')}  {event.get('event_type')}  {event.get('actor') or ''}{detail}")
    return lines


def _goal_command_lines(cmd: str, base: str, state: dict) -> tuple[str, list[str]] | None:
    if cmd == '/goals':
        suffix = f"?room={state['current_room']}" if state.get('current_room') else ""
        runs = _get_json(f'{base}/v1/goal-runs{suffix}').get('goal_runs', [])
        if not runs:
            return ('goal runs', ['(no goal runs)'])
        return ('goal runs', [
            f"{run.get('goal_run_id')}  {run.get('status')}  "
            f"round={run.get('current_round')}/{run.get('max_rounds')}  "
            f"score={run.get('latest_score')}/{run.get('threshold')}  "
            f"owner={run.get('owner_agent') or '(none)'}  room=#{run.get('room_name')}"
            for run in runs
        ])
    if cmd.startswith('/goal-run '):
        goal_run_id = cmd.split(' ', 1)[1].strip()
        if not goal_run_id:
            return ('goal run', ['usage: /goal-run <id>'])
        return ('goal run', _format_goal_run_lines(_get_json(f'{base}/v1/goal-runs/{goal_run_id}')))
    if cmd == '/goal-run':
        return ('goal run', ['usage: /goal-run <id>'])
    if cmd.startswith('/cancel-goal '):
        goal_run_id = cmd.split(' ', 1)[1].strip()
        if not goal_run_id:
            return ('cancel goal', ['usage: /cancel-goal <id>'])
        result = _post_json(f'{base}/v1/goal-runs/{goal_run_id}/cancel', {'actor': 'synkraken-tui'})
        return ('cancel goal', _format_goal_run_lines(result.get('goal_run') or {}))
    if cmd == '/cancel-goal':
        return ('cancel goal', ['usage: /cancel-goal <id>'])
    return None


def _decision_command_lines(cmd: str, base: str, state: dict) -> tuple[str, list[str]] | None:
    if cmd == '/decisions':
        suffix = f"?room={state['current_room']}" if state.get('current_room') else ""
        decisions = _get_json(f'{base}/v1/decisions{suffix}').get('decisions', [])
        if not decisions:
            return ('decisions', ['(no decisions)'])
        return ('decisions', [
            f"{d.get('id') or d.get('decision_id')}  {d.get('status')}  "
            f"{str(d.get('created_at') or d.get('timestamp') or '')[:10]}  "
            f"{str(d.get('title') or '')[:80]}  proposed_by={d.get('proposed_by') or '-'}"
            for d in decisions
        ])
    if cmd == '/decision latest':
        suffix = f"?room={state['current_room']}" if state.get('current_room') else ""
        try:
            decision = _get_json(f'{base}/v1/decision/latest{suffix}')
        except Exception:
            return ('decision latest', ['(no decisions)'])
        return ('decision latest', _format_decision_lines(decision))
    if cmd.startswith('/decision '):
        decision_id = cmd.split(' ', 1)[1].strip()
        if not decision_id:
            return ('decision', ['usage: /decision <id>'])
        try:
            d = _get_json(f'{base}/v1/decision/{decision_id}')
        except Exception:
            return ('decision', [f'could not load decision: {decision_id}'])
        return ('decision', _format_decision_lines(d))
    if cmd == '/decision':
        return ('decision', ['usage: /decision latest | /decision <id>'])
    return None


def _format_decision_lines(d: dict) -> list[str]:
    lines = [
        f"decision        {d.get('id') or d.get('decision_id')}",
        f"status          {d.get('status')}",
        f"title           {d.get('title')}",
        f"proposed_by     {d.get('proposed_by') or '-'}",
        f"approved_by     {d.get('approved_by') or '-'}",
        f"room            {d.get('room_id') or d.get('room_name') or '-'}",
        f"task            {d.get('task_id') or '-'}",
        f"goal            {d.get('goal_id') or '-'}",
        f"confidence      {d.get('confidence') if d.get('confidence') is not None else '-'}",
        '',
        f"summary         {str(d.get('summary') or '')[:160]}",
        f"reason          {str(d.get('reason') or d.get('reasoning') or '')[:160]}",
    ]
    runtimes = d.get('linked_runtime_ids') or []
    messages = d.get('linked_message_ids') or []
    if runtimes or messages:
        lines.extend([
            '',
            f"runtimes        {', '.join(runtimes) or '-'}",
            f"messages        {', '.join(messages) or '-'}",
        ])
    events = d.get('events') or []
    if events:
        lines.extend(['', 'events'])
        for ev in events[-12:]:
            lines.append(f"  {str(ev.get('created_at') or '')[:19]}  {ev.get('event_type')}  actor={ev.get('actor') or '-'}")
    return lines


def _handoff_command_lines(cmd: str, base: str, state: dict) -> tuple[str, list[str]] | None:
    if cmd == '/handoffs':
        suffix = f"?room={state['current_room']}" if state.get('current_room') else ""
        handoffs = _get_json(f'{base}/v1/handoffs{suffix}').get('handoffs', [])
        if not handoffs:
            return ('handoffs', ['(no handoffs)'])
        return ('handoffs', [
            f"[{h.get('status'):10}] {h.get('created_at')[:10]}  "
            f"{h.get('from_agent')} -> {h.get('to_agent')}: "
            f"{h.get('summary', '')[:w-55]}"
            for h in handoffs
        ])
    if cmd.startswith('/handoff '):
        parts = cmd.split(' ', 2)
        action = parts[1] if len(parts) > 1 else ''
        handoff_id = parts[2].strip() if len(parts) > 2 else ''
        if action == 'create':
            return ('handoff', ['use POST /v1/handoff to create a handoff'])
        if action in ('accept', 'reject', 'complete'):
            if not handoff_id:
                return ('handoff', [f'usage: /handoff {action} <id>'])
            result = _post_json(f'{base}/v1/handoff/{handoff_id}/{action}', {'actor': 'synkraken-tui'})
            h = result.get('handoff', {})
            return ('handoff', [f"{h.get('handoff_id')}  status={h.get('status')}"])
        if handoff_id:
            try:
                h = _get_json(f'{base}/v1/handoffs/{handoff_id}')
            except Exception:
                return ('handoff', [f'could not load handoff: {handoff_id}'])
            lines = [
                f"handoff_id      {h.get('handoff_id')}",
                f"status          {h.get('status')}",
                f"from_agent      {h.get('from_agent')}",
                f"to_agent        {h.get('to_agent')}",
                f"room            {h.get('room_name') or '-'}",
                f"task            {h.get('task_id') or '-'}",
                f"confidence      {h.get('confidence')}",
                f"next_step       {h.get('recommended_next_step')}",
                '',
                f"summary:        {h.get('summary')}",
                f"open_questions: {', '.join(h.get('open_questions') or [])}",
                f"risks:          {', '.join(h.get('risks') or [])}",
                '',
                "Events:",
            ]
            for ev in h.get('events', []):
                lines.append(f"  {ev.get('created_at')[:19]}  {ev.get('event_type')}  actor={ev.get('actor')}")
            return ('handoff', lines)
        return ('handoff', ['usage: /handoff [create|accept|reject|complete|<id>]'])
    if cmd == '/handoff':
        return ('handoff', ['usage: /handoff [create|accept|reject|complete|<id>]'])
    return None


def _local_command_lines(cmd: str, base: str, data: dict, state: dict) -> tuple[str, list[str]] | None:
    """Return local-only slash command output without touching the router."""
    health = data.get('health', {})
    agents = data.get('agents', {}).get('agents', [])
    if cmd == '/status':
        return ('status', [
            f'daemon URL      {base}',
            f"daemon health   {'healthy' if health.get('ok') else 'unhealthy'}",
            f'agent count     {len(agents)}',
            f"current view    {state.get('view', 'dashboard')}",
            f"current filter  {state.get('event_filter', 'all')}",
            f"transcript      {_transcript_key(state)}",
            f"scroll offset   {int(_transcript_state(state).get('scroll_offset') or 0)} lines",
        ])
    if cmd == '/health':
        return ('health', json.dumps(health, indent=2, ensure_ascii=False).splitlines())
    if cmd == '/flight':
        flight = _get_json(f'{base}/v1/flight')
        return ('flight', [
            f"agents online   {flight.get('agents_online')}/{flight.get('agents_total')}",
            f"active goals    {flight.get('active_goals')}",
            f"blocked goals   {flight.get('blocked_goals')}",
            f"token risk      {flight.get('token_risk')}",
            f"failures        {flight.get('failures')}",
            f"dead letters    {flight.get('dead_letters')}",
            f"cost complexity {flight.get('cost_complexity')}",
            f"cost tiers      {json.dumps((flight.get('cost_profiles') or {}).get('cost_tiers') or {}, sort_keys=True)}",
            f"usage risk      {json.dumps((flight.get('cost_profiles') or {}).get('usage_risk') or {}, sort_keys=True)}",
            f"memory count    {flight.get('memory_count')}",
            f"pending reviews {flight.get('pending_reviews')}",
        ])
    if cmd == '/runtimes':
        runtimes = _get_json(f'{base}/v1/runtimes').get('runtimes', [])
        return ('runtimes', [
            f"{item.get('runtime_id')}  type={item.get('runtime_type')}  cost={item.get('cost_tier') or item.get('cost_profile')}  risk={item.get('usage_risk', 'medium')}  roles={','.join(item.get('preferred_roles') or []) or '-'}  avoid={','.join(item.get('avoid_roles') or []) or '-'}  timeout={item.get('timeout')}  modes={','.join(item.get('supported_modes') or []) or '-'}"
            for item in runtimes
        ] or ['(no runtimes)'])
    if cmd == '/runtime doctor':
        doctor = _get_json(f'{base}/v1/runtimes/doctor').get('runtimes', [])
        return ('runtime doctor', [
            f"{item.get('runtime_id')}  {'ok' if item.get('ok') else 'check'}  registered={item.get('registered')}  cost={item.get('cost_tier', 'medium')}  risk={item.get('usage_risk', 'medium')}  roles={','.join(item.get('preferred_roles') or []) or '-'}  avoid={','.join(item.get('avoid_roles') or []) or '-'}  warnings={','.join(item.get('warnings') or []) or '-'}"
            for item in doctor
        ] or ['(no runtimes)'])
    if cmd.startswith('/runtime '):
        runtime_id = cmd.split(' ', 1)[1].strip()
        runtime = _get_json(f'{base}/v1/runtimes/{runtime_id}')
        return ('runtime', json.dumps(runtime, indent=2, ensure_ascii=False).splitlines())
    if cmd == '/runtime':
        return ('runtime', ['usage: /runtime <id> | /runtime doctor'])
    if cmd.startswith('/workspace'):
        parts = cmd.split()
        if len(parts) < 2:
            return ('workspace', ['usage: /workspace init|load|export|list [name]'])
        action = parts[1]
        name = parts[2] if len(parts) > 2 else None
        if action == 'list':
            workspaces = _get_json(f'{base}/v1/workspaces').get('workspaces', [])
            return ('workspaces', [
                f"{item.get('name')}  rooms={len(item.get('rooms') or [])} agents={len(item.get('agents') or [])} runtimes={len(item.get('runtime_refs') or [])}"
                for item in workspaces
            ] or ['(no workspaces)'])
        if action in {'init', 'load', 'export'}:
            result = _post_json(f'{base}/v1/workspaces/{action}', {'name': name} if name else {})
            return ('workspace', json.dumps(result.get('workspace', {}), indent=2, ensure_ascii=False).splitlines())
        return ('workspace', [f'unknown workspace command: {action}'])
    if cmd == '/agents':
        if not agents:
            return ('agents', ['(no agents configured)'])
        lines = []
        for agent in agents:
            marker = 'enabled' if agent.get('enabled', False) else 'disabled'
            lines.append(
                f"{_runtime_label(agent)} [{agent.get('adapter_id', '')}] "
                f"type={agent.get('type', '')} {marker}"
            )
        return ('agents', lines)
    if cmd == '/presence':
        if not agents:
            return ('presence', ['(no agents configured)'])
        return ('presence', [_agent_presence_line(agent) for agent in agents])
    if cmd == '/profiles':
        if not agents:
            return ('profiles', ['(no agents configured)'])
        return ('profiles', [
            f"{agent.get('adapter_id')}  cost={agent.get('cost_tier', 'medium')}  "
            f"speed={agent.get('speed', 5)} trust={agent.get('trust', 5)}  "
            f"roles={','.join(agent.get('preferred_roles') or []) or '-'}  "
            f"caps={','.join(agent.get('capabilities') or []) or '-'}"
            for agent in agents
        ])
    if cmd.startswith('/agent profile '):
        agent_id = cmd.split(' ', 2)[2].strip()
        if not agent_id:
            return ('agent profile', ['usage: /agent profile <adapter_id>'])
        try:
            profile = _get_json(f"{base}/v1/agents/{agent_id}/profile").get('profile', {})
        except Exception as exc:  # noqa: BLE001
            return ('agent profile', [f'unavailable: {exc}'])
        if not profile:
            return ('agent profile', [f'unknown agent: {agent_id}'])
        return ('agent profile', [
            f"agent          {profile.get('adapter_id')}",
            f"cost tier      {profile.get('cost_tier', 'medium')}",
            f"preferred      {', '.join(profile.get('preferred_roles') or []) or '(none)'}",
            f"capabilities   {', '.join(profile.get('capabilities') or []) or '(none)'}",
            f"speed          {profile.get('speed', 5)}/10",
            f"trust          {profile.get('trust', 5)}/10",
        ])
    if cmd.startswith('/agent '):
        agent_id = cmd.split(' ', 1)[1].strip()
        agent = next((item for item in agents if item.get('adapter_id') == agent_id), None)
        if not agent:
            return ('agent', [f'unknown agent: {agent_id}'])
        lines = [
            f"agent          {agent.get('adapter_id')}",
            f"status         {agent.get('status')}",
            f"last seen      {agent.get('last_seen_at') or '(never)'}",
            f"task           {agent.get('current_task_id') or '(none)'}",
            f"room           {agent.get('current_room') or '(none)'}",
            f"last message   {agent.get('last_message_at') or '(none)'}",
        ]
        try:
            events = _get_json(f"{base}/v1/agents/{agent_id}/events?limit=5").get('events', [])
        except Exception as exc:  # noqa: BLE001
            events = []
            lines.append(f"events         unavailable: {exc}")
        if events:
            lines.append('recent events')
            for event in events:
                lines.append(
                    f"  {event.get('created_at')}  {event.get('event_type')}  "
                    f"{event.get('old_value') or ''} -> {event.get('new_value') or ''}"
                )
        return ('agent', lines)
    if cmd == '/agent':
        return ('agent', ['usage: /agent <adapter_id>'])
    if cmd == '/rooms':
        rooms = data.get('rooms', {}).get('rooms', [])
        if not rooms:
            return ('rooms', ['(no rooms yet)'])
        return ('rooms', [
            f"#{room.get('name', '')}  members={room.get('member_count', 0)}"
            for room in rooms
        ])
    if cmd == '/tasks':
        tasks = data.get('tasks', {}).get('tasks', [])
        visible = [task for task in tasks if task.get('status') != 'done'] or tasks[:10]
        if not visible:
            return ('tasks', ['(no tasks)'])
        return ('tasks', [
            f"{task.get('status', 'unknown'):<11} {task.get('task_id', '')}  {task.get('title', '')}"
            for task in visible[:10]
        ])
    if cmd == '/transcript':
        return ('transcript', _transcript_mode_lines(state, base))
    return None


def _is_unknown_slash_command(cmd: str) -> bool:
    return cmd.startswith('/') and cmd.split(' ', 1)[0] not in COMMANDS


# ── command-result view ───────────────────────────────────────────────────
def _view_command_result(stdscr, label, result, top, h, w):
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title=f'RESULT  •  {label}')
    lines: list[tuple] = []
    msg = result.get('message') or {}
    # Only show route/ids when they're actually present (room CRUD and other
    # non-message ops produce empty values that just look noisy).
    cid = msg.get('conversation_id') or ''
    mid = msg.get('message_id') or ''
    src = msg.get('source') or ''
    tgt = msg.get('target') or ''
    if src or tgt or cid:
        if cid:
            lines.append((f"conversation_id   {cid}", C_MUTED, 0))
        if mid:
            lines.append((f"message_id        {mid}", C_MUTED, 0))
        if src or tgt:
            lines.append((f"route             {src} → {tgt}", C_MUTED, 0))
        lines.append(('', None, 0))
    deliveries = result.get('deliveries', [])
    if not deliveries and not result.get('dead_letters'):
        lines.append(('(no deliveries)', C_MUTED, curses.A_DIM))
    for d in deliveries:
        aid = d.get('adapter_id', '')
        label_ = d.get('runtime_name') or aid
        ok = bool(d.get('ok'))
        d_color, l_color = _agent_color(aid)
        marker = '✓' if ok else '✗'
        # Format the metadata line: omit duration when None, render ms cleanly.
        dur_ms = d.get('duration_ms')
        dur = f"{dur_ms}ms" if dur_ms is not None else ''
        parts = [f"{marker} {label_} [{aid}]", f"attempts={d.get('attempts', 1)}"]
        if dur:
            parts.append(dur)
        lines.append(('   '.join(parts), d_color if ok else C_RED, curses.A_BOLD))
        if d.get('error'):
            lines.append((f"   error: {d.get('error')}", C_RED, 0))
        body = (d.get('body') or '').strip()
        if body:
            for chunk in _wrap(body, w - 8):
                lines.append((f"   {chunk}", l_color, 0))
        lines.append(('', None, 0))
    dl = result.get('dead_letters', [])
    if dl:
        lines.append(('DEAD LETTERS', C_RED, curses.A_BOLD))
        for it in dl:
            lines.append((f"  ✗ {it.get('adapter_id')}: {it.get('reason')}", C_RED, 0))
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


# ── status bar + prompt ───────────────────────────────────────────────────
def _draw_status_bar(stdscr, y, w, state, connected, dead_count, typing_names, view):
    sep = '  │  '
    parts = [
        f' {NAME} ',
        f'view: {view}',
        f'agents: {connected}',
    ]
    if state.get('current_room'):
        parts.insert(1, f"room: #{state['current_room']}")
    if typing_names:
        parts.append(f"typing: {', '.join(typing_names)}")
    parts.append(f"filter: {state['event_filter']}")
    parts.append(f"refresh: {state['refresh_seconds']}s")
    if dead_count:
        parts.append(f"⚠ dead: {dead_count}")
    text = sep.join(parts)
    _safe_addstr(stdscr, y, 0, ' ' * (w - 1), w - 1, C_NAVY, curses.A_REVERSE)
    _safe_addstr(stdscr, y, 0, text[:w - 1], w - 1, C_NAVY, curses.A_REVERSE | curses.A_BOLD)


def _draw_prompt(stdscr, y, w, command, hint, in_room: str | None):
    if hint:
        _safe_addstr(stdscr, y - 1, 0, hint[:w - 1], w - 1, C_TEAL, curses.A_DIM)
    if in_room:
        prefix = f' #{in_room} › '
        _safe_addstr(stdscr, y, 0, prefix, len(prefix) + 1, C_ROOM, curses.A_BOLD)
        _safe_addstr(stdscr, y, len(prefix), command[:max(0, w - 1 - len(prefix))],
                     max(0, w - 1 - len(prefix)), C_BRIGHT, curses.A_BOLD)
    else:
        prefix = ' › '
        _safe_addstr(stdscr, y, 0, prefix, len(prefix) + 1, C_TEAL, curses.A_BOLD)
        _safe_addstr(stdscr, y, len(prefix), command[:max(0, w - 1 - len(prefix))],
                     max(0, w - 1 - len(prefix)), C_BRIGHT, curses.A_BOLD)


# ── command handlers ──────────────────────────────────────────────────────
SPINNER_FRAMES = ('⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏')


def _spinner_frame() -> str:
    return SPINNER_FRAMES[int(time.time() * 10) % len(SPINNER_FRAMES)]


def _handle_send(base: str, target: str, body: str) -> dict:
    return _post_json(f'{base}/v1/messages', {'source': 'synkraken-tui', 'target': target, 'body': body})


def _mention_route(target: str, body: str, current_room: str | None) -> tuple[str, str]:
    """Resolve mention routing while preserving an explicit global escape hatch."""
    stripped = body.strip()
    if stripped.startswith('--global '):
        return target, stripped[len('--global '):].strip()
    if target == 'broadcast' and current_room:
        return f'room:{current_room}', stripped
    return target, stripped


def _parse_leading_mentions(cmd: str, aliases: dict[str, str]) -> tuple[list[str], str]:
    """Parse only leading @mentions as routing targets.

    Mentions later in the sentence, especially quoted ones like ``"@goose"``,
    are message content rather than delivery targets.
    """
    remaining = cmd.strip()
    targets: list[str] = []
    while remaining.startswith('@'):
        match = re.match(r'@([A-Za-z0-9._-]+)(?:\s+|$)', remaining)
        if not match:
            break
        name = match.group(1)
        target = aliases.get(name.lower())
        if target is None:
            break
        if target == 'broadcast':
            targets = ['broadcast']
            remaining = remaining[match.end():].lstrip()
            break
        if target not in targets:
            targets.append(target)
        remaining = remaining[match.end():].lstrip()
    return targets, remaining


def _start_async_send(state: dict, base: str, target: str, body: str,
                      label: str, *, return_view: str | None = None,
                      metadata: dict | None = None) -> None:
    """Kick off a POST /v1/messages in the background.

    The main loop reaps `state['pending']` each frame and surfaces the result.
    `return_view` controls where the user lands when the send completes:
      - None: smart default (stay on dashboard/chat/rooms; otherwise show command-result)
      - 'command-result': always show the result view
      - 'chat': keep current chat view (for in-conversation replies)
    """
    pending = {
        'label': label, 'target': target, 'body': body,
        'metadata': metadata or {},
        'started_at': time.time(), 'done': False,
        'result': None, 'error': None, 'return_view': return_view,
    }
    state['pending'] = pending
    temp_message = {
        'message_id': f"pending:{time.time()}",
        'conversation_id': '',
        'source': 'synkraken-tui',
        'target': target,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'body': body,
    }
    base_result = {}
    if state.get('view') == 'chat' and state.get('command_result'):
        base_result = dict(state['command_result'][1])
    messages = list(base_result.get('messages', []))
    messages.append(temp_message)
    state['command_result'] = (label, {
        'conversation_id': '',
        'messages': messages,
        'deliveries': list(base_result.get('deliveries', [])),
        'dead_letters': list(base_result.get('dead_letters', [])),
    })
    state['chat_target'] = target
    state['view'] = 'chat'

    def run():
        try:
            pending['result'] = _post_json(
                f'{base}/v1/messages',
                {'source': 'synkraken-tui', 'target': target, 'body': body,
                 'metadata': metadata or {}},
            )
        except Exception as exc:  # noqa: BLE001
            pending['error'] = str(exc)
        finally:
            pending['done'] = True

    threading.Thread(target=run, daemon=True).start()


def _start_async_multi_send(state: dict, base: str, targets: list[str], body: str,
                            label: str = '@mentions') -> None:
    """Kick off multiple directed sends in one background worker."""
    pending = {
        'label': label, 'target': ','.join(targets), 'body': body,
        'started_at': time.time(), 'done': False,
        'result': None, 'error': None, 'return_view': 'command-result',
    }
    state['pending'] = pending
    temp_message = {
        'message_id': f"pending:{time.time()}",
        'conversation_id': '',
        'source': 'synkraken-tui',
        'target': ','.join(targets),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'body': body,
    }
    base_result = {}
    if state.get('view') == 'chat' and state.get('command_result'):
        base_result = dict(state['command_result'][1])
    messages = list(base_result.get('messages', []))
    messages.append(temp_message)
    state['command_result'] = (label, {
        'conversation_id': '',
        'messages': messages,
        'deliveries': list(base_result.get('deliveries', [])),
        'dead_letters': list(base_result.get('dead_letters', [])),
    })
    state['chat_target'] = ','.join(targets)
    state['view'] = 'chat'

    def run():
        combined = {'message': {'source': 'synkraken-tui'},
                    'deliveries': [], 'dead_letters': []}
        try:
            for target in targets:
                try:
                    result = _handle_send(base, target, body)
                    combined['message'] = result.get('message') or combined['message']
                    combined['deliveries'].extend(result.get('deliveries', []))
                    combined['dead_letters'].extend(result.get('dead_letters', []))
                except Exception as exc:  # noqa: BLE001
                    combined['dead_letters'].append({'adapter_id': target, 'reason': str(exc)})
            pending['result'] = combined
        except Exception as exc:  # noqa: BLE001
            pending['error'] = str(exc)
        finally:
            pending['done'] = True

    threading.Thread(target=run, daemon=True).start()


def _handle_history(base: str, conversation_id: str) -> dict:
    return _get_json(f'{base}/v1/conversations/{conversation_id}')


def _handle_room_transcript(base: str, name: str) -> dict:
    data = _get_json(f'{base}/v1/rooms/{name}/messages')
    return {
        'conversation_id': f'room:{name}',
        'messages': data.get('messages', []),
        'deliveries': [],
        'dead_letters': [],
    }


def _parse_discuss_args(rest: str, current_room: str | None) -> dict[str, Any]:
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        raise ValueError(f'invalid /discuss syntax: {exc}') from None
    max_turns = 4
    room_name = current_room
    values: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--turns':
            i += 1
            if i >= len(parts):
                raise ValueError('usage: /discuss [--turns N] [--room name] <agent1> <agent2> "topic"')
            max_turns = int(parts[i])
        elif part == '--room':
            i += 1
            if i >= len(parts):
                raise ValueError('usage: /discuss [--turns N] [--room name] <agent1> <agent2> "topic"')
            room_name = parts[i].lstrip('#')
        else:
            values.append(part)
        i += 1
    if len(values) < 3:
        raise ValueError('usage: /discuss [--turns N] [--room name] <agent1> <agent2> "topic"')
    return {
        'agents': values[:-1],
        'topic': values[-1],
        'max_turns': max_turns,
        'room_name': room_name,
    }


def _handle_discussion(base: str, params: dict[str, Any]) -> dict:
    payload = {
        'source': 'synkraken-tui',
        'agents': params['agents'],
        'topic': params['topic'],
        'max_turns': params['max_turns'],
    }
    if params.get('room_name'):
        payload['room_name'] = params['room_name']
    return _post_json(f'{base}/v1/discussions', payload)


def _parse_team_args(rest: str, current_room: str | None) -> dict[str, Any]:
    if not current_room:
        raise ValueError('Team mode needs a room. Create or select a room first.')
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        raise ValueError(f'invalid /team syntax: {exc}') from None
    turns = 4
    values: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--turns':
            i += 1
            if i >= len(parts):
                raise ValueError('usage: /team [--turns N] "question or task"')
            turns = int(parts[i])
        else:
            values.append(part)
        i += 1
    question = ' '.join(values).strip()
    if not question:
        raise ValueError('usage: /team [--turns N] "question or task"')
    return {'room_name': current_room, 'question': question, 'turns': turns}


def _handle_team_task(base: str, params: dict[str, Any]) -> dict:
    return _post_json(f'{base}/v1/team-tasks', {
        'source': 'synkraken-tui',
        'room_name': params['room_name'],
        'question': params['question'],
        'turns': params['turns'],
    })


def _parse_goal_args(rest: str, current_room: str | None) -> dict[str, Any]:
    if not current_room:
        raise ValueError('Goal mode needs a room. Create or select a room first.')
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        raise ValueError(f'invalid /goal syntax: {exc}') from None
    threshold = 80
    rounds = 3
    mode = 'balanced'
    values: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--threshold':
            i += 1
            if i >= len(parts):
                raise ValueError('usage: /goal [--threshold N] [--rounds N] "goal text"')
            threshold = int(parts[i])
        elif part == '--rounds':
            i += 1
            if i >= len(parts):
                raise ValueError('usage: /goal [--mode cheap|balanced|full] [--threshold N] [--rounds N] "goal text"')
            rounds = int(parts[i])
        elif part == '--mode':
            i += 1
            if i >= len(parts):
                raise ValueError('usage: /goal [--mode cheap|balanced|full] [--threshold N] [--rounds N] "goal text"')
            mode = parts[i].strip().lower()
            if mode not in {'cheap', 'balanced', 'full'}:
                raise ValueError('goal mode must be cheap, balanced, or full')
        else:
            values.append(part)
        i += 1
    goal = ' '.join(values).strip()
    if not goal:
        raise ValueError('usage: /goal [--mode cheap|balanced|full] [--threshold N] [--rounds N] "goal text"')
    return {'room_name': current_room, 'goal': goal, 'threshold': threshold, 'max_rounds': rounds, 'mode': mode}


def _handle_goal_run(base: str, params: dict[str, Any]) -> dict:
    return _post_json(f'{base}/v1/goal-runs', {
        'source': 'synkraken-tui',
        'room_name': params['room_name'],
        'goal': params['goal'],
        'threshold': params['threshold'],
        'max_rounds': params['max_rounds'],
        'mode': params.get('mode', 'balanced'),
    })


def _start_async_discussion(state: dict, base: str, params: dict[str, Any]) -> None:
    agents = params['agents']
    topic = params['topic']
    room_name = params.get('room_name')
    label = f"discussion #{room_name}" if room_name else 'discussion'
    pending = {
        'label': label,
        'target': f"room:{room_name}" if room_name else 'discussion',
        'body': topic,
        'started_at': time.time(),
        'done': False,
        'result': None,
        'error': None,
        'return_view': 'chat',
        'discussion': True,
        'room_name': room_name,
    }
    state['pending'] = pending
    state['command_result'] = (label, {
        'conversation_id': '',
        'messages': [{
            'message_id': f"pending-discussion:{time.time()}",
            'conversation_id': '',
            'source': 'synkraken-tui',
            'target': pending['target'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'body': f"Discussion topic: {topic}",
        }],
        'deliveries': [],
        'dead_letters': [],
    })
    state['chat_target'] = pending['target']
    state['view'] = 'chat'

    def run():
        try:
            pending['result'] = _handle_discussion(base, params)
        except Exception as exc:  # noqa: BLE001
            pending['error'] = str(exc)
        finally:
            pending['done'] = True

    threading.Thread(target=run, daemon=True).start()


def _start_async_team_task(state: dict, base: str, params: dict[str, Any]) -> None:
    room_name = params['room_name']
    question = params['question']
    label = f"team #{room_name}"
    pending = {
        'label': label,
        'target': f"room:{room_name}",
        'body': question,
        'started_at': time.time(),
        'done': False,
        'result': None,
        'error': None,
        'return_view': 'chat',
        'team_task': True,
        'room_name': room_name,
    }
    state['pending'] = pending
    state['command_result'] = (f'#{room_name}', {
        'conversation_id': '',
        'messages': [{
            'message_id': f"pending-team:{time.time()}",
            'conversation_id': '',
            'source': 'synkraken-tui',
            'target': pending['target'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'body': f"Team task: {question}",
        }],
        'deliveries': [],
        'dead_letters': [],
    })
    state['chat_target'] = pending['target']
    state['view'] = 'chat'

    def run():
        try:
            pending['result'] = _handle_team_task(base, params)
        except Exception as exc:  # noqa: BLE001
            pending['error'] = str(exc)
        finally:
            pending['done'] = True

    threading.Thread(target=run, daemon=True).start()


def _start_async_goal_run(state: dict, base: str, params: dict[str, Any]) -> None:
    room_name = params['room_name']
    goal = params['goal']
    label = f"goal #{room_name}"
    pending = {
        'label': label,
        'target': f"room:{room_name}",
        'body': goal,
        'started_at': time.time(),
        'done': False,
        'result': None,
        'error': None,
        'return_view': 'chat',
        'goal_run': True,
        'room_name': room_name,
    }
    state['pending'] = pending
    state['command_result'] = (f'#{room_name}', {
        'conversation_id': '',
        'messages': [{
            'message_id': f"pending-goal:{time.time()}",
            'conversation_id': '',
            'source': 'synkraken-tui',
            'target': pending['target'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'body': f"Goal: {goal}",
        }],
        'deliveries': [],
        'dead_letters': [],
    })
    state['chat_target'] = pending['target']
    state['view'] = 'chat'

    def run():
        try:
            pending['result'] = _handle_goal_run(base, params)
        except Exception as exc:  # noqa: BLE001
            pending['error'] = str(exc)
        finally:
            pending['done'] = True

    threading.Thread(target=run, daemon=True).start()


def _normalize_command(cmd: str) -> str:
    cmd = cmd.strip()
    if not cmd or cmd.startswith(('@', '/', '#')):
        return cmd
    first = cmd.split(' ', 1)[0]
    if first in {c.lstrip('/') for c in COMMANDS}:
        return '/' + cmd
    return cmd


def _autocomplete(command: str, data: dict) -> tuple[str, str]:
    command = _normalize_command(command)

    # @mentions
    if command.startswith('@') and ' ' not in command:
        aliases = sorted(_mention_alias_map(data).keys())
        matches = ['@' + a for a in aliases if ('@' + a).startswith(command.lower())]
        if len(matches) == 1:
            return matches[0] + ' ', ''
        if matches:
            return command, 'mentions: ' + ', '.join(matches[:8])
        return command, ''

    # #room
    if command.startswith('#') and ' ' not in command:
        names = [r.get('name', '') for r in data.get('rooms', {}).get('rooms', [])]
        matches = ['#' + n for n in names if ('#' + n).startswith(command.lower())]
        if len(matches) == 1:
            return matches[0] + ' ', ''
        if matches:
            return command, 'rooms: ' + ', '.join(matches[:8])
        return command, ''

    # /command
    if not command.startswith('/'):
        return command, ''
    if ' ' not in command:
        matches = [c for c in COMMANDS if c.startswith(command)]
        if len(matches) == 1:
            return matches[0] + ' ', ''
        if matches:
            return command, 'matches: ' + ', '.join(matches[:8])
        return command, ''
    head, rest = command.split(' ', 1)
    parts = rest.split(' ')
    if head in ('/send', '/compose') and len(parts) == 1 and parts[0]:
        ids = _agent_ids(data) + ['broadcast', 'openclaw', 'main']
        matches = [a for a in ids if a.startswith(parts[0])]
        if len(matches) == 1:
            return f'{head} {matches[0]} ', ''
        if matches:
            return command, 'targets: ' + ', '.join(matches)
    if head == '/room' and len(parts) == 1:
        matches = [s for s in ROOM_SUBCOMMANDS if s.startswith(parts[0])]
        if len(matches) == 1:
            return f'/room {matches[0]} ', ''
        if matches:
            return command, 'subcommands: ' + ', '.join(matches)
    if head == '/room' and len(parts) >= 2 and parts[0] in ('enter', 'delete', 'add', 'remove'):
        names = [r.get('name', '') for r in data.get('rooms', {}).get('rooms', [])]
        prefix_words = parts[:1]
        target_word = parts[1]
        matches = [n for n in names if n.startswith(target_word)]
        if len(matches) == 1:
            new_rest = ' '.join(prefix_words + [matches[0]] + parts[2:]) + (' ' if len(parts) == 2 else '')
            return f'/room {new_rest}', ''
        if matches:
            return command, 'rooms: ' + ', '.join(matches)
    if head == '/filter' and rest:
        matches = [f for f in EVENT_FILTERS if f.startswith(rest)]
        if len(matches) == 1:
            return f'/filter {matches[0]}', ''
        if matches:
            return command, 'filters: ' + ', '.join(sorted(matches))
    return command, ''


def _open_by_index(data: dict, idx: int, base: str) -> tuple[str, dict]:
    conversations = data.get('recent', {}).get('conversations', [])
    if idx < 1 or idx > len(conversations):
        return ('history error',
                {'conversation_id': '', 'messages': [], 'deliveries': [],
                 'dead_letters': [{'adapter_id': 'history', 'reason': f'No conversation at index {idx}'}]})
    cid = conversations[idx - 1].get('conversation_id', '')
    return (f'history {cid[:12]}', _handle_history(base, cid))


# ── colour setup ──────────────────────────────────────────────────────────
def _init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK

    if curses.COLORS >= 256:
        curses.init_pair(C_RED,        196, bg)
        curses.init_pair(C_TEAL,        45, bg)
        curses.init_pair(C_BLUE,        32, bg)
        curses.init_pair(C_NAVY,        25, bg)
        curses.init_pair(C_MUTED,      244, bg)
        curses.init_pair(C_BRIGHT,      87, bg)
        curses.init_pair(C_OK,          84, bg)
        curses.init_pair(C_WARN,       214, bg)
        curses.init_pair(C_TYPING,     119, bg)
        curses.init_pair(C_GOOSE_D,    244, bg)
        curses.init_pair(C_GOOSE_L,    250, bg)
        curses.init_pair(C_HERMES_D,   178, bg)
        curses.init_pair(C_HERMES_L,   220, bg)
        curses.init_pair(C_OPENCLAW_D, 167, bg)
        curses.init_pair(C_OPENCLAW_L, 209, bg)
        curses.init_pair(C_OPERATOR_D, 153, bg)
        curses.init_pair(C_OPERATOR_L, 159, bg)
        curses.init_pair(C_ROOM,       141, bg)
        curses.init_pair(C_CLAUDE_D,   173, bg)   # warm tan / Claude brand
        curses.init_pair(C_CLAUDE_L,   215, bg)
        curses.init_pair(C_CRUSH_D,     93, bg)   # vivid purple
        curses.init_pair(C_CRUSH_L,    219, bg)   # light magenta
    else:
        curses.init_pair(C_RED,        curses.COLOR_RED, bg)
        curses.init_pair(C_TEAL,       curses.COLOR_CYAN, bg)
        curses.init_pair(C_BLUE,       curses.COLOR_BLUE, bg)
        curses.init_pair(C_NAVY,       curses.COLOR_BLUE, bg)
        curses.init_pair(C_MUTED,      curses.COLOR_WHITE, bg)
        curses.init_pair(C_BRIGHT,     curses.COLOR_CYAN, bg)
        curses.init_pair(C_OK,         curses.COLOR_GREEN, bg)
        curses.init_pair(C_WARN,       curses.COLOR_YELLOW, bg)
        curses.init_pair(C_TYPING,     curses.COLOR_GREEN, bg)
        curses.init_pair(C_GOOSE_D,    curses.COLOR_WHITE, bg)
        curses.init_pair(C_GOOSE_L,    curses.COLOR_WHITE, bg)
        curses.init_pair(C_HERMES_D,   curses.COLOR_YELLOW, bg)
        curses.init_pair(C_HERMES_L,   curses.COLOR_YELLOW, bg)
        curses.init_pair(C_OPENCLAW_D, curses.COLOR_RED, bg)
        curses.init_pair(C_OPENCLAW_L, curses.COLOR_RED, bg)
        curses.init_pair(C_OPERATOR_D, curses.COLOR_CYAN, bg)
        curses.init_pair(C_OPERATOR_L, curses.COLOR_CYAN, bg)
        curses.init_pair(C_ROOM,       curses.COLOR_MAGENTA, bg)
        curses.init_pair(C_CLAUDE_D,   curses.COLOR_YELLOW, bg)
        curses.init_pair(C_CLAUDE_L,   curses.COLOR_YELLOW, bg)
        curses.init_pair(C_CRUSH_D,    curses.COLOR_MAGENTA, bg)
        curses.init_pair(C_CRUSH_L,    curses.COLOR_MAGENTA, bg)

    # SYNKRAKEN wordmark ocean fade (pairs 30..36)
    if curses.COLORS >= 256:
        for i, c256 in enumerate(LOGO_ROW_XTERM256):
            try:
                curses.init_pair(_WORDMARK_PAIR_OFFSET + i, c256, bg)
            except curses.error:
                curses.init_pair(_WORDMARK_PAIR_OFFSET + i, curses.COLOR_CYAN, bg)
    else:
        fallback = [curses.COLOR_CYAN] * 3 + [curses.COLOR_BLUE] * 3 + [curses.COLOR_CYAN]
        for i, c in enumerate(fallback):
            curses.init_pair(_WORDMARK_PAIR_OFFSET + i, c, bg)

    # Kraken sigil vertical fade (pairs 40..47) — bright crown → navy tips
    if curses.COLORS >= 256:
        for i, c256 in enumerate(KRAKEN_ROW_XTERM256):
            try:
                curses.init_pair(_KRAKEN_PAIR_OFFSET + i, c256, bg)
            except curses.error:
                curses.init_pair(_KRAKEN_PAIR_OFFSET + i, curses.COLOR_CYAN, bg)
    else:
        k_fallback = [curses.COLOR_CYAN, curses.COLOR_CYAN, curses.COLOR_CYAN,
                      curses.COLOR_BLUE, curses.COLOR_BLUE, curses.COLOR_BLUE,
                      curses.COLOR_BLUE, curses.COLOR_BLUE]
        for i, c in enumerate(k_fallback):
            curses.init_pair(_KRAKEN_PAIR_OFFSET + i, c, bg)


# ── room command dispatcher ───────────────────────────────────────────────
def _exec_room_command(base: str, rest: str, state: dict, data: dict) -> tuple[str, dict | None, str]:
    """Returns (label, command_result_for_view, hint)."""
    if not rest:
        return ('rooms', None, 'usage: /room <create|delete|enter|leave|add|remove|members|kick|list> …')
    parts = rest.split()
    sub = parts[0]
    args = parts[1:]
    if sub == 'list':
        return ('rooms', None, '')  # caller will switch to rooms view
    if sub == 'enter':
        if not args:
            return ('rooms', None, 'usage: /room enter <name>')
        name = args[0].lstrip('#').lower()
        result = _handle_room_transcript(base, name)
        state['current_room'] = name
        save_preferences(state)
        return (f'#{name}', result, f'in #{name}  ·  type to chat  ·  /room leave to exit')
    if sub == 'leave':
        if not state.get('current_room'):
            return ('rooms', None, 'not in a room')
        prev = state['current_room']
        state['current_room'] = None
        save_preferences(state)
        return (f'leave #{prev}', None, f'left #{prev}')
    if sub == 'create':
        if not args:
            return ('rooms', None, 'usage: /room create <name> [member1 member2 …]')
        name = args[0].lstrip('#').lower()
        members = [_resolve_target(m.lstrip('@')) for m in args[1:]]
        try:
            _post_json(f'{base}/v1/rooms',
                       {'name': name, 'description': '', 'members': members})
            # Auto-enter the new room so the user can immediately chat into it
            # by typing plain text — no need to follow up with `/room enter`.
            state['current_room'] = name
            save_preferences(state)
            mc = len(members)
            plural = '' if mc == 1 else 's'
            return (f'#{name}', _handle_room_transcript(base, name),
                    f'created and entered #{name}  ·  {mc} member{plural}  ·  type to chat')
        except Exception as exc:  # noqa: BLE001
            return ('create error',
                    {'message': {}, 'deliveries': [],
                     'dead_letters': [{'adapter_id': f'room:{name}', 'reason': str(exc)}]},
                    '')
    if sub == 'delete':
        if not args:
            return ('rooms', None, 'usage: /room delete <name>')
        name = args[0].lstrip('#').lower()
        try:
            _delete(f'{base}/v1/rooms/{name}')
            if state.get('current_room') == name:
                state['current_room'] = None
            return ('rooms', None, f'room #{name} deleted')
        except Exception as exc:  # noqa: BLE001
            return ('delete error',
                    {'message': {}, 'deliveries': [],
                     'dead_letters': [{'adapter_id': f'room:{name}', 'reason': str(exc)}]},
                    '')
    if sub == 'add':
        if len(args) < 2:
            return ('rooms', None, 'usage: /room add <name> <adapter_id>')
        name = args[0].lstrip('#').lower()
        adapter = _resolve_target(args[1].lstrip('@'))
        try:
            room = _post_json(f'{base}/v1/rooms/{name}/members', {'adapter_id': adapter})
            return ('rooms', None, f'added {adapter} to #{name}')
        except Exception as exc:  # noqa: BLE001
            return ('add error',
                    {'message': {}, 'deliveries': [],
                     'dead_letters': [{'adapter_id': adapter, 'reason': str(exc)}]},
                    '')
    if sub == 'members':
        if not args:
            return ('rooms', None, 'usage: /room members <name>')
        name = args[0].lstrip('#').lower()
        try:
            room = _get_json(f'{base}/v1/rooms/{name}')
            members = [member.get('adapter_id') for member in room.get('members', [])]
            return ('room members', None, f"#{name}: {', '.join(members) if members else '(none)'}")
        except Exception as exc:  # noqa: BLE001
            return ('members error',
                    {'message': {}, 'deliveries': [],
                     'dead_letters': [{'adapter_id': f'room:{name}', 'reason': str(exc)}]},
                    '')
    if sub in {'remove', 'kick'}:
        if len(args) < 2:
            return ('rooms', None, f'usage: /room {sub} <name> <adapter_id>')
        name = args[0].lstrip('#').lower()
        adapter = _resolve_target(args[1].lstrip('@'))
        try:
            _delete(f'{base}/v1/rooms/{name}/members/{adapter}')
            verb = 'kicked' if sub == 'kick' else 'removed'
            return ('rooms', None, f'{verb} {adapter} from #{name}')
        except Exception as exc:  # noqa: BLE001
            return (f'{sub} error',
                    {'message': {}, 'deliveries': [],
                     'dead_letters': [{'adapter_id': adapter, 'reason': str(exc)}]},
                    '')
    return ('rooms', None, f'unknown room subcommand: {sub}')


# ── main loop ──────────────────────────────────────────────────────────────
def _main(stdscr):
    prefs = load_preferences()
    state = {
        'view': prefs.get('default_view', 'dashboard'),
        'event_filter': prefs.get('event_filter', 'all'),
        'refresh_seconds': prefs.get('refresh_seconds', 3),
        'last_target': prefs.get('last_target', 'hermes'),
        'current_room': prefs.get('current_room'),
        'command_result': None,
        'local_output': None,
        'pending': None,        # in-flight send (set by _start_async_send)
        'chat_target': None,    # target captured when /open <n> or /open #x is run
        'transcripts': {},
        'last_chat_total_lines': 0,
        'last_chat_viewport_h': 1,
        'last_team_run_id': None,
        'last_goal_run_id': None,
    }
    _init_colors()
    curses.curs_set(1)
    stdscr.keypad(True)
    # 120 ms tick gives ~8 fps — enough for a smooth spinner without burning CPU.
    stdscr.timeout(120)
    base = DEFAULT_BASE
    command = ''
    hint = ''
    previous_sigint = _install_sigint_handler()
    try:
        data = _fetch_dashboard(base)
    except Exception as exc:  # noqa: BLE001
        data = {'health': {'ok': False, 'timestamp': '', 'error': str(exc)},
                'agents': {'agents': []}, 'recent': {'conversations': []},
                'deliveries': {'deliveries': []}, 'dead_letters': {'dead_letters': []},
                'rooms': {'rooms': []}, 'tasks': {'tasks': []}}
    stream = EventStreamWorker(base)
    stream.start()
    last_refresh = 0.0

    try:
        while True:
            now = time.time()
            if now - last_refresh >= state['refresh_seconds']:
                try:
                    data = _fetch_dashboard(base)
                except Exception as exc:  # noqa: BLE001
                    data = {'health': {'ok': False, 'timestamp': '', 'error': str(exc)},
                            'agents': {'agents': []}, 'recent': {'conversations': []},
                            'deliveries': {'deliveries': []}, 'dead_letters': {'dead_letters': []},
                            'rooms': {'rooms': []}, 'tasks': {'tasks': []}}
                last_refresh = now
                if state.get('view') == 'chat' and state.get('current_room'):
                    room_name = state['current_room']
                    try:
                        state['command_result'] = (f'#{room_name}', _handle_room_transcript(base, room_name))
                        state['chat_target'] = f'room:{room_name}'
                    except Exception:
                        pass

            # Reap completed async send (runs every frame). When done we
            # surface the result and force a data refresh so the dashboard's
            # LATEST REPLIES and RECENT CONVERSATIONS reflect it immediately.
            if state.get('pending') and state['pending'].get('done'):
                p = state.pop('pending')
                if p.get('error'):
                    if (p.get('team_task') or p.get('goal_run')) and p.get('room_name'):
                        room_name = p['room_name']
                        run_kind = 'Goal' if p.get('goal_run') else 'Team'
                        endpoint = 'goal-runs' if p.get('goal_run') else 'team-runs'
                        inspect_cmd = '/goal-run' if p.get('goal_run') else '/team-run'
                        try:
                            transcript = _handle_room_transcript(base, room_name)
                            key = 'goal_runs' if p.get('goal_run') else 'team_runs'
                            runs = _get_json(f'{base}/v1/{endpoint}?room={room_name}&limit=1').get(key, [])
                            id_key = 'goal_run_id' if p.get('goal_run') else 'team_run_id'
                            summary = {
                                'message_id': f"{endpoint}-timeout:{time.time()}",
                                'conversation_id': '',
                                'source': 'synkraken-goal' if p.get('goal_run') else 'synkraken-team',
                                'target': f"room:{room_name}",
                                'timestamp': datetime.now(timezone.utc).isoformat(),
                                'body': (
                                    f"{run_kind} run request timed out in the TUI.\n"
                                    f"Room transcript is still visible for #{room_name}.\n"
                                    f"Latest run: {runs[0].get(id_key) if runs else '(pending)'}\n"
                                    f"Inspect: {inspect_cmd} {runs[0].get(id_key) if runs else '<id>'}\n"
                                    f"Client error: {p['error']}"
                                ),
                            }
                            transcript.setdefault('messages', []).append(summary)
                            state['command_result'] = (f'#{room_name}', transcript)
                            state['chat_target'] = f'room:{room_name}'
                            state['view'] = 'chat'
                        except Exception:
                            state['command_result'] = (f"{p['label']}  ✗",
                                {'message': {'body': f"Team run request timed out: {p['error']}"},
                                 'deliveries': [], 'dead_letters': []})
                            state['view'] = 'command-result'
                    else:
                        state['command_result'] = (f"{p['label']}  ✗",
                            {'message': {}, 'deliveries': [],
                             'dead_letters': [{'adapter_id': p['target'], 'reason': p['error']}]})
                        state['view'] = 'command-result'
                else:
                    if p.get('team_task'):
                        result = p.get('result') or {}
                        run = result.get('team_run') or {}
                        run_id = run.get('team_run_id') or result.get('team_run_id')
                        if run_id:
                            state['last_team_run_id'] = run_id
                    if p.get('goal_run'):
                        result = p.get('result') or {}
                        run = result.get('goal_run') or {}
                        run_id = run.get('goal_run_id') or result.get('goal_run_id')
                        if run_id:
                            state['last_goal_run_id'] = run_id
                    if (p.get('discussion') or p.get('team_task') or p.get('goal_run')) and p.get('room_name'):
                        room_name = p['room_name']
                        state['command_result'] = (
                            f'#{room_name}',
                            _handle_room_transcript(base, room_name),
                        )
                        state['chat_target'] = f'room:{room_name}'
                    elif p.get('discussion'):
                        result = p['result'] or {}
                        cid = result.get('conversation_id') or result.get('discussion_id')
                        state['command_result'] = (
                            p['label'],
                            _handle_history(base, cid) if cid else result,
                        )
                        state['chat_target'] = 'discussion'
                    elif state.get('view') == 'chat' and state.get('current_room'):
                        room_name = state['current_room']
                        state['command_result'] = (
                            f'#{room_name}',
                            _handle_room_transcript(base, room_name),
                        )
                        state['chat_target'] = f'room:{room_name}'
                    elif (state.get('view') == 'chat'
                            and str(p.get('target', '')).startswith('room:')):
                        room_name = str(p['target']).split(':', 1)[1]
                        state['command_result'] = (
                            f'#{room_name}',
                            _handle_room_transcript(base, room_name),
                        )
                        state['chat_target'] = p['target']
                    else:
                        state['command_result'] = (p['label'], p['result'])
                    # If user is browsing dashboard/chat/rooms, stay there
                    # — the new reply will appear in the relevant panel.
                    if state.get('view') not in ('dashboard', 'chat', 'rooms', 'events'):
                        state['view'] = 'command-result'
                hint = f"{p['label']}  done ({time.time() - p['started_at']:.1f}s)"
                if p.get('team_task') and state.get('last_team_run_id'):
                    run_id = state['last_team_run_id']
                    hint = f"team done  ·  view/review: /team-run {run_id}  ·  export: /save-transcript"
                if p.get('goal_run') and state.get('last_goal_run_id'):
                    run_id = state['last_goal_run_id']
                    hint = f"goal done  ·  inspect: /goal-run {run_id}  ·  export: /save-transcript"
                last_refresh = 0  # immediate refetch of the dashboard data

            events = list(stream.events)
            typing_names = stream.get_typing_names()
            typing_ids = stream.get_typing_ids()
            connected = len(data.get('agents', {}).get('agents', []))
            dead_count = len(data.get('dead_letters', {}).get('dead_letters', []))

            stdscr.erase()
            h, w = stdscr.getmaxyx()
            header_h = _draw_header(stdscr, w)
            top = header_h
            view = state.get('view', 'dashboard')

            if view == 'events':
                _view_events(stdscr, events, state, top, h, w)
            elif view == 'conversations':
                _view_conversations(stdscr, data, top, h, w)
            elif view == 'deadletters':
                _view_deadletters(stdscr, data, top, h, w)
            elif view == 'adapters':
                _view_adapters(stdscr, data, top, h, w)
            elif view == 'rooms':
                _view_rooms(stdscr, data, state, top, h, w)
            elif view == 'help':
                _view_help(stdscr, top, h, w)
            elif view == 'local-output' and state.get('local_output'):
                label, lines = state['local_output']
                _view_local_output(stdscr, label, lines, top, h, w)
            elif view == 'chat' and state.get('command_result'):
                label, result = state['command_result']
                target = state.get('chat_target')
                conversation_id = result.get('conversation_id') or None
                result = dict(result)
                result['activity'] = stream.get_delivery_activity(target, conversation_id)
                _view_chat(stdscr, result, state, top, h, w, label=label)
            elif view == 'command-result' and state.get('command_result'):
                label, result = state['command_result']
                _view_command_result(stdscr, label, result, top, h, w)
            else:
                state['view'] = 'dashboard'
                _view_dashboard(stdscr, data, state, typing_ids, top, h, w)

            _draw_status_bar(stdscr, h - 3, w, state, connected, dead_count, typing_names, view)

            if _SIGINT_STATE['count'] == 1 and time.time() - _SIGINT_STATE['last'] <= 2.0:
                hint = 'Ctrl-C again to quit'
            elif _SIGINT_STATE['count'] == 1:
                _SIGINT_STATE['count'] = 0
                if hint == 'Ctrl-C again to quit':
                    hint = ''

            # Compose the hint line in priority order:
            #   1. an active send shows a spinner (most important — user is waiting)
            #   2. an explicit hint set by the last action
            #   3. an in-room reminder of how to leave (lowest priority, ambient)
            in_room = state.get('current_room')
            if state.get('pending'):
                p = state['pending']
                elapsed = time.time() - p['started_at']
                display_hint = f"{_spinner_frame()} sending to {p['target']}  ({elapsed:.1f}s)…"
            elif hint:
                display_hint = hint
            elif in_room:
                display_hint = f"in #{in_room}  ·  type  /room leave  to exit"
            else:
                display_hint = ''

            _draw_prompt(stdscr, h - 1, w, command, display_hint, in_room)
            stdscr.refresh()

            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                break

            if ch in ('\n', '\r'):
                raw = command.strip()
                command = ''
                cmd = _normalize_command(raw)

                if cmd in ('/quit', '/exit'):
                    break
                if cmd in ('/dashboard', '/refresh', ''):
                    state['view'] = 'dashboard'
                    state['command_result'] = None
                    state['local_output'] = None
                    last_refresh = 0
                    hint = ''
                    continue
                if cmd == '/events':
                    state['view'] = 'events'; hint = ''; continue
                if cmd == '/conversations':
                    state['view'] = 'conversations'; hint = ''; continue
                if cmd == '/deadletters':
                    state['view'] = 'deadletters'; hint = ''; continue
                if cmd == '/adapters':
                    state['view'] = 'adapters'; hint = ''; continue
                if cmd == '/help':
                    state['view'] = 'help'; hint = ''; continue
                if cmd == '/clear':
                    state['view'] = 'dashboard'
                    state['command_result'] = None
                    state['local_output'] = None
                    hint = ''
                    continue
                if cmd == '/tail':
                    _reset_transcript_view(state)
                    hint = 'live transcript'
                    continue
                if cmd == '/save-transcript':
                    try:
                        path = _save_current_transcript(state)
                        state['local_output'] = ('save transcript', [f'exported {path}'])
                        state['view'] = 'local-output'
                        hint = ''
                    except Exception as exc:  # noqa: BLE001
                        state['local_output'] = ('save transcript', [str(exc)])
                        state['view'] = 'local-output'
                        hint = ''
                    continue

                if cmd == '/memory' or cmd.startswith('/memory '):
                    state['local_output'] = _memory_command_lines(cmd, base, state)
                    state['view'] = 'local-output'
                    if cmd == '/memory edit':
                        command = '/memory set '
                        hint = 'choose purpose, objective, focus, rules, constraints, or notes'
                    else:
                        hint = ''
                    continue

                team_output = _team_governance_command_lines(cmd, base, state)
                if team_output is not None:
                    state['local_output'] = team_output
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                goal_output = _goal_command_lines(cmd, base, state)
                if goal_output is not None:
                    state['local_output'] = goal_output
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                decision_output = _decision_command_lines(cmd, base, state)
                if decision_output is not None:
                    state['local_output'] = decision_output
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                handoff_output = _handoff_command_lines(cmd, base, state)
                if handoff_output is not None:
                    state['local_output'] = handoff_output
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                if cmd.startswith('/replay '):
                    replay_id = cmd.split(' ', 1)[1].strip()
                    if not replay_id:
                        state['local_output'] = ('replay', ['usage: /replay <id>'])
                        state['view'] = 'local-output'
                        hint = ''
                        continue
                    try:
                        replay = _get_json(f'{base}/v1/replay/{replay_id}')
                        lines = [
                            f"type            {replay.get('type')}",
                            f"run_id          {replay.get('run', {}).get('goal_run_id') or replay.get('run', {}).get('team_run_id') or replay_id}",
                            f"status          {replay.get('run', {}).get('status')}",
                            '',
                            "Events:",
                        ]
                        for ev in replay.get('events', []):
                            lines.append(f"  {ev.get('created_at')[:19]}  {ev.get('event_type')}  actor={ev.get('actor') or ''}")
                        lines.extend(['', 'Messages:', ''])
                        for msg in replay.get('messages', []):
                            lines.append(f"  {msg.get('source')} -> {msg.get('target')}: {str(msg.get('body') or '')[:80]}")
                        state['local_output'] = ('replay', lines)
                    except Exception as exc:
                        state['local_output'] = ('replay', [f'error: {exc}'])
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                if cmd == '/incident latest' or cmd == '/incident':
                    try:
                        incident = _get_json(f'{base}/v1/incident/latest')
                        lines = [
                            f"type            {incident.get('type')}",
                            f"run_id          {incident.get('run', {}).get('goal_run_id') or incident.get('run', {}).get('team_run_id')}",
                            f"status          {incident.get('run', {}).get('status')}",
                            '',
                            "Events:",
                        ]
                        for ev in incident.get('events', []):
                            lines.append(f"  {ev.get('created_at')[:19]}  {ev.get('event_type')}  actor={ev.get('actor') or ''}")
                        state['local_output'] = ('incident', lines)
                    except Exception:
                        state['local_output'] = ('incident', ['no incidents found'])
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                local_output = _local_command_lines(cmd, base, data, state)
                if local_output is not None:
                    state['local_output'] = local_output
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                # Match /room exactly or /room <subcommand> — NOT /roomfoo.
                if cmd == '/room' or cmd.startswith('/room '):
                    rest = cmd[len('/room'):].strip()
                    label, result, h2 = _exec_room_command(base, rest, state, data)
                    hint = h2
                    if result is not None:
                        state['command_result'] = (label, result)
                        if label.startswith('#'):
                            state['view'] = 'chat'
                            state['chat_target'] = f'room:{label[1:]}'
                        else:
                            state['view'] = 'command-result'
                    else:
                        state['view'] = 'rooms'
                    last_refresh = 0
                    continue

                if cmd.startswith('/filter '):
                    value = cmd.split(' ', 1)[1].strip()
                    if value in EVENT_FILTERS:
                        state['event_filter'] = value
                        save_preferences(state)
                        hint = f'filter set to {value}'
                    else:
                        hint = f'unknown filter: {value}'
                    continue

                # ── read-only commands (safe during a pending send) ───

                if cmd.startswith('/history '):
                    cid = cmd.split(' ', 1)[1].strip()
                    try:
                        result = _handle_history(base, cid)
                        msgs = result.get('messages', [])
                        if not msgs:
                            # Empty — treat as not-found rather than landing
                            # the user in a stale chat view with no context.
                            hint = f'no conversation {cid[:12]}'
                            continue
                        state['command_result'] = (f'history {cid[:12]}', result)
                        state['view'] = 'chat'
                        state['chat_target'] = msgs[0].get('target') or None
                    except Exception as exc:  # noqa: BLE001
                        state['command_result'] = (f'history {cid[:12]}',
                            {'conversation_id': cid, 'messages': [], 'deliveries': [],
                             'dead_letters': [{'adapter_id': 'history', 'reason': str(exc)}]})
                        state['view'] = 'command-result'
                    continue

                if cmd.startswith('/open '):
                    arg = cmd.split(' ', 1)[1].strip()
                    if arg.isdigit():
                        # /open <n> → recent conversation by index
                        try:
                            label, result = _open_by_index(data, int(arg), base)
                            state['command_result'] = (label, result)
                            state['view'] = 'chat'
                            msgs = result.get('messages', [])
                            if msgs:
                                target = msgs[0].get('target') or None
                                state['chat_target'] = target
                                # If the conversation was a room, enter it too
                                # so plain text continues into the same room.
                                if target and target.startswith('room:'):
                                    state['current_room'] = target.split(':', 1)[1]
                                    save_preferences(state)
                                hint = f'viewing chat  ·  type to send to {target}'
                        except Exception as exc:  # noqa: BLE001
                            state['command_result'] = ('history error',
                                {'conversation_id': '', 'messages': [], 'deliveries': [],
                                 'dead_letters': [{'adapter_id': 'history', 'reason': str(exc)}]})
                            state['view'] = 'command-result'
                    elif arg:
                        # /open <name>  or  /open #<name>  →  enter & view a room
                        name = arg.lstrip('#').lower()
                        try:
                            result = _handle_room_transcript(base, name)
                            state['command_result'] = (f'#{name}', result)
                            state['view'] = 'chat'
                            state['chat_target'] = f'room:{name}'
                            # Slack-style: opening a room enters it. Plain text
                            # typed after this broadcasts to the room.
                            state['current_room'] = name
                            save_preferences(state)
                            hint = f'in #{name}  ·  type to chat  ·  /room leave to exit'
                        except Exception as exc:  # noqa: BLE001
                            # Common case: the room doesn't exist. Stay on the
                            # rooms view and surface a clean hint rather than
                            # punting to the verbose command-result panel.
                            msg = str(exc)
                            if 'not found' in msg.lower() or '404' in msg:
                                state['view'] = 'rooms'
                                hint = f'no room named #{name}  ·  see /rooms or /room create'
                            else:
                                state['command_result'] = (f'#{name}',
                                    {'conversation_id': '', 'messages': [], 'deliveries': [],
                                     'dead_letters': [{'adapter_id': f'room:{name}', 'reason': msg}]})
                                state['view'] = 'command-result'
                    continue

                if cmd == '/compose':
                    ct = state.get('chat_target') or ''
                    if state.get('current_room'):
                        prefix = f"#{state['current_room']}"
                    elif ct.startswith('room:'):
                        prefix = f"#{ct.split(':', 1)[1]}"
                    else:
                        prefix = f"@{ct or state.get('last_target', 'hermes')}"
                    command = f'{prefix} '
                    hint = 'compose: complete the message and press Enter'
                    continue

                # ── send-blocking guard ───────────────────────────────
                # All read-only commands above are safe during a pending send.
                # Everything below this guard initiates a new send, so we
                # block them until the current one completes. View/quit/etc.
                # remain available throughout.
                if state.get('pending'):
                    hint = f"{_spinner_frame()} send to {state['pending']['target']} still in flight…"
                    command = raw  # preserve the text so they can resubmit
                    continue

                if (cmd.startswith('/') and state.get('view') == 'chat'
                        and state.get('command_result')
                        and cmd.split(' ', 1)[0] not in COMMANDS):
                    label, result = state['command_result']
                    lines = _chat_lines(dict(result), w)
                    term = cmd[1:].strip()
                    if _search_transcript(state, lines, term):
                        hint = f'search: {term}'
                    else:
                        hint = f'no match: {term}'
                    continue

                if _is_unknown_slash_command(cmd):
                    state['local_output'] = ('unknown command', [
                        f'Unknown command: {cmd.split(" ", 1)[0]}. Type /help.'
                    ])
                    state['view'] = 'local-output'
                    hint = ''
                    continue

                if cmd.startswith('/send '):
                    parts = cmd.split(' ', 2)
                    if len(parts) >= 3:
                        target, body = _resolve_target(parts[1]), parts[2]
                        state['last_target'] = target
                        save_preferences(state)
                        _start_async_send(state, base, target, body, f'send → {target}')
                    else:
                        hint = 'usage: /send <target> <message>'
                    continue

                if cmd.startswith('/broadcast '):
                    body = cmd.split(' ', 1)[1].strip()
                    if body:
                        _start_async_send(state, base, 'broadcast', body, 'broadcast')
                    else:
                        hint = 'usage: /broadcast <message>'
                    continue

                if cmd.startswith('/approve ') or cmd.startswith('/reject '):
                    action, record_id = cmd.split(' ', 1)
                    record_id = record_id.strip()
                    if not record_id:
                        hint = f'usage: {action} <id>'
                        continue
                    try:
                        result = _post_json(
                            f"{base}/v1/decision/{action.lstrip('/')}",
                            {'id': record_id, 'actor': 'synkraken-tui'},
                        )
                        decision = result.get('decision') or {}
                        decision['events'] = result.get('events') or []
                        state['local_output'] = (action.lstrip('/'), _format_decision_lines(decision))
                        state['view'] = 'local-output'
                        hint = f"{'approved' if action == '/approve' else 'rejected'} decision {record_id}"
                    except Exception as exc:  # noqa: BLE001
                        try:
                            result = _post_json(
                                f"{base}/v1/team-runs/{record_id}/{action.lstrip('/')}",
                                {'actor': 'synkraken-tui'},
                            )
                            run = result.get('team_run') or {}
                            state['local_output'] = (action.lstrip('/'), _format_team_run_lines(run))
                            state['view'] = 'local-output'
                            hint = f"{'approved' if action == '/approve' else 'rejected'} {record_id}"
                        except Exception:
                            state['local_output'] = (action.lstrip('/'), [str(exc)])
                            state['view'] = 'local-output'
                            hint = ''
                    continue

                if cmd.startswith('/discuss '):
                    try:
                        params = _parse_discuss_args(cmd.split(' ', 1)[1], state.get('current_room'))
                        _start_async_discussion(state, base, params)
                    except Exception as exc:  # noqa: BLE001
                        hint = str(exc)
                    continue

                if cmd == '/team' or cmd.startswith('/team '):
                    try:
                        params = _parse_team_args(cmd[len('/team'):].strip(), state.get('current_room'))
                        _start_async_team_task(state, base, params)
                    except Exception as exc:  # noqa: BLE001
                        state['local_output'] = ('team', [str(exc)])
                        state['view'] = 'local-output'
                        hint = ''
                    continue

                if cmd == '/goal' or cmd.startswith('/goal '):
                    try:
                        params = _parse_goal_args(cmd[len('/goal'):].strip(), state.get('current_room'))
                        _start_async_goal_run(state, base, params)
                    except Exception as exc:  # noqa: BLE001
                        state['local_output'] = ('goal', [str(exc)])
                        state['view'] = 'local-output'
                        hint = ''
                    continue

                # ── #room shorthand ───────────────────────────────────
                if cmd.startswith('#') and ' ' in cmd:
                    name, body = cmd[1:].split(' ', 1)
                    name = name.lower()
                    body = body.strip()
                    if body:
                        _start_async_send(state, base, f'room:{name}', body, f'#{name}')
                    continue

                # ── @mentions ─────────────────────────────────────────
                if cmd.startswith('@'):
                    aliases = _mention_alias_map(data)
                    targets_list, body = _parse_leading_mentions(cmd, aliases)
                    if targets_list and body:
                        if len(targets_list) == 1:
                            t = targets_list[0]
                            metadata = None
                            if t == 'broadcast':
                                t, body = _mention_route(t, body, state.get('current_room'))
                            elif body.startswith('--global '):
                                body = body[len('--global '):].strip()
                            elif state.get('current_room'):
                                metadata = {'room_context': f"room:{state['current_room']}"}
                            label = ('broadcast' if t == 'broadcast'
                                     else f'#{t.split(":", 1)[1]}' if t.startswith('room:')
                                     else f'@{t}')
                            _start_async_send(state, base, t, body, label, metadata=metadata)
                        else:
                            _start_async_multi_send(state, base, targets_list, body)
                    continue

                # ── in-room plain text → broadcast to room ────────────
                if state.get('current_room') and raw and not raw.startswith(('/', '@', '#')):
                    name = state['current_room']
                    _start_async_send(state, base, f'room:{name}', raw, f'#{name}')
                    continue

                # ── chat-view plain text → continues the conversation ─
                if (state.get('view') == 'chat' and raw
                        and not raw.startswith(('/', '@', '#'))
                        and state.get('chat_target')):
                    target = state['chat_target']
                    label = (f'#{target.split(":", 1)[1]}'
                             if target.startswith('room:') else f'@{target}')
                    _start_async_send(state, base, target, raw, label)
                    continue

                # Fall-through: unknown
                if raw:
                    state['command_result'] = ('unknown',
                        {'message': {}, 'deliveries': [],
                         'dead_letters': [{'adapter_id': 'unknown', 'reason': f'Unknown: {cmd}'}]})
                    state['view'] = 'command-result'
                continue

            if state.get('view') == 'chat' and command == '':
                total = int(state.get('last_chat_total_lines') or 0)
                viewport = int(state.get('last_chat_viewport_h') or 1)
                page = max(1, viewport - 2)
                if ch == curses.KEY_UP:
                    _scroll_transcript(state, 1, total, viewport)
                    hint = ''
                    continue
                if ch == curses.KEY_DOWN:
                    _scroll_transcript(state, -1, total, viewport)
                    hint = ''
                    continue
                if ch == curses.KEY_PPAGE:
                    _scroll_transcript(state, page, total, viewport)
                    hint = ''
                    continue
                if ch == curses.KEY_NPAGE:
                    _scroll_transcript(state, -page, total, viewport)
                    hint = ''
                    continue
                if ch == curses.KEY_HOME:
                    _jump_transcript(state, False, total, viewport)
                    hint = 'top of transcript'
                    continue
                if ch == curses.KEY_END:
                    _jump_transcript(state, True, total, viewport)
                    hint = 'live transcript'
                    continue
                if ch in ('n', 'N') and state.get('command_result'):
                    label, result = state['command_result']
                    lines = _chat_lines(dict(result), w)
                    if _repeat_search_transcript(state, lines, backwards=(ch == 'N')):
                        hint = f"search: {_transcript_state(state).get('search', {}).get('term')}"
                    else:
                        hint = 'no active search'
                    continue

            if ch == '\t':
                command, hint = _autocomplete(command, data)
                continue
            if ch == '\x7f' or ch == '\b' or ch == curses.KEY_BACKSPACE:
                command = command[:-1]
                hint = ''
                continue
            if isinstance(ch, str) and ch.isprintable():
                command += ch
                hint = ''

    finally:
        _restore_sigint_handler(previous_sigint)
        _SIGINT_STATE['count'] = 0
        save_preferences(state)
        stream.stop()


def run_tui() -> None:
    print('\033[2J\033[3J\033[H', end='', flush=True)
    curses.wrapper(_main)
