from __future__ import annotations

import base64
import hashlib
import json
import secrets
from threading import RLock
import time
from urllib.parse import urlencode

from .models import new_id, utc_now_iso
from .providers import ProviderClient


HOST_TOOLS = ['workspace_bots', 'create_bot', 'configure_bot', 'request_connection', 'request_secret']
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
        card = {'card_id': new_id(), 'bot_id': bot_id, 'kind': kind, 'status': 'pending',
                'created_at': utc_now_iso(), **fields}
        self.storage.save_chat_card(card)
        return {'card_id': card['card_id'], 'status': 'waiting_for_user',
                'message': 'The input card is in the conversation. Do not ask for secrets in chat.'}

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
                             and c['capability'] == capability), None)
            if existing:
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
        raise ValueError('Unknown workspace action')

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
                self.bots.save(card['changes'], card['target_id'])
                card['status'] = 'applied'
            elif card['kind'] == 'browser_access':
                if payload.get('approve') is not True:
                    raise ValueError('Approve browser access to this site')
                self.bots.browsers.grant(card['bot_id'], card['origin'])
                card['status'] = 'approved'
            else:
                raise ValueError('Unknown card type')
            self.storage.save_chat_card(card)
            return {'card': card}
