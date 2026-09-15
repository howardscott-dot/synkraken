from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import re
import secrets
import sys
from threading import RLock
import time
from urllib.parse import urlencode

from .models import new_id, utc_now_iso
from .providers import ProviderClient


HOST_TOOLS = ['workspace_bots', 'create_bot', 'configure_bot', 'request_connection', 'request_secret',
              'run_diagnostics', 'workspace_health', 'pending_approvals', 'resolve_approval']
TEAM_BOTS = ('Chief of Staff', 'PA', 'Account Manager', 'Researcher', 'Writer', 'PM')
TEAM_WORKERS = tuple(name for name in TEAM_BOTS if name != 'Chief of Staff')
CHIEF_DELEGATION_GRANT = 'chief_delegation'
MEMORY_PROBE_KEY = 'diagnostics.probe'
BRIDGE_EVENTS = {'api_connection_reestablished', 'ui_bridge_ready'}
PRESETS = {
    'openrouter': {'name': 'OpenRouter', 'protocol': 'openai_compatible', 'base_url': 'https://openrouter.ai/api/v1'},
    'openai': {'name': 'OpenAI', 'protocol': 'openai_compatible', 'base_url': 'https://api.openai.com/v1'},
    'anthropic': {'name': 'Anthropic', 'protocol': 'anthropic', 'base_url': 'https://api.anthropic.com/v1'},
    'minimax': {'name': 'MiniMax', 'protocol': 'anthropic', 'base_url': 'https://api.minimax.io/anthropic/v1'},
    'grok': {'name': 'Grok', 'protocol': 'openai_compatible', 'base_url': 'https://api.x.ai/v1'},
    'ollama': {'name': 'Ollama', 'protocol': 'openai_compatible', 'base_url': 'http://localhost:11434/v1'},
}


class ChatWorkspace:
    def __init__(self, bots) -> None:
        self.bots = bots
        self.storage = bots.storage
        self.lock = RLock()
        self.oauth = {}

    def state(self) -> dict:
        value = self.storage.workspace_value('chat')
        return {**value, 'ready': bool(value.get('home_bot_id')), 'cloud_sync': False,
                'providers': self.bots.providers.list(), 'presets': list(PRESETS)}

    def capabilities(self) -> dict:
        return {"skills": [{"id": key, "name": path.parent.name}
                           for key, path in self.bots.engine.skills().items()],
                "mcp_available": False}

    def setup(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError('Invalid setup request')
        with self.lock:
            current = self.storage.workspace_value('chat')
            action = payload.get('action')
            if action == 'restart':
                if current.get('home_bot_id'):
                    raise ValueError('Setup is already complete')
                current = {}
                self.oauth.clear()
            elif action == 'select':
                kind = payload.get('provider')
                if kind not in PRESETS:
                    raise ValueError('Choose a supported provider')
                if current.get('home_bot_id'):
                    raise ValueError('Initial setup is complete; request a connection in chat')
                current.update(provider_kind=kind, step='model')
                current.pop('model', None)
            elif action == 'model':
                model = payload.get('model')
                if not isinstance(model, str) or not model.strip() or len(model) > 200:
                    raise ValueError('Enter the model name you want to use')
                if not current.get('provider_kind') or current.get('home_bot_id'):
                    raise ValueError('Choose a provider first')
                current.update(model=model.strip(), step='connect')
            elif action == 'connect':
                if current.get('home_bot_id'):
                    return self.state()
                if not current.get('model'):
                    raise ValueError('Choose a default model first')
                provider_id = payload.get('provider_id')
                if provider_id:
                    provider = self.bots.providers.get(provider_id)
                else:
                    fields = dict(PRESETS[current['provider_kind']])
                    if current['provider_kind'] != 'ollama' and not payload.get('api_key'):
                        raise ValueError('Sign in or use the secure key card')
                    fields['api_key'] = payload.get('api_key', '')
                    provider = self.bots.providers.save(fields)
                self.bots.providers.client(provider['provider_id']).complete(current['model'],
                    [{'role': 'user', 'content': 'Reply with OK.'}], [], 30)
                home = self.bots.save({'name': 'SynKraken', 'job': '', 'instructions': '', 'notes': '',
                    'provider_id': provider['provider_id'], 'model': current['model'], 'tools': HOST_TOOLS})
                current.update(home_bot_id=home['bot_id'], default_provider_id=provider['provider_id'],
                               default_model=current['model'], step='done')
            elif action == 'use_existing':
                if current.get('home_bot_id'):
                    return self.state()
                provider = self.bots.providers.get(payload.get('provider_id', ''))
                model = payload.get('model', '')
                if not isinstance(model, str) or not model.strip() or len(model) > 200:
                    raise ValueError('Choose a default model')
                home = self.bots.save({'name': 'SynKraken', 'job': '', 'provider_id': provider['provider_id'],
                                      'model': model.strip(), 'tools': HOST_TOOLS})
                current.update(home_bot_id=home['bot_id'], default_provider_id=provider['provider_id'],
                               default_model=model.strip(), step='done')
            else:
                raise ValueError('Unknown setup action')
            self.storage.save_workspace_value('chat', current)
            return self.state()

    def start_oauth(self, card_id: str = '') -> dict:
        with self.lock:
            now = time.monotonic()
            self.oauth = {key: value for key, value in self.oauth.items() if value['expires'] > now}
            if len(self.oauth) >= 8:
                raise ValueError('Too many pending sign-ins; wait for an earlier one to expire')
            if card_id:
                card = self.storage.get_chat_card(card_id)
                if not card or card['kind'] != 'connection' or card['provider'] != 'openrouter' or card['status'] != 'pending':
                    raise ValueError('Invalid connection card')
            elif self.storage.workspace_value('chat').get('provider_kind') != 'openrouter' or not self.storage.workspace_value('chat').get('model'):
                raise ValueError('Choose OpenRouter first')
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            token = secrets.token_urlsafe(32)
            self.oauth[token] = {'verifier': verifier, 'expires': now + 600, 'card_id': card_id,
                                 'model': self.storage.workspace_value('chat').get('model')}
            return {'flow_id': token, 'authorization_url': 'https://openrouter.ai/auth?' + urlencode({
                'code_challenge': challenge, 'code_challenge_method': 'S256', 'key_label': 'SynKraken'}),
                'expires_in': 600}

    def finish_oauth(self, flow_id: str, code: str) -> dict:
        if not isinstance(code, str) or not code.strip() or len(code) > 4096:
            raise ValueError('Enter the one-time authorization code')
        with self.lock:
            flow = self.oauth.pop(flow_id, None)
            if not flow or flow['expires'] <= time.monotonic():
                raise ValueError('Sign-in expired or already used. Start again')
            if not flow['card_id']:
                current = self.storage.workspace_value('chat')
                if current.get('provider_kind') != 'openrouter' or current.get('model') != flow['model'] or current.get('home_bot_id'):
                    raise ValueError('Setup changed. Start sign-in again for the selected model')
            result = ProviderClient(PRESETS['openrouter'], '').request('/auth/keys', {
                'code': code.strip(), 'code_verifier': flow['verifier'], 'code_challenge_method': 'S256'}, 30)
            key = result.get('key')
            if not isinstance(key, str) or not key:
                raise ValueError('Provider did not return a valid credential')
            if flow['card_id']:
                return self.resolve_card(flow['card_id'], {'api_key': key})
            return self.setup({'action': 'connect', 'api_key': key})

    def card(self, bot_id: str, kind: str, **fields) -> dict:
        bot = next((item for item in self.storage.list_bots() if item.get('bot_id') == bot_id), None)
        if bot and not fields.get('target_name'):
            fields['target_name'] = bot.get('name') or ''
        if bot and not fields.get('target_id') and kind in {'capability', 'browser_access', 'credential', 'connection'}:
            fields['target_id'] = bot_id
        card = {'card_id': new_id(), 'bot_id': bot_id, 'kind': kind, 'status': 'pending',
                'created_at': utc_now_iso(), **fields}
        self.storage.save_chat_card(card)
        return {'card_id': card['card_id'], 'status': 'waiting_for_user',
                'message': 'The input card is in the conversation. Do not ask for secrets in chat.'}

    def card_is_renderable(self, card: dict) -> bool:
        if not card or card.get('probe') or not card.get('card_id') or not card.get('kind'):
            return False
        required = {
            'capability': ('capability', 'reason'),
            'browser_access': ('origin',),
            'bot_change': ('target_name', 'changes'),
            'connection': ('provider',),
            'credential': ('service', 'purpose'),
        }.get(card['kind'], ())
        return all(card.get(key) not in (None, '', []) for key in required)

    def visible_cards(self, bot_id: str) -> list[dict]:
        waiting = self.storage.waiting_bot_run(bot_id)
        by_id = {}
        for card in self.storage.all_chat_cards():
            if not card.get('card_id') or card.get('probe'):
                continue
            mine = card.get('bot_id') == bot_id
            targeted = card.get('target_id') == bot_id
            waiting_match = bool(waiting and card.get('run_id') == waiting.get('run_id'))
            if mine or targeted or waiting_match:
                by_id[card['card_id']] = card
        cards = list(by_id.values())
        pending = [card for card in cards if card.get('status') == 'pending']
        done = [card for card in cards if card.get('status') != 'pending']
        done.sort(key=lambda card: (card.get('created_at') or '', card.get('card_id') or ''))
        merged = pending + done[-50:]
        merged.sort(key=lambda card: (card.get('created_at') or '', card.get('card_id') or ''))
        return merged

    def public_card(self, card: dict) -> dict:
        run = self.storage.get_bot_run(card['run_id']) if card.get('run_id') else None
        bot = next((item for item in self.storage.list_bots() if item.get('bot_id') == card.get('bot_id')), None)
        target = next((item for item in self.storage.list_bots() if item.get('bot_id') == card.get('target_id')), None)
        kind = card.get('kind')
        capability = card.get('capability') or ''
        if kind == 'browser_access':
            capability = card.get('origin') or capability
        elif kind == 'bot_change' and card.get('grant') == CHIEF_DELEGATION_GRANT:
            capability = 'delegation'
        elif kind == 'connection':
            capability = card.get('provider') or capability
        elif kind == 'credential':
            capability = card.get('service') or capability
        return {
            'card_id': card.get('card_id'),
            'kind': kind,
            'status': card.get('status'),
            'bot_name': (bot or {}).get('name') or '',
            'target_name': card.get('target_name') or (target or {}).get('name') or '',
            'capability': capability,
            'reason': safe_detail(card.get('reason') or card.get('purpose') or ''),
            'created_at': card.get('created_at') or '',
            'run_id': card.get('run_id') or '',
            'run_status': (run or {}).get('status') or '',
            'resumes_paused_run': bool(run and run.get('status') == 'waiting_for_user'),
            'renderable': self.card_is_renderable(card),
        }

    def pending_approvals(self) -> dict:
        pending = [card for card in self.storage.all_chat_cards()
                   if card.get('status') == 'pending' and not card.get('probe')]
        cards = [self.public_card(card) for card in pending]
        return {'pending': cards, 'count': len(cards)}

    def format_pending_approvals(self, result: dict) -> str:
        cards = result.get('pending') or []
        if not cards:
            return 'Pending approvals\nNone.'
        lines = [f'Pending approvals ({len(cards)})']
        for card in cards:
            resume = 'resumes paused run' if card.get('resumes_paused_run') else 'no paused run'
            run_status = card.get('run_status') or 'no run'
            lines.append(
                f"- type {card.get('kind')} · bot {card.get('bot_name') or 'unknown'} · "
                f"target {card.get('target_name') or card.get('bot_name') or ''} · "
                f"capability {card.get('capability') or 'n/a'} · "
                f"{card.get('reason') or 'no reason'} · created {card.get('created_at') or 'unknown'} · "
                f"run {run_status} · {resume}. Approve or cancel."
            )
        return '\n'.join(lines)

    def format_resolve_approval(self, result: dict) -> str:
        if result.get('resolved'):
            card = result.get('card') or {}
            run = result.get('run') or {}
            action = 'Approved' if (card.get('status') or '') not in {'dismissed', 'cancelled'} else 'Cancelled'
            resume = 'Original run resumed' if run.get('run_id') else 'No paused run to resume'
            return (
                f"{action} the matching {card.get('kind') or 'approval'} card for "
                f"{card.get('target_name') or card.get('bot_name') or 'the bot'}. "
                f"Card status: {card.get('status') or 'unknown'}. {resume}."
            )
        matches = result.get('matches') or []
        if not matches:
            return 'No matching pending card. Choose from the visible cards. Nothing was changed.'
        lines = ['Multiple cards matched. Choose from the visible cards. Nothing was changed.']
        for card in matches:
            lines.append(
                f"- {card.get('kind')} · {card.get('bot_name') or 'bot'} · "
                f"{card.get('capability') or card.get('target_name') or ''}"
            )
        return '\n'.join(lines)

    def _approval_name_key(self, value: str) -> str:
        return re.sub(r'[^\w]+$', '', (value or '').strip(), flags=re.U).casefold()

    def resolve_approval(self, bot_name: str, kind: str, action: str = 'approve') -> dict:
        bot_name = (bot_name or '').strip()
        kind = (kind or '').strip().lower()
        action = (action or 'approve').strip().lower()
        if action not in {'approve', 'cancel'}:
            raise ValueError('Choose approve or cancel')
        pending = [card for card in self.storage.all_chat_cards()
                   if card.get('status') == 'pending' and not card.get('probe')]
        kind_aliases = {
            'browser': ('browser_access', 'capability'),
            'origin': ('browser_access',),
            'capability': ('capability',),
            'delegation': ('bot_change',),
            'connection': ('connection',),
            'credential': ('credential',),
            'bot_change': ('bot_change',),
        }
        wanted_kinds = kind_aliases.get(kind, (kind,) if kind else None)
        wanted_name = self._approval_name_key(bot_name)
        matches = []
        for card in pending:
            bot = next((item for item in self.storage.list_bots() if item.get('bot_id') == card.get('bot_id')), None)
            target = next((item for item in self.storage.list_bots() if item.get('bot_id') == card.get('target_id')), None)
            names = {(bot or {}).get('name'), (target or {}).get('name'), card.get('target_name')}
            if wanted_name and not any(self._approval_name_key(name) == wanted_name for name in names if name):
                continue
            if wanted_kinds and card.get('kind') not in wanted_kinds:
                continue
            if kind == 'browser' and card.get('kind') == 'capability' and card.get('capability') != 'browser':
                continue
            if kind == 'delegation' and card.get('grant') not in {CHIEF_DELEGATION_GRANT, None}:
                if card.get('grant') and card.get('grant') != CHIEF_DELEGATION_GRANT:
                    continue
            matches.append(card)
        if kind == 'delegation':
            matches = [card for card in matches if card.get('kind') == 'bot_change']
        public = [self.public_card(card) for card in matches]
        if len(matches) != 1:
            return {'resolved': False, 'ambiguous': len(matches) != 1, 'matches': public,
                    'message': 'Choose the matching visible card. Nothing was changed.'}
        payload = {'approve': True} if action == 'approve' else {'cancel': True}
        result = self.resolve_card(matches[0]['card_id'], payload)
        return {'resolved': True, 'ambiguous': False, 'card': self.public_card(result['card']),
                'run': result.get('run'), 'status': result.get('status') or result['card'].get('status')}

    def request_capability(self, bot: dict, args: dict, run_id: str) -> dict:
        groups = {
            'browser': ['browser_open', 'browser_read', 'browser_click', 'browser_type', 'browser_scroll'],
            'memory': ['memory_read', 'memory_write'],
            'files': ['workspace_list', 'read_file', 'write_file'],
            'skills': ['skills_list', 'skill_read'],
        }
        capability = args['capability']
        if capability not in groups:
            raise ValueError('Choose browser, memory, files or skills')
        if set(groups[capability]).issubset(bot['tools']):
            return {'enabled': True, 'tools': groups[capability]}
        with self.lock:
            existing = next((c for c in self.storage.chat_cards(bot['bot_id'])
                             if c['kind'] == 'capability' and c['status'] == 'pending'
                             and c['capability'] == capability and not c.get('probe')), None)
            if existing:
                if run_id and existing.get('run_id') != run_id:
                    existing = {**existing, 'run_id': run_id}
                    self.storage.save_chat_card(existing)
                return {'card_id': existing['card_id'], 'status': 'waiting_for_user'}
            return self.card(bot['bot_id'], 'capability', capability=capability,
                             reason=args['reason'][:500], tools=groups[capability], run_id=run_id,
                             target_id=bot['bot_id'], target_name=bot['name'])

    def host_tool(self, bot: dict, name: str, args: dict, run_id: str) -> dict:
        current = self.storage.workspace_value('chat')
        if current.get('home_bot_id') != bot['bot_id']:
            raise ValueError('Workspace management is available only in the entry conversation')
        if name == 'workspace_bots':
            return {'bots': [{'bot_id': item['bot_id'], 'name': item['name'], 'job': item['job'],
                             'provider_id': item.get('provider_id'), 'model': item.get('model')}
                            for item in self.storage.list_bots()],
                    'providers': self.bots.providers.list()}
        if name == 'create_bot':
            fingerprint = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
            receipt_key = 'create:' + run_id + ':' + fingerprint
            with self.lock:
                receipt = self.storage.workspace_value(receipt_key)
                if receipt:
                    return receipt
                created = self.bots.save({'name': args['name'], 'job': args['job'], 'instructions': args['instructions'],
                    'provider_id': current['default_provider_id'], 'model': current['default_model'], 'tools': []})
                receipt = {'bot_id': created['bot_id'], 'name': created['name'], 'created': True}
                self.storage.save_workspace_value(receipt_key, receipt)
                self._ensure_chief_delegation_card(run_id)
                return receipt
        if name == 'configure_bot':
            target = self.bots.get(args['bot_id'])
            changes = {key: value for key, value in args.items() if key != 'bot_id' and value}
            if 'delegate_to' in changes:
                changes['delegate_to'] = [value.strip() for value in changes['delegate_to'].split(',') if value.strip()]
                for target_id in changes['delegate_to']:
                    self.bots.get(target_id)
            if 'tools' in changes:
                from .bot_engine import TOOL_NAMES
                changes['tools'] = [item.strip() for item in changes['tools'].split(',') if item.strip()]
                if set(changes['tools']) - (TOOL_NAMES - set(HOST_TOOLS)):
                    raise ValueError('Unknown or reserved capability')
            if target['bot_id'] == current['home_bot_id'] and 'tools' in changes:
                changes['tools'] = list(dict.fromkeys(HOST_TOOLS + changes['tools']))
            if not changes:
                return {'bot_id': target['bot_id'], 'unchanged': True}
            return self.card(bot['bot_id'], 'bot_change', target_id=target['bot_id'],
                             target_name=target['name'], changes=changes, run_id=run_id)
        if name == 'request_connection':
            if args['provider'] not in PRESETS:
                raise ValueError('Supported connections: ' + ', '.join(PRESETS))
            return self.card(bot['bot_id'], 'connection', provider=args['provider'], run_id=run_id)
        if name == 'request_secret':
            return self.card(bot['bot_id'], 'credential', service=args['service'][:100],
                             purpose=args['purpose'][:500], run_id=run_id)
        if name == 'workspace_health':
            return self.workspace_health()
        if name == 'run_diagnostics':
            return self.run_diagnostics(args.get('scope', 'all'))
        if name == 'pending_approvals':
            return self.pending_approvals()
        if name == 'resolve_approval':
            return self.resolve_approval(args.get('bot_name', ''), args.get('kind', ''), args.get('action', 'approve'))
        raise ValueError('Unknown workspace action')

    def note_bridge(self, event: str) -> dict:
        if event not in BRIDGE_EVENTS:
            raise ValueError('Unknown bridge event')
        print('synkraken: ' + event, file=sys.stderr, flush=True)
        return {'logged': True, 'event': event}

    def workspace_health(self) -> dict:
        bots = self.bots.list()
        providers = self.bots.providers.list()
        pending = sum(1 for card in self.storage.all_chat_cards()
                      if card.get('status') == 'pending' and not card.get('probe'))
        last = self.storage.workspace_value('chat').get('last_diagnostics')
        return {
            'provider_status': [{'name': item.get('name'), 'enabled': bool(item.get('enabled')),
                                 'credential_ready': bool(item.get('credential_ready'))} for item in providers],
            'bot_count': len(bots),
            'bots': [{'name': bot['name'], 'model': bot.get('model', ''),
                      'provider': next((p.get('name') for p in providers if p.get('provider_id') == bot.get('provider_id')), '')}
                     for bot in bots],
            'pending_cards': pending,
            'last_diagnostics': last,
        }

    def format_health(self, health: dict) -> str:
        providers = health.get('provider_status') or []
        ready = next((item['name'] for item in providers if item.get('credential_ready')), 'none ready')
        last = health.get('last_diagnostics') or {}
        last_line = 'none'
        if last:
            failed = ', '.join(last.get('failed') or []) or 'none'
            last_line = ('pass' if last.get('ok') else 'fail') + ' · failed: ' + failed
        lines = [
            'Workspace health',
            f"Provider: {ready}",
            f"Bots: {health.get('bot_count', 0)}",
        ]
        for bot in health.get('bots') or []:
            lines.append(f"{bot.get('name')}: {bot.get('model') or 'unassigned'}")
        lines.append(f"Pending approval cards: {health.get('pending_cards', 0)}")
        lines.append(f"Last diagnostics: {last_line}")
        return '\n'.join(lines)

    def format_diagnostics(self, result: dict) -> str:
        lines = ['SynKraken diagnostics']
        for check in result.get('checks') or []:
            status = check.get('status') or ('pass' if check.get('ok') is True else 'fail')
            mark = {'pass': 'Pass', 'fail': 'Fail', 'skip': 'Skip'}.get(status, status)
            lines.append(f"{mark} · {check.get('label')}: {check.get('detail')}")
        if result.get('scope') == 'failed' and not result.get('checks'):
            lines.append('No failed checks to rerun.')
        elif not result.get('ok'):
            lines.append('Ask to rerun failed diagnostics to retry only the failed checks.')
        return '\n'.join(lines)

    def run_diagnostics(self, scope: str = 'all') -> dict:
        scope = scope if scope in {'all', 'failed'} else 'all'
        current = self.storage.workspace_value('chat')
        previous = current.get('last_diagnostics') or {}
        run_id = new_id()
        stamp = utc_now_iso()
        self._diag_ctx = {
            'bots': list(self.storage.list_bots()),
            'providers': list(self.bots.providers.list()),
            'home_bot_id': current.get('home_bot_id'),
            'run_id': run_id,
            'timestamp': stamp,
        }
        try:
            wanted = None
            if scope == 'failed':
                wanted = [item for item in previous.get('failed') or [] if item in DIAGNOSTIC_CHECKS]
                if not wanted:
                    result = {
                        'scope': 'failed', 'checks': [], 'ok': True, 'completed_at': stamp,
                        'run_id': run_id, 'failed': [],
                    }
                    return result
            checks = []
            for check_id, (label, runner) in DIAGNOSTIC_CHECKS.items():
                if wanted is not None and check_id not in wanted:
                    continue
                try:
                    check = runner(self)
                except Exception as exc:
                    check = self._check(check_id, label, False, exc)
                check['id'] = check_id
                check['label'] = check.get('label') or label
                check['detail'] = safe_detail(check.get('detail', ''))
                check['timestamp'] = check.get('timestamp') or stamp
                check['run_id'] = check.get('run_id') or run_id
                if check.get('status') == 'skip':
                    check['ok'] = False
                    check['status'] = 'skip'
                else:
                    check['ok'] = check.get('ok') is True
                    check['status'] = 'pass' if check['ok'] else 'fail'
                checks.append(check)
            failed = [item['id'] for item in checks if item.get('status') == 'fail']
            if wanted is not None:
                failed = [item for item in wanted if item in failed]
            result = {
                'scope': scope, 'checks': checks, 'ok': not failed,
                'completed_at': stamp, 'run_id': run_id, 'failed': failed,
            }
            self.storage.save_workspace_value('chat', {**current, 'last_diagnostics': {
                'ok': result['ok'], 'completed_at': result['completed_at'], 'failed': failed,
                'run_id': run_id, 'scope': scope, 'checks': checks}})
            return result
        finally:
            self._diag_ctx = None

    def _saved_bots(self) -> list[dict]:
        ctx = getattr(self, '_diag_ctx', None)
        if ctx:
            return list(ctx['bots'])
        return list(self.storage.list_bots())

    def _saved_providers(self) -> list[dict]:
        ctx = getattr(self, '_diag_ctx', None)
        if ctx:
            return list(ctx['providers'])
        return list(self.bots.providers.list())

    def _diag_run_meta(self) -> tuple[str, str]:
        ctx = getattr(self, '_diag_ctx', None) or {}
        return ctx.get('run_id') or new_id(), ctx.get('timestamp') or utc_now_iso()

    def _home(self) -> dict | None:
        home_id = (getattr(self, '_diag_ctx', None) or {}).get('home_bot_id') or self.storage.workspace_value('chat').get('home_bot_id')
        return next((bot for bot in self._saved_bots() if bot.get('bot_id') == home_id), None)

    def _named(self, name: str) -> dict | None:
        return next((bot for bot in self._saved_bots() if bot.get('name') == name), None)

    def _probe_bot(self) -> dict | None:
        return self._named('Researcher') or next(
            (bot for bot in self._saved_bots() if bot.get('name') in TEAM_BOTS), None) or self._home()

    def _check(self, check_id: str, label: str, ok: bool, detail: str, *, status: str | None = None) -> dict:
        run_id, stamp = self._diag_run_meta()
        if status == 'skip':
            mark = 'skip'
            passed = False
        else:
            passed = bool(ok)
            mark = 'pass' if passed else 'fail'
        return {
            'id': check_id, 'label': label, 'ok': passed,
            'status': mark,
            'detail': safe_detail(detail),
            'timestamp': stamp, 'run_id': run_id,
        }

    def _diag_provider(self) -> dict:
        home = self._home()
        providers = self._saved_providers()
        provider = next((item for item in providers if home and item.get('provider_id') == home.get('provider_id')), None)
        ok = bool(provider and provider.get('credential_ready') and home and home.get('model'))
        detail = f"{(provider or {}).get('name') or 'none'} · {(home or {}).get('model') or 'no host model'}"
        return self._check('provider', 'Active provider and model', ok, detail)

    def _diag_roundtrip(self) -> dict:
        home = self._home()
        if not home or not home.get('provider_id') or not home.get('model'):
            return self._check('provider_roundtrip', 'Provider round trip', False, 'Host has no provider/model')
        try:
            self.bots.providers.client(home['provider_id']).complete(
                home['model'], [{'role': 'user', 'content': 'Reply with OK.'}], [], 20)
            return self._check('provider_roundtrip', 'Provider round trip', True, 'Provider round trip succeeded')
        except Exception as exc:
            return self._check('provider_roundtrip', 'Provider round trip', False, exc)

    def _diag_roster(self) -> dict:
        names = [bot.get('name') for bot in self._saved_bots()]
        dupes = sorted({name for name in names if names.count(name) > 1})
        missing = [name for name in TEAM_BOTS if name not in names]
        home = self._home()
        host_ok = bool(home and home['name'] == 'SynKraken')
        ok = host_ok and not dupes and not missing
        parts = [f'{len(names)} bots']
        if not host_ok:
            parts.append('host missing')
        if missing:
            parts.append('missing ' + ', '.join(missing))
        if dupes:
            parts.append('duplicates ' + ', '.join(dupes))
        return self._check('roster', 'Roster integrity', ok, '; '.join(parts))

    def _diag_minimax(self) -> dict:
        records = [bot for bot in self._saved_bots() if bot.get('name') in TEAM_BOTS]
        present = {bot.get('name') for bot in records}
        missing = [name for name in TEAM_BOTS if name not in present]
        wrong = [f"{bot.get('name')}={bot.get('model') or 'unassigned'}"
                 for bot in records if bot.get('model') != 'MiniMax-M3']
        ok = not missing and not wrong
        if missing:
            detail = 'missing ' + ', '.join(missing)
        elif wrong:
            detail = 'not MiniMax-M3: ' + ', '.join(wrong)
        else:
            detail = 'all six team bots use MiniMax-M3'
        return self._check('minimax_assignment', 'MiniMax assignment', ok, detail)

    def _team_workers(self) -> list[dict]:
        return [bot for bot in self._saved_bots() if bot.get('name') in TEAM_WORKERS]

    def _team_complete(self) -> bool:
        names = {bot['name'] for bot in self._saved_bots()}
        return all(name in names for name in TEAM_BOTS)

    def _chief_delegation_changes(self) -> dict | None:
        if not self._team_complete():
            return None
        chief = self._named('Chief of Staff')
        if not chief:
            return None
        workers = self._team_workers()
        tools = [name for name in (chief.get('tools') or []) if name not in HOST_TOOLS]
        if 'bots_list' not in tools:
            tools.append('bots_list')
        if 'delegate_bot' not in tools:
            tools.append('delegate_bot')
        delegate_to = list(chief.get('delegate_to') or [])
        for worker in workers:
            if worker['bot_id'] not in delegate_to:
                delegate_to.append(worker['bot_id'])
        needed = (
            'delegate_bot' not in (chief.get('tools') or [])
            or 'bots_list' not in (chief.get('tools') or [])
            or any(worker['bot_id'] not in (chief.get('delegate_to') or []) for worker in workers)
        )
        if not needed:
            return None
        return {'tools': tools, 'delegate_to': delegate_to}

    def _chief_delegation_granted(self) -> bool:
        chief = self._named('Chief of Staff')
        if not chief or not self._team_complete():
            return False
        tools = chief.get('tools') or []
        allowed = set(chief.get('delegate_to') or [])
        workers = self._team_workers()
        return ('delegate_bot' in tools and 'bots_list' in tools
                and bool(workers) and all(worker['bot_id'] in allowed for worker in workers))

    def _pending_chief_delegation_card(self) -> dict | None:
        home = self._home()
        chief = self._named('Chief of Staff')
        if not home or not chief:
            return None
        return next((card for card in self.storage.chat_cards(home['bot_id'])
                     if card.get('status') == 'pending' and card.get('kind') == 'bot_change'
                     and card.get('grant') == CHIEF_DELEGATION_GRANT
                     and card.get('target_id') == chief['bot_id']
                     and not card.get('probe')), None)

    def _dismiss_applied_chief_delegation_cards(self) -> None:
        home = self._home()
        if not home or not self._chief_delegation_granted():
            return
        for card in self.storage.chat_cards(home['bot_id']):
            if (card.get('status') == 'pending' and card.get('kind') == 'bot_change'
                    and card.get('grant') == CHIEF_DELEGATION_GRANT):
                card = {**card, 'status': 'dismissed'}
                self.storage.save_chat_card(card)

    def _ensure_chief_delegation_card(self, run_id: str) -> dict | None:
        """Propose a host chat card so CoS can delegate. Never auto-grants or adds host tools."""
        changes = self._chief_delegation_changes()
        if not changes:
            self._dismiss_applied_chief_delegation_cards()
            return None
        home = self._home()
        chief = self._named('Chief of Staff')
        if not home or not chief:
            return None
        existing = self._pending_chief_delegation_card()
        if existing:
            if existing.get('changes') != changes:
                existing = {**existing, 'changes': changes, 'run_id': run_id}
                self.storage.save_chat_card(existing)
            return existing
        reason = (
            'Chief of Staff needs bots_list and delegate_bot, allowed to PA, '
            'Account Manager, Researcher, Writer, and PM. Approve to grant. '
            'This does not give workspace management tools.'
        )
        result = self.card(home['bot_id'], 'bot_change', target_id=chief['bot_id'],
                           target_name=chief['name'], changes=changes, run_id=run_id,
                           grant=CHIEF_DELEGATION_GRANT, reason=reason)
        return self.storage.get_chat_card(result['card_id'])

    def _diag_delegation(self) -> dict:
        self._ensure_chief_delegation_card('diagnostics-delegation')
        chief = self._named('Chief of Staff')
        workers = self._team_workers()
        missing_roles = [name for name in TEAM_WORKERS if not self._named(name)]
        if not chief:
            return self._check('delegation', 'Chief of Staff delegation', False, 'Chief of Staff is not in the roster')
        if missing_roles:
            return self._check('delegation', 'Chief of Staff delegation', False,
                               'missing ' + ', '.join(missing_roles))
        allowed = set(chief.get('delegate_to') or [])
        missing = [name for name in TEAM_WORKERS
                   if any(bot['name'] == name and bot['bot_id'] not in allowed for bot in workers)]
        tools = chief.get('tools') or []
        has_tool = 'delegate_bot' in tools
        has_list = 'bots_list' in tools
        ok = bool(workers) and not missing and has_tool and has_list
        pending = self._pending_chief_delegation_card()
        parts = []
        if not has_tool:
            parts.append('delegate_bot is not enabled')
        elif not has_list:
            parts.append('bots_list is not enabled')
        if missing:
            parts.append('not allowed: ' + ', '.join(missing))
        if pending and parts:
            parts.append('approval card is in the host conversation')
        detail = '; '.join(parts) if parts else f'{len(workers)} workers allowed'
        return self._check('delegation', 'Chief of Staff delegation', ok, detail)

    def _diag_delegation_execution(self) -> dict:
        from .bot_engine import RunBudget
        chief_row = self._named('Chief of Staff')
        workers = self._team_workers()
        if not chief_row or not workers:
            return self._check('delegation_execution', 'Chief of Staff delegation execution', False,
                               'configuration incomplete')
        if 'delegate_bot' not in (chief_row.get('tools') or []) or any(
                worker['bot_id'] not in (chief_row.get('delegate_to') or []) for worker in workers):
            return self._check('delegation_execution', 'Chief of Staff delegation execution', False,
                               'configuration incomplete')
        try:
            chief = self.bots.get(chief_row['bot_id'])
        except KeyError:
            return self._check('delegation_execution', 'Chief of Staff delegation execution', False,
                               'Chief of Staff is not executable')
        if not chief.get('provider_id') or not chief.get('model'):
            return self._check('delegation_execution', 'Chief of Staff delegation execution', False,
                               'Chief of Staff has no executable provider/model', status='skip')
        parent_id = new_id()
        now = utc_now_iso()
        self.storage.save_bot_run({
            'run_id': parent_id, 'bot_id': chief['bot_id'],
            'request_key': 'diagnostics-delegate-' + parent_id,
            'body': 'diagnostics delegation execution', 'status': 'running',
            'created_at': now, 'updated_at': now,
        })
        failed = []
        try:
            for worker in workers:
                try:
                    result = self.bots.engine.execute_tool(
                        chief, 'delegate_bot',
                        {'bot_id': worker['bot_id'], 'prompt': 'Reply with the single word OK.'},
                        parent_id, RunBudget(), ())
                    reply = str(result.get('reply') or '')
                    status = result.get('status')
                    if result.get('error') or status != 'done' or not reply.strip():
                        failed.append(worker['name'] + (f' ({status or "no status"})' if status != 'done' else ''))
                except Exception as exc:
                    failed.append(worker['name'] + ' (' + safe_detail(exc, 80) + ')')
        finally:
            parent = self.storage.get_bot_run(parent_id) or {}
            parent.update(run_id=parent_id, bot_id=chief['bot_id'],
                          request_key='diagnostics-delegate-' + parent_id,
                          status='done', updated_at=utc_now_iso())
            self.storage.save_bot_run(parent)
        ok = not failed
        detail = ('delegated to ' + ', '.join(w['name'] for w in workers) if ok
                  else 'execution failed: ' + ', '.join(failed))
        return self._check('delegation_execution', 'Chief of Staff delegation execution', ok, detail)

    def _emit_card_mismatch(self, run_id: str, data: dict) -> None:
        rid = run_id or 'diagnostics-card'
        if not self.storage.get_bot_run(rid):
            home = self._home()
            if not home:
                return
            now = utc_now_iso()
            self.storage.save_bot_run({
                'run_id': rid, 'bot_id': home['bot_id'],
                'request_key': 'diag-mismatch-' + rid[:80],
                'body': 'diagnostics card visibility', 'status': 'done',
                'created_at': now, 'updated_at': now,
            })
        self.bots.engine.emit(rid, 'card_render_mismatch', data)

    def _diag_card_visibility(self) -> dict:
        mismatches = []
        for card in self.storage.all_chat_cards():
            if card.get('status') != 'pending' or card.get('probe'):
                continue
            visible = self.visible_cards(card['bot_id'])
            if card.get('target_id'):
                visible += self.visible_cards(card['target_id'])
            ids = {item.get('card_id') for item in visible}
            if card.get('card_id') not in ids or not self.card_is_renderable(card):
                mismatches.append(card.get('kind') or 'card')
                self._emit_card_mismatch(card.get('run_id') or '', {
                    'card_id': card.get('card_id'), 'kind': card.get('kind'),
                    'detail': 'pending card is not renderable in its conversation'})
        for bot in self._saved_bots():
            waiting = self.storage.waiting_bot_run(bot['bot_id'])
            if not waiting:
                continue
            pending = [card for card in self.visible_cards(bot['bot_id'])
                       if card.get('status') == 'pending' and not card.get('probe')
                       and card.get('run_id') == waiting.get('run_id')]
            if not pending:
                mismatches.append(bot.get('name') or 'bot')
                self._emit_card_mismatch(waiting.get('run_id') or '', {
                    'bot_id': bot.get('bot_id'),
                    'detail': 'waiting_for_user with no visible approval card'})
        ok = not mismatches
        return self._check('card_visibility', 'Approval card visibility', ok,
                           'pending cards are visible in chat' if ok else 'hidden cards: ' + ', '.join(mismatches))

    def _diag_memory(self) -> dict:
        from .bot_engine import RunBudget
        snapshot = next((bot for bot in self._saved_bots()
                         if 'memory_write' in (bot.get('tools') or [])
                         and 'memory_read' in (bot.get('tools') or [])), None)
        if not snapshot:
            return self._check('memory', 'Memory write/read', False, 'No bot has memory tools granted')
        try:
            target = self.bots.get(snapshot['bot_id'])
        except KeyError:
            return self._check('memory', 'Memory write/read', False, 'Memory bot is not executable')
        marker = 'diagnostics-ok'
        try:
            self.bots.engine.execute_tool(target, 'memory_write', {'key': MEMORY_PROBE_KEY, 'body': marker},
                                         'diagnostics-memory', RunBudget(), ())
            result = self.bots.engine.execute_tool(target, 'memory_read', {}, 'diagnostics-memory', RunBudget(), ())
        except Exception as exc:
            return self._check('memory', 'Memory write/read', False, exc)
        memories = result.get('memories') or []
        ok = any(item.get('memory_key') == MEMORY_PROBE_KEY and item.get('body') == marker for item in memories)
        return self._check('memory', 'Memory write/read', ok,
                           'wrote and read diagnostics probe' if ok else 'probe value was not returned')

    @contextmanager
    def _probe_origin(self):
        browsers = self.bots.browsers
        origin = 'http://127.0.0.1:9'
        previous = list(browsers.test_origins)
        if origin not in previous:
            browsers.test_origins = previous + [origin]
        try:
            yield origin, origin + '/synkraken-diagnostics'
        finally:
            browsers.test_origins = previous

    def _diag_browser_capability(self) -> dict:
        bot = self._probe_bot()
        if not bot:
            return self._check('browser_capability', 'Browser capability card', False, 'No bot available')
        pending = next((card for card in self.storage.chat_cards(bot['bot_id'])
                        if card['kind'] == 'capability' and card['status'] == 'pending'
                        and card.get('capability') == 'browser' and not card.get('probe')), None)
        if pending:
            ok = bool(pending.get('run_id'))
            return self._check('browser_capability', 'Browser capability card', ok,
                               'operator capability card is present' if ok else 'pending capability card has no run_id')
        result = self.request_capability(bot, {'capability': 'browser', 'reason': 'diagnostics'}, 'diagnostics-cap')
        if result.get('enabled'):
            return self._check('browser_capability', 'Browser capability card', True, 'browser tools already granted')
        card_id = result.get('card_id')
        card = self.storage.get_chat_card(card_id) if card_id else None
        if not card:
            return self._check('browser_capability', 'Browser capability card', False, 'capability card was not created')
        card['probe'] = True
        self.storage.save_chat_card(card)
        bound = card.get('run_id') == 'diagnostics-cap'
        self.resolve_card(card_id, {'cancel': True})
        return self._check('browser_capability', 'Browser capability card', bound,
                           'capability card created and bound to the probe run' if bound else 'capability card missing run_id')

    def _origin_resume_probe(self) -> dict:
        cached = (getattr(self, '_diag_ctx', None) or {}).get('origin_probe')
        if cached is not None:
            return cached
        bot = self._probe_bot()
        if not bot:
            result = {'origin_ok': False, 'same_run_ok': False, 'origin_detail': 'No bot available',
                      'same_run_detail': 'No bot available'}
            if getattr(self, '_diag_ctx', None) is not None:
                self._diag_ctx['origin_probe'] = result
            return result
        with self._probe_origin() as (origin, url):
            existing = next((card for card in self.storage.chat_cards(bot['bot_id'])
                             if card['kind'] == 'browser_access' and card['status'] == 'pending'
                             and card.get('origin') == origin and not card.get('probe')), None)
            if existing:
                bound = bool(existing.get('run_id'))
                result = {
                    'origin_ok': bound,
                    'same_run_ok': bound,
                    'origin_detail': 'operator origin card is bound to a run' if bound else 'pending origin card has no run_id',
                    'same_run_detail': 'operator origin card is bound to a run' if bound else 'pending origin card has no run_id',
                }
                if getattr(self, '_diag_ctx', None) is not None:
                    self._diag_ctx['origin_probe'] = result
                return result
            previous_origins = list(self.bots.browsers.permitted_origins(bot['bot_id']))
            run_id = new_id()
            now = utc_now_iso()
            probe_run = {
                'run_id': run_id, 'bot_id': bot['bot_id'], 'request_key': 'diagnostics-origin-' + run_id,
                'body': 'diagnostics origin continuation', 'status': 'waiting_for_user',
                'created_at': now, 'updated_at': now,
            }
            self.bots.storage.save_bot_run(probe_run)
            opened = self.bots.browsers.act(bot['bot_id'], 'open', {'url': url}, run_id=run_id)
            if opened.get('status') != 'waiting_for_user':
                probe_run.update(status='cancelled', updated_at=utc_now_iso())
                self.bots.storage.save_bot_run(probe_run)
                result = {'origin_ok': False, 'same_run_ok': False,
                          'origin_detail': 'origin card was not requested',
                          'same_run_detail': 'origin card was not requested'}
                if getattr(self, '_diag_ctx', None) is not None:
                    self._diag_ctx['origin_probe'] = result
                return result
            card = self.storage.get_chat_card(opened['card_id'])
            card['probe'] = True
            self.storage.save_chat_card(card)
            if card.get('run_id') != run_id:
                self.resolve_card(card['card_id'], {'cancel': True})
                probe_run.update(status='cancelled', updated_at=utc_now_iso())
                self.bots.storage.save_bot_run(probe_run)
                result = {'origin_ok': False, 'same_run_ok': False,
                          'origin_detail': 'origin card was not bound to the same run',
                          'same_run_detail': 'same-run resume was not requested'}
                if getattr(self, '_diag_ctx', None) is not None:
                    self._diag_ctx['origin_probe'] = result
                return result
            resumed = []
            original_resume = self.bots.resume
            self.bots.resume = lambda value: resumed.append(value) or {
                'run_id': value, 'status': 'waiting_for_user', 'resumed': True}
            try:
                outcome = self.resolve_card(card['card_id'], {'approve': True})
            finally:
                self.bots.resume = original_resume
                self.storage.save_workspace_value('browser:' + bot['bot_id'], {'origins': previous_origins})
                probe_run.update(status='done', updated_at=utc_now_iso(), result='diagnostics probe')
                self.bots.storage.save_bot_run(probe_run)
            origin_ok = outcome.get('card', {}).get('status') == 'approved'
            same_run_ok = resumed == [run_id]
            result = {
                'origin_ok': origin_ok,
                'same_run_ok': same_run_ok,
                'origin_detail': 'origin approved' if origin_ok else 'origin was not approved',
                'same_run_detail': 'origin approved and same-run resume requested' if same_run_ok
                else 'same-run resume was not requested',
            }
            if getattr(self, '_diag_ctx', None) is not None:
                self._diag_ctx['origin_probe'] = result
            return result

    def _diag_browser_origin(self) -> dict:
        probe = self._origin_resume_probe()
        origin_ok = probe['origin_ok']
        return self._check('browser_origin', 'Browser origin card', origin_ok, probe['origin_detail'])

    def _diag_same_run(self) -> dict:
        probe = self._origin_resume_probe()
        return self._check('same_run_continuation', 'Same-run continuation', probe['same_run_ok'],
                           probe['same_run_detail'])

    def _diag_browser_failure(self) -> dict:
        bot = self._probe_bot()
        if not bot:
            return self._check('browser_failure', 'Honest browser failure', False, 'No bot available')
        browsers = self.bots.browsers
        previous_act = browsers._act
        previous_origins = list(browsers.permitted_origins(bot['bot_id']))

        def fail(*_args, **_kwargs):
            raise ValueError('Browser runtime is unavailable')

        with self._probe_origin() as (origin, url):
            browsers.grant(bot['bot_id'], origin)
            browsers._act = fail
            try:
                result = browsers.act(bot['bot_id'], 'open', {'url': url}, run_id='diagnostics-fail')
            except ValueError as exc:
                text = str(exc).lower()
                fabricated = any(word in text for word in ('citation', 'according to', 'verified page'))
                ok = 'unavailable' in text and not fabricated
                return self._check('browser_failure', 'Honest browser failure', ok,
                                   'failure reported without invented sources' if ok else 'failure was not reported honestly')
            finally:
                browsers._act = previous_act
                self.storage.save_workspace_value('browser:' + bot['bot_id'], {'origins': previous_origins})
        text = json.dumps(result).lower()
        invented = any(word in text for word in ('citation', 'according to', 'verified page', 'sources:'))
        ok = bool(result.get('error')) and not invented and not result.get('text')
        return self._check('browser_failure', 'Honest browser failure', ok,
                           'failure reported without invented sources' if ok else 'browser result looked fabricated')

    def resolve_card(self, card_id: str, payload: dict) -> dict:
        with self.lock:
            card = self.storage.get_chat_card(card_id)
            if not card:
                raise KeyError(card_id)
            if card['status'] != 'pending':
                return {'card': card}
            if payload.get('cancel') is True:
                card['status'] = 'dismissed'
            elif card['kind'] == 'credential':
                values = {key: payload.get(key, '') for key in ('username', 'password')}
                if not all(isinstance(value, str) and 0 < len(value) <= 4096 for value in values.values()):
                    raise ValueError('Username and password are required')
                self.bots.providers.vault.put(card_id, values)
                card.update(status='saved', credential_ref=card_id)
            elif card['kind'] == 'connection':
                key = payload.get('api_key', '')
                if card['provider'] != 'ollama' and not key:
                    raise ValueError('Sign in or enter an API key in this card')
                provider = self.bots.providers.save({**PRESETS[card['provider']], 'api_key': key})
                card.update(status='connected', provider_id=provider['provider_id'])
            elif card['kind'] == 'capability':
                if payload.get('approve') is not True:
                    raise ValueError('Approve this capability first')
                bot = self.bots.get(card['bot_id'])
                self.bots.save({'tools': list(dict.fromkeys(bot['tools'] + card['tools']))}, bot['bot_id'])
                card['status'] = 'applied'
            elif card['kind'] == 'bot_change':
                if payload.get('approve') is not True:
                    raise ValueError('Review and apply the proposed change')
                changes = card['changes']
                if card.get('grant') == CHIEF_DELEGATION_GRANT:
                    recomputed = self._chief_delegation_changes()
                    if not recomputed:
                        card['status'] = 'applied'
                        self.storage.save_chat_card(card)
                        return {'card': card}
                    changes = recomputed
                    card['changes'] = changes
                self.bots.save(changes, card['target_id'])
                card['status'] = 'applied'
            elif card['kind'] == 'browser_access':
                if payload.get('approve') is not True:
                    raise ValueError('Approve browser access to this site')
                self.bots.browsers.grant(card['bot_id'], card['origin'])
                card['status'] = 'approved'
            else:
                raise ValueError('Unknown card type')
            self.storage.save_chat_card(card)
            result = {'card': card}
            if (payload.get('approve') is True and card.get('run_id')):
                waiting = self.bots.storage.get_bot_run(card['run_id'])
                if waiting and waiting.get('status') == 'waiting_for_user':
                    outcome = self.bots.resume(card['run_id'])
                    result['run'] = self.bots.storage.get_bot_run(card['run_id'])
                    result['status'] = outcome['status']
            return result


DIAGNOSTIC_CHECKS = {
    'provider': ('Active provider and model', ChatWorkspace._diag_provider),
    'provider_roundtrip': ('Provider round trip', ChatWorkspace._diag_roundtrip),
    'roster': ('Roster integrity', ChatWorkspace._diag_roster),
    'minimax_assignment': ('MiniMax assignment', ChatWorkspace._diag_minimax),
    'delegation': ('Chief of Staff delegation', ChatWorkspace._diag_delegation),
    'delegation_execution': ('Chief of Staff delegation execution', ChatWorkspace._diag_delegation_execution),
    'memory': ('Memory write/read', ChatWorkspace._diag_memory),
    'browser_capability': ('Browser capability card', ChatWorkspace._diag_browser_capability),
    'browser_origin': ('Browser origin card', ChatWorkspace._diag_browser_origin),
    'same_run_continuation': ('Same-run continuation', ChatWorkspace._diag_same_run),
    'browser_failure': ('Honest browser failure', ChatWorkspace._diag_browser_failure),
    'card_visibility': ('Approval card visibility', ChatWorkspace._diag_card_visibility),
}


def safe_detail(value, limit: int = 240) -> str:
    text = str(value or '')
    text = re.sub(r'(?i)(api[_-]?key|authorization|bearer|password|passwd|secret|token|keychain|vault|credential)([=:\s]+)\S+',
                  r'\1\2[redacted]', text)
    text = re.sub(r'(?i)\b(?:sk-|or-|xai-|mm-)[A-Za-z0-9_\-]{8,}', '[redacted]', text)
    return text[:limit] if limit else text
