from __future__ import annotations

import base64
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from synkraken.bot_engine import RunBudget
from synkraken.chat_install import prepare_config
from synkraken.providers import ProviderClient, ModelReply
from synkraken.vault import CredentialVault
from synkraken.workspace import HOST_TOOLS
from test_bot_engine import provider_server, answer, call
from synkraken.fabric import AgentFabric
from synkraken.storage import Storage


@pytest.fixture
def fabric(tmp_path):
    storage = Storage(tmp_path / "chat.db")
    value = AgentFabric({"adapters": {}, "routing": {}}, storage)
    yield value
    value.bots._executor.shutdown(wait=True)
    storage._conn.close()


def bootstrap(fabric, endpoint):
    provider = fabric.bots.providers.save({'name': 'Test', 'protocol': 'openai_compatible', 'base_url': endpoint})
    return fabric.bots.workspace.setup({'action': 'use_existing', 'provider_id': provider['provider_id'], 'model': 'test-model'})


def test_blank_bootstrap_inherits_model_without_persona_or_skills(fabric):
    with provider_server(lambda *_: answer('Hello')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        bot = fabric.bots.get(state['home_bot_id'])
        assert bot['job'] == bot['instructions'] == bot['notes'] == ''
        assert bot['tools'] == HOST_TOOLS
        fabric.bots.send(bot['bot_id'], {'body': 'Hello'})
        assert requests[0]['body']['messages'][-1] == {'role': 'user', 'content': 'Hello'}
        assert 'Never invent approximate schedules' in requests[0]['body']['messages'][0]['content']
        assert 'Current host date and time:' in requests[0]['body']['messages'][0]['content']
        assert fabric.bots.workspace.state()['home_bot_id'] == bot['bot_id']


def test_workspace_health_and_diagnostics_are_chat_safe(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        health = fabric.bots.workspace.host_tool(home, 'workspace_health', {}, 'run')
        assert health['bot_count'] == 1
        assert 'credential_ready' in health['provider_status'][0]
        assert all('api_key' not in json.dumps(value) for value in health.values())
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'run')
        ids = {item['id'] for item in result['checks']}
        assert ids >= {'provider', 'provider_roundtrip', 'roster', 'minimax_assignment', 'delegation',
                       'delegation_execution', 'memory', 'browser_capability', 'browser_origin',
                       'same_run_continuation', 'browser_failure', 'card_visibility'}
        assert 'api_key' not in json.dumps(result)
        assert result['ok'] is False
        failed = {item['id'] for item in result['checks'] if not item['ok']}
        assert 'roster' in failed
        rerun = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'failed'}, 'run')
        assert {item['id'] for item in rerun['checks']} == failed
        assert fabric.bots.workspace.state()['last_diagnostics']['failed'] == [
            item['id'] for item in rerun['checks'] if not item['ok']]


def test_chat_creates_real_blank_bot_and_preserves_default(fabric):
    def respond(body, count):
        return answer('', [call('create_bot', {'name': 'Quinn', 'job': '', 'instructions': ''})]) if count == 1 else answer('Quinn is ready.')
    with provider_server(respond) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        fabric.bots.send(state['home_bot_id'], {'body': 'Create Quinn, a blank bot'})
        bots = fabric.bots.list()
        assert len(bots) == 2
        quinn = next(bot for bot in bots if bot['name'] == 'Quinn')
        assert quinn['model'] == state['default_model']
        assert quinn['provider_id'] == state['default_provider_id']
        assert quinn['tools'] == [] and quinn['instructions'] == ''
        assert requests[1]['body']['messages'][-1]['role'] == 'tool'


def test_secure_card_values_never_enter_state_events_or_model_messages(fabric):
    with provider_server(lambda *_: answer()) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        bot = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(bot, 'request_secret', {'service': 'Example', 'purpose': 'Store login'}, 'run')
        card_id = result['card_id']
        fabric.bots.workspace.resolve_card(card_id, {'username': 'private-user', 'password': 'private-password'})
        assert fabric.bots.providers.vault.get(card_id) == {'username': 'private-user', 'password': 'private-password'}
        fabric.bots.send(bot['bot_id'], {'body': 'Is my input saved?'})
        all_visible = json.dumps([fabric.bots.conversation(bot['bot_id']), requests, fabric.bots.workspace.state()])
        assert 'private-password' not in all_visible and 'private-user' not in all_visible
        assert any('Host input-card receipts:' in m['content'] and 'saved' in m['content'] for m in requests[0]['body']['messages'] if m['role'] == 'system')
        assert b'private-password' not in fabric.storage.sqlite_path.read_bytes()
        assert 'private-password' not in json.dumps(fabric.bots.providers.vault.encrypted_export())
        repeated = fabric.bots.workspace.resolve_card(card_id, {'password': 'different'})
        assert repeated['card']['status'] == 'saved'
        assert fabric.bots.providers.vault.get(card_id)['password'] == 'private-password'


def test_bot_change_requires_card_acceptance(fabric):
    state = bootstrap(fabric, 'http://localhost:1234/v1')
    home = fabric.bots.get(state['home_bot_id'])
    created = fabric.bots.workspace.host_tool(home, 'create_bot', {'name': 'Writer', 'job': '', 'instructions': ''}, 'run')
    args = {'bot_id': created['bot_id'], 'name': 'Editor', 'job': '', 'instructions': '', 'provider_id': '', 'model': '', 'tools': 'memory_read'}
    result = fabric.bots.workspace.host_tool(home, 'configure_bot', args, 'run')
    assert fabric.bots.get(created['bot_id'])['name'] == 'Writer'
    with pytest.raises(ValueError):
        fabric.bots.workspace.resolve_card(result['card_id'], {})
    fabric.bots.workspace.resolve_card(result['card_id'], {'approve': True})
    assert fabric.bots.get(created['bot_id'])['name'] == 'Editor'
    assert fabric.bots.get(created['bot_id'])['tools'] == ['memory_read']
    with pytest.raises(ValueError, match='entry conversation'):
        fabric.bots.workspace.host_tool(fabric.bots.get(created['bot_id']), 'workspace_bots', {}, 'run')


def test_oauth_pkce_verifier_stays_on_host_and_code_is_single_use(fabric, monkeypatch):
    ws = fabric.bots.workspace
    ws.setup({'action': 'select', 'provider': 'openrouter'})
    ws.setup({'action': 'model', 'model': 'chosen/model'})
    flow = ws.start_oauth()
    verifier = ws.oauth[flow['flow_id']]['verifier']
    assert verifier not in json.dumps(flow)
    assert 'code_challenge_method=S256' in flow['authorization_url']
    observed = []

    def exchange(self, path, payload, timeout):
        observed.append((self.provider['base_url'], path, payload))
        if path == '/chat/completions':
            return answer('OK')
        return {'key': 'oauth-secret-key'}

    monkeypatch.setattr(ProviderClient, 'request', exchange)
    result = ws.finish_oauth(flow['flow_id'], 'one-time-code')
    assert result['ready']
    assert observed[0][0] == 'https://openrouter.ai/api/v1'
    assert observed[0][2]['code_verifier'] == verifier
    assert 'oauth-secret-key' not in json.dumps(result)
    with pytest.raises(ValueError, match='already used'):
        ws.finish_oauth(flow['flow_id'], 'one-time-code')


@pytest.mark.parametrize('reason', ['expired', 'changed'])
def test_oauth_expiry_and_setup_binding(fabric, reason):
    ws = fabric.bots.workspace
    ws.setup({'action': 'select', 'provider': 'openrouter'})
    ws.setup({'action': 'model', 'model': 'chosen/model'})
    flow = ws.start_oauth()
    if reason == 'expired':
        ws.oauth[flow['flow_id']]['expires'] = time.monotonic() - 1
    else:
        ws.setup({'action': 'select', 'provider': 'anthropic'})
        ws.setup({'action': 'model', 'model': 'other-model'})
    with pytest.raises(ValueError):
        ws.finish_oauth(flow['flow_id'], 'unused-code')
    assert not fabric.bots.providers.list()


def test_parallel_setup_creates_only_one_entry_bot(fabric):
    provider = fabric.bots.providers.save({'name': 'Local', 'protocol': 'openai_compatible', 'base_url': 'http://localhost:1234/v1'})
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: fabric.bots.workspace.setup({'action': 'use_existing', 'provider_id': provider['provider_id'], 'model': 'test'}), range(4)))
    assert len({result['home_bot_id'] for result in results}) == 1
    assert len(fabric.bots.list()) == 1


def test_vault_authentication_and_key_separation(tmp_path, monkeypatch):
    vault = CredentialVault(tmp_path / 'vault')
    vault.put('one', {'password': 'sensitive'})
    assert vault.get('one')['password'] == 'sensitive'
    encrypted = vault.encrypted_export()
    assert 'sensitive' not in json.dumps(encrypted)
    assert sorted(path.name for path in vault.directory.iterdir()) == ['one.enc']
    (vault.directory / 'two.enc').write_bytes((vault.directory / 'one.enc').read_bytes())
    with pytest.raises(ValueError, match='verified'):
        vault.get('two')
    monkeypatch.setenv('SYNKRAKEN_VAULT_KEY', base64.urlsafe_b64encode(os.urandom(32)).decode())
    with pytest.raises(ValueError, match='verified'):
        vault.get('one')


def test_legacy_plain_key_is_encrypted_on_first_use(fabric):
    provider = fabric.bots.providers.save({'name': 'Legacy', 'protocol': 'openai_compatible', 'base_url': 'https://example.com/v1'})
    old = fabric.bots.providers.credentials / provider['provider_id']
    old.parent.mkdir(parents=True)
    old.write_text('legacy-secret')
    assert fabric.bots.providers.client(provider['provider_id']).api_key == 'legacy-secret'
    assert not old.exists()
    assert fabric.bots.providers.vault.get(provider['provider_id'])['api_key'] == 'legacy-secret'


def test_install_preserves_existing_configuration_and_creates_native_defaults(tmp_path):
    path = tmp_path / 'config.json'
    prepare_config(path)
    assert json.loads(path.read_text())['adapters'] == {}
    original = path.read_bytes()
    prepare_config(path)
    assert path.read_bytes() == original


def test_blank_bot_cannot_execute_ungranted_host_tools(fabric):
    state = bootstrap(fabric, 'http://localhost:1234/v1')
    bot = fabric.bots.save({'name': 'Blank', 'provider_id': state['default_provider_id'], 'model': 'test', 'tools': []})
    with pytest.raises(ValueError, match='not permitted'):
        fabric.bots.engine.execute_tool(bot, 'workspace_bots', {}, 'none', RunBudget(), ())


def test_vault_never_falls_back_to_plaintext_keyring(tmp_path, monkeypatch):
    import synkraken.vault as module
    monkeypatch.delenv('SYNKRAKEN_VAULT_KEY')
    monkeypatch.setattr(module.keyring, 'get_keyring', lambda: object())
    vault = CredentialVault(tmp_path / 'vault')
    with pytest.raises(ValueError, match='OS keychain'):
        vault.put('one', {'password': 'sensitive'})
    assert not vault.directory.exists()


def test_workspace_and_card_routes_require_authentication(fabric):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from synkraken.api import FabricRequestHandler
    from test_bots import request

    class Handler(FabricRequestHandler):
        auth_token = 'test-token'

        def log_message(self, *args):
            pass

    Handler.fabric = fabric
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_port
        assert request(port, '/v1/workspace', token='wrong')[0] == 401
        assert request(port, '/v1/workspace/setup', 'POST', {'action': 'select', 'provider': 'openrouter'})[0] == 200
        assert request(port, '/v1/workspace/setup', 'POST', {'action': 'model', 'model': 'chosen'})[0] == 200
        assert request(port, '/v1/workspace/oauth/start', 'POST', {}, token='wrong')[0] == 401
        assert request(port, '/v1/workspace/oauth/start', 'POST', {})[0] == 200
        assert request(port, '/v1/chat-cards/missing', 'POST', {}, token='wrong')[0] == 401
        assert request(port, '/v1/chat-cards/missing', 'POST', {})[0] == 404
        assert request(port, '/v1/workspace/setup', 'POST', [])[0] == 400
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('kind,model,protocol,base_url', [
    ('minimax', 'MiniMax-M2.5', 'anthropic', 'https://api.minimax.io/anthropic/v1'),
    ('grok', 'user-chosen-model', 'openai_compatible', 'https://api.x.ai/v1'),
])
def test_requested_provider_bootstrap_and_inheritance(fabric, monkeypatch, kind, model, protocol, base_url):
    verified = []
    def verify(self, selected_model, messages, tools, timeout):
        verified.append(selected_model)
        return ModelReply({'role': 'assistant', 'content': 'OK'}, {}, 'stop')
    monkeypatch.setattr(ProviderClient, 'complete', verify)
    ws = fabric.bots.workspace
    ws.setup({'action': 'select', 'provider': kind})
    ws.setup({'action': 'model', 'model': model})
    state = ws.setup({'action': 'connect', 'api_key': 'test-only-secret'})
    assert verified == [model]
    bot = fabric.bots.get(state['home_bot_id'])
    provider = fabric.bots.providers.get(bot['provider_id'])
    assert provider['base_url'] == base_url
    assert provider['protocol'] == protocol
    assert bot['model'] == model
    assert bot['instructions'] == ''
    assert 'test-only-secret' not in json.dumps(state)
    assert fabric.bots.providers.client(provider['provider_id']).api_key == 'test-only-secret'
    with pytest.raises(ValueError, match='Choose OpenRouter'):
        ws.start_oauth()


def test_minimax_transport_preserves_thinking_across_tool_calls():
    thinking = {'type': 'thinking', 'thinking': 'private test reasoning', 'signature': 'opaque-test'}
    first = [thinking, {'type': 'tool_use', 'id': 'tool-1', 'name': 'memory_read', 'input': {}}]
    with provider_server(lambda body, n: {'content': first if n == 1 else [{'type': 'text', 'text': 'Done'}],
                                         'stop_reason': 'tool_use' if n == 1 else 'end_turn'}) as (endpoint, requests):
        client = ProviderClient({'protocol': 'anthropic', 'base_url': endpoint.replace('/v1', '/anthropic/v1')}, 'test-only-key')
        messages = [{'role': 'user', 'content': 'Recall my context'}]
        result = client.complete('MiniMax-M2.5', messages, [], 2)
        messages += [result.message, {'role': 'tool', 'tool_call_id': 'tool-1', 'content': 'No saved memory'}]
        assert client.complete('MiniMax-M2.5', messages, [], 2).message['content'] == 'Done'
        assert requests[0]['path'] == '/anthropic/v1/messages'
        assert {k.lower(): v for k, v in requests[0]['headers'].items()}['x-api-key'] == 'test-only-key'
        assert requests[1]['body']['messages'][1]['content'] == first
        assert requests[1]['body']['messages'][2]['content'][0]['tool_use_id'] == 'tool-1'


def test_blank_bot_can_request_but_not_grant_its_own_browser(fabric):
    with provider_server(lambda body, n: answer(calls=[call('request_capability', {
            'capability': 'browser', 'reason': 'Check official train times for tomorrow'})]) if n == 1
            else answer('Please enable browser access using the card.')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        created = fabric.bots.workspace.host_tool(home, 'create_bot', {
            'name': 'Scout', 'job': 'Research topics', 'instructions': ''}, 'create')
        scout = fabric.bots.get(created['bot_id'])
        assert scout['tools'] == []
        result = fabric.bots.send(scout['bot_id'], {'body': 'Train times tomorrow morning'})
        assert result['status'] == 'waiting_for_user'
        assert 'request_capability' in [t['function']['name'] for t in requests[0]['body']['tools']]
        cards = fabric.storage.chat_cards(scout['bot_id'])
        card = next(c for c in cards if c['kind'] == 'capability')
        assert card['bot_id'] == scout['bot_id']
        assert fabric.bots.get(scout['bot_id'])['tools'] == []
        with pytest.raises(ValueError, match='not permitted'):
            fabric.bots.engine.execute_tool(scout, 'browser_open', {'url': 'https://example.com'}, 'test', RunBudget(), ())
        fabric.bots.workspace.resolve_card(card['card_id'], {'approve': True})
        assert 'browser_open' in fabric.bots.get(scout['bot_id'])['tools']
        assert 'browser_open' not in fabric.bots.get(home['bot_id'])['tools']
        assert fabric.bots.browsers.permitted_origins(scout['bot_id']) == []
        assert fabric.bots.workspace.resolve_card(card['card_id'], {'approve': True})['card']['status'] == 'applied'


def test_capability_request_cannot_grant_workspace_management(fabric):
    with provider_server(lambda *_: answer()) as (endpoint, _):
        state = bootstrap(fabric, endpoint)
        bot = fabric.bots.get(state['home_bot_id'])
        with pytest.raises(ValueError, match='Choose browser'):
            fabric.bots.workspace.request_capability(bot, {'capability': 'create_bot', 'reason': 'escalate'}, 'test')
        result = fabric.bots.workspace.request_capability(bot, {'capability': 'browser', 'reason': 'research'}, 'test')
        again = fabric.bots.workspace.request_capability(bot, {'capability': 'browser', 'reason': 'research'}, 'test')
        assert result['card_id'] == again['card_id']
        fabric.bots.workspace.resolve_card(result['card_id'], {'cancel': True})
        assert 'browser_open' not in fabric.bots.get(bot['bot_id'])['tools']


def test_missing_web_refusal_becomes_actionable_card(fabric):
    with provider_server(lambda *_: answer("I don't have live access to train schedules. If you'd like, I can request browser access.")) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        bot_id = state['home_bot_id']
        result = fabric.bots.send(bot_id, {'body': 'Train times tomorrow morning'})
        assert len(requests) == 1
        assert 'Enable it in the card' in result['result']['deliveries'][-1]['body']
        assert 'If you' not in result['result']['deliveries'][-1]['body']
        assert any(c['kind'] == 'capability' and c['status'] == 'pending' for c in fabric.storage.chat_cards(bot_id))
        assert 'browser_open' not in fabric.bots.get(bot_id)['tools']


def test_pending_access_card_pauses_without_another_model_call(fabric):
    with provider_server(lambda *_: answer("", [call("request_capability", {
        "capability": "browser", "reason": "Check current sources"})])) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        result = fabric.bots.send(state["home_bot_id"], {"body": "Check live train times"})
    assert len(requests) == 1
    assert "card below" in result["result"]["deliveries"][0]["body"]
    assert fabric.storage.chat_cards(state["home_bot_id"])[-1]["status"] == "pending"


def test_fabricated_bot_creation_is_retried_then_verified(fabric):
    def respond(body, count):
        if count == 1:
            return answer("Done! Your bot **Pa** is ready (ID: `made-up-id`).")
        if count == 2:
            assert "no successful create_bot receipt" in body["messages"][-1]["content"]
            return answer("", [call("create_bot", {"name": "Pa", "job": "Personal assistant", "instructions": ""})])
        return answer("Pa is ready with calendar access and reminders. ID: made-up-id")
    with provider_server(respond) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        result = fabric.bots.send(state["home_bot_id"], {"body": "Create a personal assistant bot"})
    assert len(fabric.bots.list()) == 2
    final = result["result"]["deliveries"][0]["body"]
    assert "Pa is ready" in final and "made-up-id" not in final and "calendar" not in final
    assert any(e["event_type"] == "unverified_action_rejected" for e in fabric.storage.bot_run_events(result["run_id"]))


def test_repeated_fabricated_creation_fails_without_a_phantom_bot(fabric):
    with provider_server(lambda *_: answer("Your bot Pa is ready.")) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        result = fabric.bots.send(state["home_bot_id"], {"body": "Create a personal assistant bot"})
    assert len(requests) == 2
    assert len(fabric.bots.list()) == 1
    assert result["status"] == "blocked"
    assert result["result"]["deliveries"][0]["body"] == ""
    assert "No bot was created" in result["result"]["deliveries"][0]["error"]


def test_host_gets_actual_roster_after_unverified_history(fabric):
    with provider_server(lambda *_: answer("There is one saved bot.")) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        fabric.bots.send(state["home_bot_id"], {"body": "How many bots exist?"})
    snapshot = next(m["content"] for m in requests[0]["body"]["messages"] if "Current saved workspace bots" in m["content"])
    assert state["home_bot_id"] in snapshot
    assert "Only these bots currently exist" in snapshot
