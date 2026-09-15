from __future__ import annotations

import json
from pathlib import Path

from synkraken.providers import ProviderClient
from synkraken.workspace import DIAGNOSTIC_CHECKS, HOST_TOOLS, MEMORY_PROBE_KEY, TEAM_BOTS, safe_detail
from test_bot_engine import answer, call, provider_server
from test_chat_workspace import bootstrap, fabric


def create_named_team(fabric, state):
    home = fabric.bots.get(state['home_bot_id'])
    created = {}
    for name in TEAM_BOTS:
        created[name] = fabric.bots.workspace.host_tool(
            home, 'create_bot', {'name': name, 'job': '', 'instructions': ''}, 'create-' + name)
    return created


def seed_team(fabric, state):
    created = create_named_team(fabric, state)
    workers = [created[name]['bot_id'] for name in TEAM_BOTS if name != 'Chief of Staff']
    for name in TEAM_BOTS:
        payload = {'model': 'MiniMax-M3', 'tools': ['memory_read', 'memory_write']}
        if name == 'Chief of Staff':
            payload['tools'] = ['memory_read', 'memory_write', 'delegate_bot', 'bots_list']
            payload['delegate_to'] = workers
        fabric.bots.save(payload, created[name]['bot_id'])
    return created


def test_seeded_team_diagnostics_pass(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        seed_team(fabric, state)
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        assert {item['id'] for item in result['checks']} == set(DIAGNOSTIC_CHECKS)
        assert result['ok']
        assert all(item['ok'] for item in result['checks'])
        health = fabric.bots.workspace.host_tool(home, 'workspace_health', {}, 'health')
        assert health['bot_count'] == 7
        assert health['last_diagnostics']['ok'] is True
        assert health['last_diagnostics']['failed'] == []
        leftover = [card for card in fabric.storage.chat_cards(home['bot_id'])
                    if card['status'] == 'pending' and card.get('grant') == 'chief_delegation']
        assert leftover == []
        assert health['last_diagnostics']['checks'] == result['checks']
        rerun = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'failed'}, 'diag-failed')
        assert rerun['checks'] == []
        assert rerun['ok']


def test_roster_integrity_detects_duplicates_and_missing_team(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        fabric.bots.workspace.host_tool(home, 'create_bot', {'name': 'Writer', 'job': '', 'instructions': ''}, 'w1')
        fabric.bots.workspace.host_tool(home, 'create_bot', {'name': 'Writer', 'job': '', 'instructions': ''}, 'w2')
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        roster = next(item for item in result['checks'] if item['id'] == 'roster')
        assert roster['ok'] is False
        assert 'duplicates Writer' in roster['detail']
        assert 'missing' in roster['detail']


def test_minimax_assignment_and_chief_of_staff_delegation(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        created = seed_team(fabric, state)
        fabric.bots.save({'model': 'other-model'}, created['Writer']['bot_id'])
        fabric.bots.save({'delegate_to': [created['PA']['bot_id']]}, created['Chief of Staff']['bot_id'])
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        minimax = next(item for item in result['checks'] if item['id'] == 'minimax_assignment')
        delegation = next(item for item in result['checks'] if item['id'] == 'delegation')
        assert minimax['ok'] is False and 'Writer' in minimax['detail']
        assert delegation['ok'] is False
        assert 'Researcher' in delegation['detail']


def test_create_bot_team_does_not_silently_enable_delegate_bot(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        created = create_named_team(fabric, state)
        chief = fabric.bots.get(created['Chief of Staff']['bot_id'])
        assert 'delegate_bot' not in (chief.get('tools') or [])
        assert 'bots_list' not in (chief.get('tools') or [])
        assert not (set(chief.get('tools') or []) & set(HOST_TOOLS))
        home = fabric.bots.get(state['home_bot_id'])
        pending = [card for card in fabric.storage.chat_cards(home['bot_id'])
                   if card['status'] == 'pending' and card.get('grant') == 'chief_delegation']
        assert len(pending) == 1
        changes = pending[0]['changes']
        assert 'delegate_bot' in changes['tools']
        assert 'bots_list' in changes['tools']
        assert not (set(changes['tools']) & set(HOST_TOOLS))
        workers = [created[name]['bot_id'] for name in TEAM_BOTS if name != 'Chief of Staff']
        assert set(changes['delegate_to']) == set(workers)
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        delegation = next(item for item in result['checks'] if item['id'] == 'delegation')
        assert delegation['ok'] is False
        assert 'delegate_bot is not enabled' in delegation['detail']
        assert 'not allowed: PA, Account Manager, Researcher, Writer, PM' in delegation['detail']
        pending = [card for card in fabric.storage.chat_cards(home['bot_id'])
                   if card['status'] == 'pending' and card.get('grant') == 'chief_delegation']
        assert len(pending) == 1
        fabric.bots.workspace.resolve_card(pending[0]['card_id'], {'approve': True})
        chief = fabric.bots.get(chief['bot_id'])
        assert 'delegate_bot' in chief['tools']
        assert 'bots_list' in chief['tools']
        assert set(chief['delegate_to']) == set(workers)
        assert not (set(chief['tools']) & set(HOST_TOOLS))
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag-after')
        delegation = next(item for item in result['checks'] if item['id'] == 'delegation')
        assert delegation['ok'] is True
        leftover = [card for card in fabric.storage.chat_cards(home['bot_id'])
                    if card['status'] == 'pending' and card.get('grant') == 'chief_delegation']
        assert leftover == []


def test_delegation_fails_when_allowlist_complete_but_tool_missing(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        created = create_named_team(fabric, state)
        workers = [created[name]['bot_id'] for name in TEAM_BOTS if name != 'Chief of Staff']
        fabric.bots.save({'delegate_to': workers, 'tools': []}, created['Chief of Staff']['bot_id'])
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        delegation = next(item for item in result['checks'] if item['id'] == 'delegation')
        assert delegation['ok'] is False
        assert 'delegate_bot is not enabled' in delegation['detail']


def test_chief_delegation_card_keeps_existing_tools_on_approve(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        created = create_named_team(fabric, state)
        fabric.bots.save({'tools': ['memory_read', 'memory_write']}, created['Chief of Staff']['bot_id'])
        home = fabric.bots.get(state['home_bot_id'])
        pending = [card for card in fabric.storage.chat_cards(home['bot_id'])
                   if card['status'] == 'pending' and card.get('grant') == 'chief_delegation']
        assert pending
        fabric.bots.workspace.resolve_card(pending[0]['card_id'], {'approve': True})
        chief = fabric.bots.get(created['Chief of Staff']['bot_id'])
        assert set(chief['tools']) >= {'memory_read', 'memory_write', 'delegate_bot', 'bots_list'}
        assert not (set(chief['tools']) & set(HOST_TOOLS))


def test_incomplete_team_does_not_propose_chief_delegation_card(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        fabric.bots.workspace.host_tool(home, 'create_bot', {'name': 'Writer', 'job': '', 'instructions': ''}, 'w')
        fabric.bots.workspace.host_tool(home, 'create_bot', {'name': 'Chief of Staff', 'job': '', 'instructions': ''}, 'c')
        pending = [card for card in fabric.storage.chat_cards(home['bot_id'])
                   if card.get('grant') == 'chief_delegation']
        assert pending == []
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        delegation = next(item for item in result['checks'] if item['id'] == 'delegation')
        assert delegation['ok'] is False
        assert 'delegate_bot is not enabled' not in delegation['detail']
        pending = [card for card in fabric.storage.chat_cards(home['bot_id'])
                   if card.get('grant') == 'chief_delegation']
        assert pending == []


def test_memory_probe_uses_engine_tools(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        seed_team(fabric, state)
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        memory = next(item for item in result['checks'] if item['id'] == 'memory')
        assert memory['ok']
        chief = next(bot for bot in fabric.bots.list() if bot['name'] == 'Chief of Staff')
        stored = fabric.storage.read_bot_memory(chief['bot_id'])
        assert any(item['memory_key'] == MEMORY_PROBE_KEY and item['body'] == 'diagnostics-ok' for item in stored)


def test_failed_checks_are_the_only_ones_rerun(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        first = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        failed = [item['id'] for item in first['checks'] if not item['ok']]
        passed = [item['id'] for item in first['checks'] if item['ok']]
        assert failed and passed
        rerun = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'failed'}, 'diag-failed')
        assert [item['id'] for item in rerun['checks']] == failed
        assert 'provider_roundtrip' not in [item['id'] for item in rerun['checks']]


def test_diagnostics_redacts_secrets_from_details(fabric, monkeypatch):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)

        def boom(*_args, **_kwargs):
            raise ValueError('HTTP 401 api_key=sk-secretvalue1234 token=abcd')

        monkeypatch.setattr(ProviderClient, 'complete', boom)
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        blob = json.dumps(result)
        assert 'sk-secretvalue1234' not in blob
        assert 'api_key=[redacted]' in blob or '[redacted]' in blob
        assert 'secretvalue' not in blob
        assert safe_detail('password=hunter2') == 'password=[redacted]'


def test_chat_phrases_run_host_tools_without_a_model_call(fabric):
    with provider_server(lambda *_: answer('should not be called')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        seed_team(fabric, state)
        diagnostics = fabric.bots.send(state['home_bot_id'], {'body': 'Run a SynKraken diagnostics check.'})
        assert diagnostics['status'] == 'done'
        assert 'SynKraken diagnostics' in diagnostics['result']['deliveries'][-1]['body']
        assert all((item['body'].get('messages') or [{}])[-1].get('content') != 'Run a SynKraken diagnostics check.' for item in requests)
        health = fabric.bots.send(state['home_bot_id'], {'body': 'Show workspace health.'})
        assert health['status'] == 'done'
        assert 'Workspace health' in health['result']['deliveries'][-1]['body']
        failed = fabric.bots.send(state['home_bot_id'], {'body': 'Rerun failed SynKraken diagnostics checks.'})
        assert failed['status'] == 'done'
        assert all((item['body'].get('messages') or [{}])[-1].get('content') != 'Show workspace health.' for item in requests)
        assert all((item['body'].get('messages') or [{}])[-1].get('content') != 'Rerun failed SynKraken diagnostics checks.' for item in requests)


def test_browser_diagnostics_bind_origin_cards_and_request_same_run_resume(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        seed_team(fabric, state)
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        origin = next(item for item in result['checks'] if item['id'] == 'browser_origin')
        capability = next(item for item in result['checks'] if item['id'] == 'browser_capability')
        failure = next(item for item in result['checks'] if item['id'] == 'browser_failure')
        same_run = next(item for item in result['checks'] if item['id'] == 'same_run_continuation')
        assert origin['ok']
        assert capability['ok']
        assert failure['ok']
        assert same_run['ok']
        assert 'same-run resume requested' in same_run['detail']
        assert not any('Continue this request' in (run.get('body') or '') for run in fabric.storage.list_bot_runs(home['bot_id']))
        pending = [card for card in fabric.storage.chat_cards(home['bot_id']) if card['status'] == 'pending']
        researcher = next(bot for bot in fabric.bots.list() if bot['name'] == 'Researcher')
        pending += [card for card in fabric.storage.chat_cards(researcher['bot_id']) if card['status'] == 'pending']
        assert pending == []


def test_chat_ui_has_stable_test_hooks():
    from html.parser import HTMLParser

    class Markup(HTMLParser):
        def __init__(self):
            super().__init__()
            self.by_id = {}
            self.by_testid = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get('id'):
                self.by_id[attrs['id']] = attrs
            if attrs.get('data-testid'):
                self.by_testid[attrs['data-testid']] = attrs

    root = Path(__file__).resolve().parents[1] / 'synkraken' / 'static'
    html = (root / 'bots.html').read_text()
    js = (root / 'bots.js').read_text()
    markup = Markup()
    markup.feed(html)

    assert markup.by_id['workspace']['data-testid'] == 'synkraken-workspace'
    assert markup.by_id['workspace']['aria-label'] == 'SynKraken workspace'
    assert markup.by_id['roster']['data-testid'] == 'bot-roster'
    assert markup.by_id['roster']['aria-label'] == 'Bots'
    assert markup.by_id['message']['data-testid'] == 'chat-input'
    assert markup.by_id['message']['aria-label'] == 'Chat message'
    assert markup.by_id['send']['data-testid'] == 'send-message'
    assert markup.by_id['send']['aria-label'] == 'Send message'
    assert markup.by_id['composer']['data-testid'] == 'composer'
    assert markup.by_id['input-cards']['data-testid'] == 'input-cards'
    assert markup.by_testid['chat-input']['id'] == 'message'
    assert markup.by_testid['send-message']['id'] == 'send'

    assert markup.by_id['presence']['data-testid'] == 'run-status'
    assert markup.by_id['activity']['data-testid'] == 'activity'

    assert "node.setAttribute('data-testid', testId)" in js
    assert "hook(n, 'bot-'+slug(bot.name), 'Open conversation with '+bot.name)" in js
    assert "hook(details, 'run-activity', 'Activity')" in js
    assert "hook(card, 'card-capability')" in js
    assert "hook(card, 'card-origin')" in js
    assert "hook(card, item.kind==='credential'?'card-credential':'card-bot-change')" in js
    assert "'approve-bot-change'" in js
    assert "'dismiss-bot-change'" in js
    assert "hook(card, 'approvals-card', 'Pending approvals')" in js
    assert "block:'center'" in js
    assert "$('roster').replaceChildren()" not in js
    assert 'api_connection_reestablished' in js
    assert 'Continue this request' not in js
    assert 'synkraken.chat.selection' in js


def test_runtime_rules_keep_article_source_gate():
    from synkraken.bot_engine import RUNTIME_RULES
    assert 'shortlist' in RUNTIME_RULES
    assert 'adjudication' in RUNTIME_RULES
    assert 'hsdigital commentary' in RUNTIME_RULES
    assert 'Unpublished work stays internal' in RUNTIME_RULES


def test_capability_and_origin_cards_appear_in_the_same_conversation(fabric):
    def respond(body, n):
        if n == 1:
            return answer('', [call('request_capability', {
                'capability': 'browser', 'reason': 'Read the live article'})])
        return answer('', [call('browser_open', {'url': 'https://example.com'}, 'open-1')])

    with provider_server(respond) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        created = fabric.bots.workspace.host_tool(home, 'create_bot', {
            'name': 'Researcher', 'job': '', 'instructions': ''}, 'create-r')
        first = fabric.bots.send(created['bot_id'], {'body': 'Research the live article now'})
        assert first['status'] == 'waiting_for_user'
        convo = fabric.bots.conversation(created['bot_id'])
        cap = next(card for card in convo['cards'] if card['kind'] == 'capability' and card['status'] == 'pending')
        assert cap['reason'] and cap['capability'] == 'browser'
        assert cap['target_name'] == 'Researcher'
        assert cap['run_id'] == first['run_id']
        assert fabric.bots.workspace.card_is_renderable(cap)
        after = fabric.bots.workspace.resolve_card(cap['card_id'], {'approve': True})
        assert after['run']['run_id'] == first['run_id']
        origin = next(card for card in fabric.bots.conversation(created['bot_id'])['cards']
                      if card['kind'] == 'browser_access' and card['status'] == 'pending')
        assert origin['origin'] and origin['run_id'] == first['run_id']
        refreshed = fabric.bots.conversation(created['bot_id'])
        applied = [card for card in refreshed['cards'] if card['card_id'] == cap['card_id']]
        assert applied and applied[0]['status'] == 'applied'


def test_delegation_card_is_visible_on_host_and_chief(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        created = create_named_team(fabric, state)
        home_cards = fabric.bots.conversation(state['home_bot_id'])['cards']
        chief_cards = fabric.bots.conversation(created['Chief of Staff']['bot_id'])['cards']
        pending_home = [card for card in home_cards if card.get('grant') == 'chief_delegation' and card['status'] == 'pending']
        pending_chief = [card for card in chief_cards if card.get('grant') == 'chief_delegation' and card['status'] == 'pending']
        assert pending_home and pending_chief
        assert pending_home[0]['card_id'] == pending_chief[0]['card_id']
        assert fabric.bots.workspace.card_is_renderable(pending_home[0])
        fabric.bots.workspace.resolve_card(pending_home[0]['card_id'], {'approve': True})
        after = fabric.bots.conversation(state['home_bot_id'])['cards']
        applied = next(card for card in after if card['card_id'] == pending_home[0]['card_id'])
        assert applied['status'] == 'applied'


def test_pending_approvals_inbox_and_named_browser_approve(fabric):
    def respond(body, n):
        if n == 1:
            return answer('', [call('request_capability', {
                'capability': 'browser', 'reason': 'Read the live article'})])
        return answer('done')

    with provider_server(respond) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        created = fabric.bots.workspace.host_tool(home, 'create_bot', {
            'name': 'Researcher', 'job': '', 'instructions': ''}, 'create-r')
        first = fabric.bots.send(created['bot_id'], {'body': 'Research the live article now'})
        assert first['status'] == 'waiting_for_user'
        listed = fabric.bots.send(state['home_bot_id'], {'body': 'Show pending approvals.'})
        assert listed['status'] == 'done'
        body = listed['result']['deliveries'][-1]['body']
        assert 'Pending approvals' in body
        assert 'Researcher' in body
        assert 'resumes paused run' in body
        assert 'Approve or cancel' in body
        approved = fabric.bots.send(state['home_bot_id'], {'body': 'Approve the browser request for Researcher.'})
        assert approved['status'] == 'done'
        assert 'Approved the matching' in approved['result']['deliveries'][-1]['body']
        resumed = fabric.storage.get_bot_run(first['run_id'])
        assert resumed['run_id'] == first['run_id']
        assert resumed['status'] in {'done', 'waiting_for_user'}
        assert not any('Continue this request' in (run.get('body') or '')
                       for run in fabric.storage.list_bot_runs(created['bot_id']))
        inbox = fabric.bots.workspace.host_tool(home, 'pending_approvals', {}, 'inbox')
        kinds = {card['kind'] for card in inbox['pending']}
        assert 'capability' not in kinds or not any(
            card['kind'] == 'capability' and card['bot_name'] == 'Researcher' for card in inbox['pending'])


def test_ambiguous_approval_does_not_resolve(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        first = fabric.bots.workspace.host_tool(home, 'create_bot', {
            'name': 'Researcher', 'job': '', 'instructions': ''}, 'r1')
        fabric.bots.workspace.request_capability(
            fabric.bots.get(first['bot_id']), {'capability': 'browser', 'reason': 'one'}, 'run-a')
        fabric.bots.workspace.request_capability(
            fabric.bots.get(first['bot_id']), {'capability': 'memory', 'reason': 'two'}, 'run-b')
        result = fabric.bots.workspace.host_tool(
            home, 'resolve_approval', {'bot_name': 'Researcher', 'kind': 'capability'}, 'approve')
        assert result['resolved'] is False
        assert result['ambiguous'] is True
        pending = [card for card in fabric.storage.chat_cards(first['bot_id']) if card['status'] == 'pending']
        assert len(pending) == 2


def test_rerun_failed_does_not_wipe_previous_when_nothing_failed(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        seed_team(fabric, state)
        home = fabric.bots.get(state['home_bot_id'])
        first = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        assert first['ok']
        assert all(check.get('status') == ('pass' if check['ok'] else 'fail') for check in first['checks'])
        assert all(check.get('run_id') and check.get('timestamp') for check in first['checks'])
        stored = fabric.bots.workspace.state()['last_diagnostics']
        assert stored['checks'] == first['checks']
        assert stored['failed'] == []
        rerun = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'failed'}, 'diag-failed')
        assert rerun['checks'] == []
        assert fabric.bots.workspace.state()['last_diagnostics']['checks'] == first['checks']


def test_card_visibility_detects_waiting_run_without_card(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        home = fabric.bots.get(state['home_bot_id'])
        run = {'run_id': 'orphan-wait', 'bot_id': home['bot_id'], 'request_key': 'orphan',
               'body': 'wait', 'status': 'waiting_for_user', 'created_at': '2026-01-01T00:00:00Z',
               'updated_at': '2026-01-01T00:00:00Z'}
        fabric.storage.save_bot_run(run)
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        visibility = next(item for item in result['checks'] if item['id'] == 'card_visibility')
        assert visibility['ok'] is False
        assert visibility['status'] == 'fail'
        events = fabric.storage.bot_run_events('orphan-wait')
        assert any(event['event_type'] == 'card_render_mismatch' for event in events)


def test_minimax_assignment_status_matches_saved_models(fabric):
    with provider_server(lambda *_: answer('OK')) as (endpoint, requests):
        state = bootstrap(fabric, endpoint)
        created = seed_team(fabric, state)
        fabric.bots.save({'model': 'other-model'}, created['Writer']['bot_id'])
        home = fabric.bots.get(state['home_bot_id'])
        result = fabric.bots.workspace.host_tool(home, 'run_diagnostics', {'scope': 'all'}, 'diag')
        minimax = next(item for item in result['checks'] if item['id'] == 'minimax_assignment')
        assert minimax['ok'] is False
        assert minimax['status'] == 'fail'
        assert 'all six team bots use MiniMax-M3' not in minimax['detail']
        assert 'Writer=other-model' in minimax['detail']
        persisted = next(item for item in fabric.bots.workspace.state()['last_diagnostics']['checks']
                         if item['id'] == 'minimax_assignment')
        assert persisted == minimax
