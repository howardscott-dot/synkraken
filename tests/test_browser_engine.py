from __future__ import annotations

import pytest

from synkraken.browser_engine import origin_of, public_url
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
