from __future__ import annotations

import curses
import json
import re
import signal
import threading
import time
import urllib.request
from collections import deque
from typing import Any

from .branding import LOGO, NAME, TAGLINE
from .preferences import load_preferences, save_preferences

DEFAULT_BASE = 'http://127.0.0.1:9460'

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

COMMANDS = [
    '/dashboard', '/events', '/conversations', '/deadletters', '/adapters', '/compose',
    '/send', '/broadcast', '/history', '/open', '/filter', '/help', '/refresh', '/quit'
]
EVENT_FILTERS = {'all', 'message.accepted', 'delivery.recorded', 'dead-letter.recorded', 'typing.started', 'typing.stopped', 'stream-error'}


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
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


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

    def get_typing_names(self) -> list[str]:
        now = time.time()
        with self._lock:
            expired = [k for k, v in self.typing.items() if now - v > 10]
            for k in expired:
                self.typing.pop(k, None)
                self.typing_names.pop(k, None)
            return [self.typing_names[k] for k in self.typing.keys() if k in self.typing_names]

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


def _fetch_dashboard(base: str) -> dict:
    return {
        'health': _get_json(f'{base}/health'),
        'agents': _get_json(f'{base}/v1/agents'),
        'recent': _get_json(f'{base}/v1/conversations?limit=5'),
        'deliveries': _get_json(f'{base}/v1/deliveries?limit=5'),
        'dead_letters': _get_json(f'{base}/v1/dead-letters?limit=5'),
    }


def _safe_addstr(win, y: int, x: int, text: str, width: int, color: int | None = None) -> None:
    if width <= 0:
        return
    try:
        if color is not None:
            win.addnstr(y, x, text, width, curses.color_pair(color))
        else:
            win.addnstr(y, x, text, width)
    except curses.error:
        pass


def _draw_header(stdscr, width: int) -> int:
    logo_lines = LOGO.strip('\n').splitlines()
    for i, line in enumerate(logo_lines):
        _safe_addstr(stdscr, i, 0, line, width - 1, 2)
    return len(logo_lines)


def _health_marker(ok: bool) -> str:
    return '●' if ok else '○'


def _status_color(ok: bool) -> int:
    return 3 if ok else 1


def _agent_ids(data: dict) -> list[str]:
    return [a.get('adapter_id', '') for a in data.get('agents', {}).get('agents', []) if a.get('adapter_id')]


def _runtime_label(agent: dict) -> str:
    return agent.get('runtime_name', agent.get('adapter_id', 'unknown'))


def _mention_alias_map(data: dict) -> dict[str, str]:
    aliases: dict[str, str] = {'everyone': 'broadcast', 'all': 'broadcast'}
    for agent in data.get('agents', {}).get('agents', []):
        adapter_id = str(agent.get('adapter_id', '')).strip()
        runtime_name = str(agent.get('runtime_name', adapter_id)).strip()
        if adapter_id:
            aliases[adapter_id.lower()] = adapter_id
        if runtime_name:
            aliases[runtime_name.lower()] = adapter_id
        if adapter_id == 'openclaw-main':
            aliases.setdefault('stanley', adapter_id)
            aliases.setdefault('openclaw', adapter_id)
            aliases.setdefault('main', adapter_id)
    return aliases


def _participants_line(data: dict) -> str:
    names = []
    for agent in data.get('agents', {}).get('agents', []):
        names.append('@' + str(agent.get('runtime_name', agent.get('adapter_id'))).lower())
    names.append('@everyone')
    return 'chat targets: ' + '  '.join(names)


def _parse_mentions(command: str, data: dict) -> tuple[list[str], str] | None:
    aliases = _mention_alias_map(data)
    matches = re.findall(r'@([A-Za-z0-9._-]+)', command)
    if not matches:
        return None
    targets: list[str] = []
    for name in matches:
        key = name.lower()
        if key in aliases:
            target = aliases[key]
            if target == 'broadcast':
                return ['broadcast'], re.sub(r'@[A-Za-z0-9._-]+', '', command).strip()
            if target not in targets:
                targets.append(target)
    body = re.sub(r'@[A-Za-z0-9._-]+', '', command).strip()
    return (targets, body) if targets and body else None


def _format_event(event: dict[str, Any]) -> str:
    etype = event.get('event', 'event')
    data = event.get('data', {}) or {}
    if etype == 'message.accepted':
        return f"{etype} | {data.get('source')} -> {data.get('target')} | {data.get('conversation_id')}"
    if etype == 'delivery.recorded':
        return f"{etype} | {data.get('adapter_id')} | ok={data.get('ok')} | {data.get('status')} | {data.get('body_preview', '')}"
    if etype == 'dead-letter.recorded':
        return f"{etype} | {data.get('adapter_id')} | {data.get('reason')}"
    if etype == 'typing.started':
        return f"{etype} | {data.get('runtime_name', data.get('adapter_id'))}"
    if etype == 'typing.stopped':
        return f"{etype} | {data.get('runtime_name', data.get('adapter_id'))} | ok={data.get('ok')}"
    if etype == 'stream-error':
        return f"{etype} | {data.get('error')}"
    preview = json.dumps(data, ensure_ascii=False)[:120]
    return f"{etype} | {preview}"


def _filter_events(events: list[dict[str, Any]], filter_name: str) -> list[dict[str, Any]]:
    if filter_name == 'all':
        return events
    return [e for e in events if e.get('event') == filter_name]


def _footer_hint() -> str:
    return 'Commands: dashboard events conversations deadletters adapters compose send broadcast history open filter help refresh quit'


def _render_left(state: dict, data: dict, events: list[dict[str, Any]]) -> list[tuple[str, int | None]]:
    view = state['view']
    lines: list[tuple[str, int | None]] = []
    if view == 'dashboard':
        lines += [(f'{NAME} dashboard', 3), (TAGLINE, 3), ('', None)]
        health = data.get('health', {})
        ok = bool(health.get('ok'))
        lines.append((f"health: {_health_marker(ok)} ok={ok} time={health.get('timestamp', '')}", _status_color(ok)))
        lines += [('', None), ('agents:', 2)]
        for agent in data.get('agents', {}).get('agents', []):
            enabled = bool(agent.get('enabled'))
            lines.append((f"- {_health_marker(enabled)} {_runtime_label(agent)} [{agent.get('adapter_id')}] type={agent.get('type')}", _status_color(enabled)))
        lines += [('', None), (_participants_line(data), 2), ('', None), ('recent conversations:', 2)]
        for idx, item in enumerate(data.get('recent', {}).get('conversations', [])[:5], start=1):
            lines.append((f"{idx}. {item.get('sample_source')} -> {item.get('sample_target')} | {item.get('preview')}", None))
            lines.append((f"   {item.get('conversation_id')}", None))
    elif view == 'conversations':
        lines += [(f'{NAME} conversations', 3), (TAGLINE, 3), ('', None)]
        for idx, item in enumerate(data.get('recent', {}).get('conversations', []), start=1):
            lines.append((f"{idx}. {_health_marker(True)} {item.get('conversation_id')}", 2))
            lines.append((f"   {item.get('sample_source')} -> {item.get('sample_target')}", None))
            lines.append((f"   {item.get('preview')}", None))
            lines.append((f"   last={item.get('last_timestamp')}", None))
            lines.append(('', None))
    elif view == 'deadletters':
        lines += [(f'{NAME} dead letters', 3), (TAGLINE, 3), ('', None)]
        dead = data.get('dead_letters', {}).get('dead_letters', [])
        if not dead:
            lines.append(('No dead letters.', 3))
        for item in dead:
            lines.append((f"adapter: {item.get('adapter_id')}", 1))
            lines.append((f"reason: {item.get('reason')}", 1))
            lines.append((f"message_id: {item.get('message_id')}", 1))
            lines.append((f"created_at: {item.get('created_at')}", None))
            lines.append(('', None))
    elif view == 'adapters':
        lines += [(f'{NAME} adapters', 3), (TAGLINE, 3), ('', None)]
        for agent in data.get('agents', {}).get('agents', []):
            enabled = bool(agent.get('enabled'))
            lines.append((f"{_runtime_label(agent)}", 2))
            lines.append((f"  adapter_id: {agent.get('adapter_id')}", None))
            lines.append((f"  type: {agent.get('type')}", None))
            lines.append((f"  enabled: {enabled}", _status_color(enabled)))
            lines.append(('', None))
    elif view == 'help':
        lines += [(f'{NAME} help', 3), (TAGLINE, 3), ('', None)]
        help_lines = [
            'dashboard                overview',
            'events                   live event pane',
            'conversations            recent conversations',
            'deadletters              dead letters',
            'adapters                 adapter drill-down',
            'compose                  compose mode',
            'send <target> <message>  directed message',
            'broadcast <message>      broadcast message',
            'history <id>             stored conversation',
            'open <index>             open conversation from list',
            'filter <type|all>        filter event pane',
            'refresh                  force refresh',
            'quit                     exit',
            '',
            'Tab completes commands and targets.',
            'Compose mode prefills send using the last target.',
            'Natural chat: @goose hi  @stanley hello  @everyone status?',
        ]
        lines.extend((line, None) for line in help_lines)
        lines += [('', None), (_participants_line(data), 2)]
    elif view == 'command-result':
        title, result = state.get('command_result', ('result', {}))
        lines += [(title, 3), (TAGLINE, 3), ('', None)]
        if title.startswith('history '):
            lines += [
                (f"conversation_id: {result.get('conversation_id')}", 2),
                (f"messages: {len(result.get('messages', []))}", None),
                (f"deliveries: {len(result.get('deliveries', []))}", None),
                ('', None),
                ('messages:', 2),
            ]
            for msg in reversed(result.get('messages', [])[:8]):
                lines.append((f"- {msg.get('source')} -> {msg.get('target')} | {msg.get('timestamp')}", None))
                lines.append((f"  {(msg.get('body') or '')[:140]}", None))
            lines += [('', None), ('deliveries:', 2)]
            for delivery in reversed(result.get('deliveries', [])[:8]):
                ok = bool(delivery.get('ok'))
                lines.append((f"- {delivery.get('adapter_id')} | {delivery.get('status')} | attempts={delivery.get('attempts')}", _status_color(ok)))
                lines.append((f"  {(delivery.get('body') or '')[:140]}", None))
        else:
            message = result.get('message', {})
            if message:
                lines.append((f"conversation_id: {message.get('conversation_id')}", 2))
                lines.append((f"route: {message.get('source')} -> {message.get('target')}", None))
                lines.append(('', None))
            for delivery in reversed(result.get('deliveries', [])):
                label = delivery.get('runtime_name') or delivery.get('adapter_id', 'unknown')
                ok = bool(delivery.get('ok'))
                lines.append((f"[{label}] {_health_marker(ok)} ok={ok} attempts={delivery.get('attempts', 1)} duration_ms={delivery.get('duration_ms')}", _status_color(ok)))
                if delivery.get('error'):
                    lines.append((f"  error: {delivery.get('error')}", 1))
                if delivery.get('body'):
                    lines.append((f"  {(delivery.get('body') or '')[:160]}", None))
                lines.append(('', None))
    else:
        lines += [(f'{NAME} dashboard', 3), (TAGLINE, 3)]
    return lines


def _render_right(state: dict, events: list[dict[str, Any]], data: dict) -> list[tuple[str, int | None]]:
    lines: list[tuple[str, int | None]] = [('live events', 2), ('', None)]
    filtered = _filter_events(events, state['event_filter'])
    if not filtered:
        lines.append(('No events.', None))
    for event in filtered[:10]:
        color = 1 if event.get('event') in ('dead-letter.recorded', 'stream-error') else 3 if event.get('event') in ('typing.started', 'typing.stopped') else None
        lines.append((_format_event(event), color))
    lines += [('', None), ('recent deliveries', 2)]
    for item in data.get('deliveries', {}).get('deliveries', [])[:5]:
        ok = bool(item.get('ok'))
        lines.append((f"{_health_marker(ok)} {item.get('adapter_id')} | {item.get('status')} | {item.get('body_preview')}", _status_color(ok)))
    return lines


def _draw(stdscr, left_lines: list[tuple[str, int | None]], right_lines: list[tuple[str, int | None]], command: str, hint: str, state: dict, typing_names: list[str], connected_count: int, dead_count: int) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    header_h = _draw_header(stdscr, w)
    bar_h = 3
    body_y = header_h + 1
    body_h = max(0, h - body_y - bar_h)
    combined = left_lines + [('', None), ('events / activity', 2), ('', None)] + right_lines
    # Smart scrolling: for command-result, prioritize showing the bottom (deliveries are newest there)
    view = state.get('view', 'dashboard')
    if view == 'command-result' and len(combined) > body_h:
        # Show the last body_h lines, ensuring deliveries (at the bottom) are visible
        visible_start = max(0, len(combined) - body_h)
        visible = combined[visible_start:]
    else:
        visible = combined[-body_h:] if len(combined) > body_h else combined
    for i, (line, color) in enumerate(visible[:body_h]):
        _safe_addstr(stdscr, body_y + i, 0, line, max(0, w - 1), color)
    top_bar_y = h - 3
    status_y = h - 2
    bottom_bar_y = h - 1
    border = '─' * max(1, w - 1)
    _safe_addstr(stdscr, top_bar_y, 0, border, max(0, w - 1), 2)
    typing_text = 'typing: none' if not typing_names else 'typing: ' + ', '.join(typing_names) + ' is typing'
    status = f" {connected_count} agents connected | {typing_text} | view={state['view']} | filter={state['event_filter']} | refresh={state['refresh_seconds']}s | dead letters={dead_count} "
    status_display = status[: max(1, w - 1)]
    _safe_addstr(stdscr, status_y, 0, ' ' * max(1, w - 1), max(0, w - 1), 3)
    _safe_addstr(stdscr, status_y, 0, status_display, max(0, w - 1), 3)
    _safe_addstr(stdscr, bottom_bar_y, 0, border, max(0, w - 1), 2)
    if body_h > 0:
        _safe_addstr(stdscr, top_bar_y - 1, 0, _footer_hint(), max(0, w - 1), 3 if hint else None)
    _safe_addstr(stdscr, bottom_bar_y, 0, border, max(0, w - 1), 2)
    # put command prompt on last visible line above bar
    prompt_y = max(header_h + 1, h - 4)
    _safe_addstr(stdscr, prompt_y, 0, ' ' * max(1, w - 1), max(0, w - 1))
    _safe_addstr(stdscr, prompt_y, 0, f'> {command}', max(0, w - 1))
    if hint:
        _safe_addstr(stdscr, max(header_h, prompt_y - 1), 0, hint, max(0, w - 1), 3)
    stdscr.refresh()


def _handle_send(base: str, target: str, body: str) -> dict:
    return _post_json(f'{base}/v1/messages', {'source': 'synkraken-tui', 'target': target, 'body': body})


def _handle_history(base: str, conversation_id: str) -> dict:
    return _get_json(f'{base}/v1/conversations/{conversation_id}')


def _normalize_command(cmd: str) -> str:
    cmd = cmd.strip()
    if not cmd:
        return cmd
    if '@' in cmd:
        return cmd
    if cmd.startswith('/'):
        return cmd
    first = cmd.split(' ', 1)[0]
    if first in {c.lstrip('/') for c in COMMANDS}:
        return '/' + cmd
    return cmd


def _autocomplete(command: str, data: dict) -> tuple[str, str]:
    command = _normalize_command(command)
    if command.startswith('@') and ' ' not in command:
        aliases = sorted(_mention_alias_map(data).keys())
        matches = ['@' + a for a in aliases if ('@' + a).startswith(command.lower())]
        if len(matches) == 1:
            return matches[0] + ' ', ''
        if matches:
            return command, 'mentions: ' + ', '.join(matches[:8])
        return command, ''
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
    if head in ('/send', '/compose') and rest and ' ' not in rest:
        ids = _agent_ids(data) + ['broadcast', 'stanley', 'openclaw', 'main']
        matches = [a for a in ids if a.startswith(rest)]
        if len(matches) == 1:
            return f'{head} {matches[0]} ', ''
        if matches:
            return command, 'targets: ' + ', '.join(matches)
    if head == '/filter' and rest:
        matches = [f for f in EVENT_FILTERS if f.startswith(rest)]
        if len(matches) == 1:
            return f'/filter {matches[0]}', ''
        if matches:
            return command, 'filters: ' + ', '.join(sorted(matches))
    return command, ''


def _resolve_target(target: str) -> str:
    lowered = target.strip().lower()
    aliases = {
        'stanley': 'openclaw-main',
        'openclaw': 'openclaw-main',
        'main': 'openclaw-main',
        'hermes': 'hermes',
        'goose': 'goose',
        'broadcast': 'broadcast',
    }
    return aliases.get(lowered, target)


def _open_recent_by_index(data: dict, idx: int, base: str) -> tuple[str, dict]:
    conversations = data.get('recent', {}).get('conversations', [])
    if idx < 1 or idx > len(conversations):
        return 'history error', {'conversation_id': '', 'messages': [], 'deliveries': [], 'dead_letters': [{'adapter_id': 'history', 'reason': f'No conversation at index {idx}'}]}
    conversation_id = conversations[idx - 1].get('conversation_id', '')
    return f'history {conversation_id}', _handle_history(base, conversation_id)


def _init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # dark green borders
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)  # green text on dark background
    curses.init_pair(4, curses.COLOR_GREEN, -1)  # logo


def _main(stdscr) -> None:
    prefs = load_preferences()
    state = {
        'view': prefs.get('default_view', 'dashboard'),
        'event_filter': prefs.get('event_filter', 'all'),
        'refresh_seconds': prefs.get('refresh_seconds', 3),
        'last_target': prefs.get('last_target', 'hermes'),
        'command_result': None,
    }
    _init_colors()
    curses.curs_set(1)
    stdscr.keypad(True)
    stdscr.timeout(250)
    base = DEFAULT_BASE
    command = ''
    hint = ''
    previous_sigint = _install_sigint_handler()
    data = _fetch_dashboard(base)
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
                    data = {'health': {'ok': False, 'timestamp': '', 'error': str(exc)}, 'agents': {'agents': []}, 'recent': {'conversations': []}, 'deliveries': {'deliveries': []}, 'dead_letters': {'dead_letters': []}}
                last_refresh = now
            events = list(stream.events)
            typing_names = stream.get_typing_names()
            connected_count = len(data.get('agents', {}).get('agents', []))
            dead_count = len(data.get('dead_letters', {}).get('dead_letters', []))
            left_lines = _render_left(state, data, events)
            right_lines = _render_right(state, events, data)
            _draw(stdscr, left_lines, right_lines, command, hint, state, typing_names, connected_count, dead_count)
            if _SIGINT_STATE['count'] == 1 and time.time() - _SIGINT_STATE['last'] <= 2.0:
                hint = 'type Ctrl-C again to quit'
            elif _SIGINT_STATE['count'] == 1:
                _SIGINT_STATE['count'] = 0
                hint = ''
            try:
                ch = stdscr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                break
            if ch in ('\n', '\r'):
                cmd = _normalize_command(command.strip())
                command = ''
                hint = ''
                if cmd in ('/quit', '/exit'):
                    break
                if cmd in ('/dashboard', '/refresh', ''):
                    state['view'] = 'dashboard'
                    state['command_result'] = None
                    last_refresh = 0
                    continue
                if cmd == '/events':
                    state['view'] = 'events'
                    state['command_result'] = None
                    continue
                if cmd == '/conversations':
                    state['view'] = 'conversations'
                    state['command_result'] = None
                    continue
                if cmd == '/deadletters':
                    state['view'] = 'deadletters'
                    state['command_result'] = None
                    continue
                if cmd == '/adapters':
                    state['view'] = 'adapters'
                    state['command_result'] = None
                    continue
                if cmd == '/help':
                    state['view'] = 'help'
                    state['command_result'] = None
                    continue
                if cmd.startswith('/filter '):
                    value = cmd.split(' ', 1)[1].strip()
                    if value in EVENT_FILTERS:
                        state['event_filter'] = value
                        save_preferences(state)
                        hint = f'event filter set to {value}'
                    else:
                        hint = f'unknown filter: {value}'
                    continue
                if cmd.startswith('/send '):
                    parts = cmd.split(' ', 2)
                    if len(parts) >= 3:
                        target, body = _resolve_target(parts[1]), parts[2]
                        state['last_target'] = target
                        save_preferences(state)
                        try:
                            result = _handle_send(base, target, body)
                            state['command_result'] = (f'send -> {target}', result)
                            state['view'] = 'command-result'
                        except Exception as exc:  # noqa: BLE001
                            state['command_result'] = ('send error', {'message': {'source': 'synkraken-tui', 'target': target}, 'deliveries': [], 'dead_letters': [{'adapter_id': target, 'reason': str(exc)}]})
                            state['view'] = 'command-result'
                    continue
                if cmd.startswith('/broadcast '):
                    body = cmd.split(' ', 1)[1]
                    try:
                        result = _handle_send(base, 'broadcast', body)
                        state['command_result'] = ('broadcast', result)
                        state['view'] = 'command-result'
                    except Exception as exc:  # noqa: BLE001
                        state['command_result'] = ('broadcast error', {'message': {'source': 'synkraken-tui', 'target': 'broadcast'}, 'deliveries': [], 'dead_letters': [{'adapter_id': 'broadcast', 'reason': str(exc)}]})
                        state['view'] = 'command-result'
                    continue
                if cmd.startswith('/history '):
                    conversation_id = cmd.split(' ', 1)[1].strip()
                    try:
                        result = _handle_history(base, conversation_id)
                        state['command_result'] = (f'history {conversation_id}', result)
                        state['view'] = 'command-result'
                    except Exception as exc:  # noqa: BLE001
                        state['command_result'] = (f'history {conversation_id}', {'conversation_id': conversation_id, 'messages': [], 'deliveries': [], 'dead_letters': [{'adapter_id': 'history', 'reason': str(exc)}]})
                        state['view'] = 'command-result'
                    continue
                if cmd.startswith('/open '):
                    arg = cmd.split(' ', 1)[1].strip()
                    if arg.isdigit():
                        try:
                            state['command_result'] = _open_recent_by_index(data, int(arg), base)
                            state['view'] = 'command-result'
                        except Exception as exc:  # noqa: BLE001
                            state['command_result'] = ('history error', {'conversation_id': '', 'messages': [], 'deliveries': [], 'dead_letters': [{'adapter_id': 'history', 'reason': str(exc)}]})
                            state['view'] = 'command-result'
                    continue
                if cmd == '/compose':
                    command = f'/send {state["last_target"]} '
                    hint = 'compose mode: complete target/message, then press Enter'
                    continue
                mention_result = _parse_mentions(cmd, data)
                if mention_result is not None:
                    targets, body = mention_result
                    if targets == ['broadcast']:
                        try:
                            result = _handle_send(base, 'broadcast', body)
                            state['command_result'] = ('broadcast', result)
                            state['view'] = 'command-result'
                        except Exception as exc:  # noqa: BLE001
                            state['command_result'] = ('broadcast error', {'message': {'source': 'synkraken-tui', 'target': 'broadcast'}, 'deliveries': [], 'dead_letters': [{'adapter_id': 'broadcast', 'reason': str(exc)}]})
                            state['view'] = 'command-result'
                    else:
                        combined = {'message': {'source': 'synkraken-tui', 'target': 'multi', 'conversation_id': None}, 'deliveries': [], 'dead_letters': []}
                        for t in targets:
                            try:
                                result = _handle_send(base, t, body)
                                if combined['message']['conversation_id'] is None:
                                    combined['message'] = result.get('message', combined['message'])
                                combined['deliveries'].extend(result.get('deliveries', []))
                                combined['dead_letters'].extend(result.get('dead_letters', []))
                            except Exception as exc:  # noqa: BLE001
                                combined['dead_letters'].append({'adapter_id': t, 'reason': str(exc)})
                        state['command_result'] = ('mentions', combined)
                        state['view'] = 'command-result'
                    continue
                state['command_result'] = ('unknown command', {'message': {'source': 'synkraken-tui', 'target': 'unknown'}, 'deliveries': [], 'dead_letters': [{'adapter_id': 'unknown', 'reason': f'Unknown command: {cmd}'}]})
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
