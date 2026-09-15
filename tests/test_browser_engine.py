from __future__ import annotations

import pytest

from synkraken.browser_engine import origin_of, public_url
from test_bot_engine import answer, call, provider_server
from test_chat_workspace import bootstrap
from synkraken.fabric import AgentFabric
from synkraken.storage import Storage


@pytest.fixture
def fabric(tmp_path):
    value = AgentFabric({'adapters': {}, 'routing': {}, 'engine': {
        'browser_test_origins': ['http://127.0.0.1:12345']}}, Storage(tmp_path / 'browser.db'))
    yield value
    value.bots.browsers.close()
    value.bots._executor.shutdown(wait=True)
    value.storage._conn.close()


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'javascript:alert(1)', 'https://user:password@example.com', 'data:text/html,x'])
def test_browser_rejects_non_web_and_credential_urls(url):
    with pytest.raises(ValueError):
        origin_of(url)


@pytest.mark.parametrize('url', ['http://127.0.0.1:9460', 'http://169.254.169.254/latest', 'http://[::1]:9460'])
def test_browser_cannot_reach_private_control_services(url):
    assert not public_url(url)


def test_browser_access_is_explicit_per_bot_and_idempotent(fabric, monkeypatch):
    state = bootstrap(fabric, 'http://localhost:1234/v1')
    bot_id = state['home_bot_id']
    browser = fabric.bots.browsers
    first = browser.act(bot_id, 'open', {'url': 'http://127.0.0.1:12345/example'})
    again = browser.act(bot_id, 'open', {'url': 'http://127.0.0.1:12345/example'})
    assert first['card_id'] == again['card_id']
    assert browser.view(bot_id) == {'open': False}
    fabric.bots.workspace.resolve_card(first['card_id'], {'approve': True})
    assert browser.permitted_origins(bot_id) == ['http://127.0.0.1:12345']
    other = fabric.bots.save({'name': 'Other', 'provider_id': state['default_provider_id'], 'model': 'test', 'tools': []})
    assert browser.permitted_origins(other['bot_id']) == []
    monkeypatch.setattr(browser, '_act', lambda *args: {'open': True, 'url': args[2]['url']})
    assert browser.act(bot_id, 'open', {'url': 'http://127.0.0.1:12345/example'})['open']


def test_label_is_metadata_and_does_not_change_instructions(fabric):
    state = bootstrap(fabric, 'http://localhost:1234/v1')
    bot = fabric.bots.save({'label': 'Research'}, state['home_bot_id'])
    assert bot['label'] == 'Research'
    assert bot['job'] == bot['instructions'] == ''


PAGE = 'http://127.0.0.1:12345/article'


def _researcher(fabric, endpoint):
    state = bootstrap(fabric, endpoint)
    home = fabric.bots.get(state['home_bot_id'])
    created = fabric.bots.workspace.host_tool(home, 'create_bot', {
        'name': 'Researcher', 'job': 'Research live sources', 'instructions': ''}, 'create')
    return created['bot_id']


def test_capability_and_origin_cards_resume_the_same_run(fabric, monkeypatch):
    monkeypatch.setattr(fabric.bots.browsers, '_act', lambda bot_id, action, args, budget=None: {
        'open': True, 'url': args.get('url', PAGE), 'title': 'Article',
        'text': 'Verified page text about the topic.'})

    def respond(body, n):
        if n == 1:
            return answer('', [call('request_capability', {
                'capability': 'browser', 'reason': 'Read the live article'})])
        assert [m['content'] for m in body['messages'] if m['role'] == 'user'][-1] == 'Research the live article now'
        if n == 2:
            assert body.get('tool_choice') == {'type': 'function', 'function': {'name': 'browser_open'}}
            return answer('', [call('browser_open', {'url': PAGE}, 'open-1')])
        return answer('From the open page: Verified page text about the topic.')

    with provider_server(respond) as (endpoint, requests):
        bot_id = _researcher(fabric, endpoint)
        first = fabric.bots.send(bot_id, {'body': 'Research the live article now'})
        assert first['status'] == 'waiting_for_user'
        run_id = first['run_id']
        cap = next(c for c in fabric.storage.chat_cards(bot_id) if c['kind'] == 'capability')
        after_cap = fabric.bots.workspace.resolve_card(cap['card_id'], {'approve': True})
        assert after_cap['run']['run_id'] == run_id
        assert after_cap['status'] == 'waiting_for_user'
        assert 'browser_open' in fabric.bots.get(bot_id)['tools']
        origin = next(c for c in fabric.storage.chat_cards(bot_id)
                      if c['kind'] == 'browser_access' and c['status'] == 'pending')
        assert origin['run_id'] == run_id
        after_origin = fabric.bots.workspace.resolve_card(origin['card_id'], {'approve': True})
        assert after_origin['run']['run_id'] == run_id
        assert after_origin['status'] == 'done'
        assert 'Verified page text about the topic' in after_origin['run']['result']
        assert [run['run_id'] for run in fabric.storage.list_bot_runs(bot_id)] == [run_id]
        assert len(requests) == 3


def test_dismissing_a_capability_card_does_not_resume_the_run(fabric):
    with provider_server(lambda *_: answer('', [call('request_capability', {
            'capability': 'browser', 'reason': 'research'})])) as (endpoint, requests):
        bot_id = _researcher(fabric, endpoint)
        first = fabric.bots.send(bot_id, {'body': 'Research the live article now'})
        cap = next(c for c in fabric.storage.chat_cards(bot_id) if c['kind'] == 'capability')
        fabric.bots.workspace.resolve_card(cap['card_id'], {'cancel': True})
        assert fabric.storage.get_bot_run(first['run_id'])['status'] == 'waiting_for_user'
        assert len(requests) == 1
        assert 'browser_open' not in fabric.bots.get(bot_id)['tools']


def test_origin_approval_does_not_fabricate_when_browser_fails(fabric, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('Browser runtime is unavailable. Install synkraken[browser] and run python -m playwright install chromium')

    monkeypatch.setattr(fabric.bots.browsers, '_act', fail)

    def respond(body, n):
        if n == 1:
            return answer('', [call('request_capability', {
                'capability': 'browser', 'reason': 'Read the live article'})])
        return answer('', [call('browser_open', {'url': PAGE}, 'open-1')])

    with provider_server(respond) as (endpoint, requests):
        bot_id = _researcher(fabric, endpoint)
        first = fabric.bots.send(bot_id, {'body': 'Research the live article now'})
        cap = next(c for c in fabric.storage.chat_cards(bot_id) if c['kind'] == 'capability')
        after_cap = fabric.bots.workspace.resolve_card(cap['card_id'], {'approve': True})
        origin = next(c for c in fabric.storage.chat_cards(bot_id) if c['kind'] == 'browser_access')
        after_origin = fabric.bots.workspace.resolve_card(origin['card_id'], {'approve': True})
        assert after_origin['run']['run_id'] == first['run_id']
        assert after_origin['status'] == 'done'
        assert 'could not open' in after_origin['run']['result'].lower()
        assert 'unavailable' in after_origin['run']['result'].lower()
        assert 'verified page' not in after_origin['run']['result'].lower()
        assert len(requests) == 2
        assert after_cap['status'] == 'waiting_for_user'
