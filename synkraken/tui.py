from __future__ import annotations

import curses
import json
import re
import signal
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
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

# ── box-drawing ────────────────────────────────────────────────────────────
BOX = dict(tl='╭', tr='╮', bl='╰', br='╯', h='─', v='│')

# ── commands & filters ─────────────────────────────────────────────────────
COMMANDS = [
    '/dashboard', '/events', '/conversations', '/deadletters', '/adapters',
    '/rooms', '/room', '/compose', '/send', '/broadcast', '/history', '/open',
    '/filter', '/help', '/refresh', '/quit',
]
ROOM_SUBCOMMANDS = ['create', 'delete', 'enter', 'leave', 'add', 'remove', 'list']
EVENT_FILTERS = {
    'all', 'message.accepted', 'delivery.recorded', 'dead-letter.recorded',
    'typing.started', 'typing.stopped', 'stream-error',
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

    def get_typing_names(self) -> list[str]:
        with self._lock:
            self._prune_typing()
            return [self.typing_names[k] for k in self.typing.keys() if k in self.typing_names]

    def get_typing_ids(self) -> set[str]:
        with self._lock:
            self._prune_typing()
            return set(self.typing.keys())

    def _note_event(self, obj: dict[str, Any]) -> None:
        event = obj.get('event')
        data = obj.get('data', {}) or {}
        adapter_id = data.get('adapter_id')
        runtime_name = data.get('runtime_name') or adapter_id
        with self._lock:
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
    return out


# ── helpers ────────────────────────────────────────────────────────────────
def _health_marker(ok: bool) -> str:
    return '●' if ok else '○'


_AGENT_COLOR_PAIRS = {
    'goose':    (C_GOOSE_D, C_GOOSE_L),
    'hermes':   (C_HERMES_D, C_HERMES_L),
    'openclaw': (C_OPENCLAW_D, C_OPENCLAW_L),
    'claude':   (C_CLAUDE_D, C_CLAUDE_L),
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
            aliases.setdefault('stanley', aid)
            aliases.setdefault('openclaw', aid)
            aliases.setdefault('main', aid)
    return aliases


def _resolve_target(target: str) -> str:
    lowered = target.strip().lower()
    aliases = {
        'stanley': 'openclaw-main', 'openclaw': 'openclaw-main', 'main': 'openclaw-main',
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
        rn = _runtime_label(a)
        en = bool(a.get('enabled'))
        d, _ = _agent_color(aid)
        typing_now = aid in typing_ids
        marker = '●' if en else '○'
        suffix = '  typing…' if typing_now else ''
        line = f"  {marker} {rn:<10}  [{aid}]{suffix}"
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


def _view_chat(stdscr, result, top, h, w, *, label: str = 'CONVERSATION'):
    """Render messages as chat bubbles. Source = left, replies = right."""
    avail_h = h - top - 4
    _draw_panel(stdscr, top, 0, w, avail_h, title=f'CHAT  •  {label}')
    msgs = result.get('messages', [])
    deliveries = result.get('deliveries', [])
    dels_by_mid: dict[str, list[dict]] = {}
    for d in deliveries:
        dels_by_mid.setdefault(d.get('message_id'), []).append(d)

    inner_w = w - 6
    lines: list[tuple] = []
    if not msgs:
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
            lines.append(('', None, 0))

    # Show only the tail when overflowing.
    if len(lines) > avail_h - 2:
        lines = lines[-(avail_h - 2):]
    _panel_lines(stdscr, top, 0, w, avail_h, lines)


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
        atype = a.get('type', '')
        en = bool(a.get('enabled', False))
        d, _ = _agent_color(aid)
        marker = '●' if en else '○'
        lines.append((f"  {marker} {rn:<14}  [{aid}]   type={atype:<10}  enabled={str(en).lower()}",
                      d, curses.A_BOLD if en else 0))
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
        ('  @hermes @stanley please confer  send to multiple agents', None, 0),
        ('  @everyone status?               broadcast to all configured agents', None, 0),
        ('  #room hi all                    send to a specific room', None, 0),
        ('  (in a room) plain text          messages go to the current room', None, 0),
        ('', None, 0),
        ('ROOMS', C_TEAL, curses.A_BOLD),
        ('  /rooms                          list rooms', None, 0),
        ('  /room create <name> [members…] create a room (members = adapter ids)', None, 0),
        ('  /room delete <name>             remove a room', None, 0),
        ('  /room enter <name>              enter a room (next plain text → room)', None, 0),
        ('  /room leave                     exit the current room', None, 0),
        ('  /room add <name> <adapter>      add a member', None, 0),
        ('  /room remove <name> <adapter>   remove a member', None, 0),
        ('', None, 0),
        ('VIEWS', C_TEAL, curses.A_BOLD),
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
        ('  TAB                             autocomplete commands & mentions', None, 0),
        ('  Enter                           submit', None, 0),
        ('  Ctrl-C  ×2                      quit (within 2 seconds)', None, 0),
        ('  /quit                           leave the TUI', None, 0),
    ]
    _panel_lines(stdscr, top, 0, w, avail_h, HELP)


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


def _start_async_send(state: dict, base: str, target: str, body: str,
                      label: str, *, return_view: str | None = None) -> None:
    """Kick off a POST /v1/messages in the background.

    The main loop reaps `state['pending']` each frame and surfaces the result.
    `return_view` controls where the user lands when the send completes:
      - None: smart default (stay on dashboard/chat/rooms; otherwise show command-result)
      - 'command-result': always show the result view
      - 'chat': keep current chat view (for in-conversation replies)
    """
    pending = {
        'label': label, 'target': target, 'body': body,
        'started_at': time.time(), 'done': False,
        'result': None, 'error': None, 'return_view': return_view,
    }
    state['pending'] = pending

    def run():
        try:
            pending['result'] = _post_json(
                f'{base}/v1/messages',
                {'source': 'synkraken-tui', 'target': target, 'body': body},
            )
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
        ids = _agent_ids(data) + ['broadcast', 'stanley', 'openclaw', 'main']
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
        return ('rooms', None, 'usage: /room <create|delete|enter|leave|add|remove|list> …')
    parts = rest.split()
    sub = parts[0]
    args = parts[1:]
    if sub == 'list':
        return ('rooms', None, '')  # caller will switch to rooms view
    if sub == 'enter':
        if not args:
            return ('rooms', None, 'usage: /room enter <name>')
        name = args[0].lstrip('#').lower()
        state['current_room'] = name
        save_preferences(state)
        return (f'enter #{name}', None, f'entered #{name}  — plain text will broadcast to the room')
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
            return ('rooms', None,
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
    if sub == 'remove':
        if len(args) < 2:
            return ('rooms', None, 'usage: /room remove <name> <adapter_id>')
        name = args[0].lstrip('#').lower()
        adapter = _resolve_target(args[1].lstrip('@'))
        try:
            _delete(f'{base}/v1/rooms/{name}/members/{adapter}')
            return ('rooms', None, f'removed {adapter} from #{name}')
        except Exception as exc:  # noqa: BLE001
            return ('remove error',
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
        'pending': None,        # in-flight send (set by _start_async_send)
        'chat_target': None,    # target captured when /open <n> or /open #x is run
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
                'rooms': {'rooms': []}}
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
                            'rooms': {'rooms': []}}
                last_refresh = now

            # Reap completed async send (runs every frame). When done we
            # surface the result and force a data refresh so the dashboard's
            # LATEST REPLIES and RECENT CONVERSATIONS reflect it immediately.
            if state.get('pending') and state['pending'].get('done'):
                p = state.pop('pending')
                if p.get('error'):
                    state['command_result'] = (f"{p['label']}  ✗",
                        {'message': {}, 'deliveries': [],
                         'dead_letters': [{'adapter_id': p['target'], 'reason': p['error']}]})
                    state['view'] = 'command-result'
                else:
                    state['command_result'] = (p['label'], p['result'])
                    # If user is browsing dashboard/chat/rooms, stay there
                    # — the new reply will appear in the relevant panel.
                    if state.get('view') not in ('dashboard', 'chat', 'rooms', 'events'):
                        state['view'] = 'command-result'
                hint = f"{p['label']}  done ({time.time() - p['started_at']:.1f}s)"
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
            elif view == 'chat' and state.get('command_result'):
                label, result = state['command_result']
                _view_chat(stdscr, result, top, h, w, label=label)
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
                if cmd == '/rooms':
                    state['view'] = 'rooms'; hint = ''; continue
                if cmd == '/help':
                    state['view'] = 'help'; hint = ''; continue

                # Match /room exactly or /room <subcommand> — NOT /roomfoo.
                if cmd == '/room' or cmd.startswith('/room '):
                    rest = cmd[len('/room'):].strip()
                    label, result, h2 = _exec_room_command(base, rest, state, data)
                    hint = h2
                    if result is not None:
                        state['command_result'] = (label, result)
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

                # ── #room shorthand ───────────────────────────────────
                if cmd.startswith('#') and ' ' in cmd:
                    name, body = cmd[1:].split(' ', 1)
                    name = name.lower()
                    body = body.strip()
                    if body:
                        _start_async_send(state, base, f'room:{name}', body, f'#{name}')
                    continue

                # ── @mentions ─────────────────────────────────────────
                if '@' in cmd:
                    targets_list: list[str] = []
                    body = cmd
                    matches = re.findall(r'@([A-Za-z0-9._-]+)', cmd)
                    aliases = _mention_alias_map(data)
                    for name in matches:
                        key = name.lower()
                        if key in aliases:
                            t = aliases[key]
                            if t == 'broadcast':
                                targets_list = ['broadcast']
                                break
                            if t not in targets_list:
                                targets_list.append(t)
                        body = re.sub(r'@' + re.escape(name), '', body).strip()
                    if targets_list and body:
                        if len(targets_list) == 1:
                            t = targets_list[0]
                            label = 'broadcast' if t == 'broadcast' else f'@{t}'
                            _start_async_send(state, base, t, body, label)
                        else:
                            # Multi-target @mentions: fall back to sequential
                            # sync sends so we can aggregate results. Rare.
                            combined = {'message': {'source': 'synkraken-tui'},
                                        'deliveries': [], 'dead_letters': []}
                            for t in targets_list:
                                try:
                                    result = _handle_send(base, t, body)
                                    combined['message'] = result.get('message') or combined['message']
                                    combined['deliveries'].extend(result.get('deliveries', []))
                                    combined['dead_letters'].extend(result.get('dead_letters', []))
                                except Exception as exc:  # noqa: BLE001
                                    combined['dead_letters'].append({'adapter_id': t, 'reason': str(exc)})
                            state['command_result'] = ('@mentions', combined)
                            state['view'] = 'command-result'
                            last_refresh = 0
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
