from __future__ import annotations

import pytest

from test_chat_workspace import fabric, bootstrap
from test_bot_engine import provider_server, answer, call
from synkraken.bot_engine import TOOLS


def test_null_optional_creation_fields_are_normalized(fabric):
    def respond(body, n):
        return answer('', [call('create_bot', {'name': 'Research', 'job': None, 'instructions': None})]) if n == 1 else answer('Created Research.')
    with provider_server(respond) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'Create a bot called Research'})
    assert result['status'] == 'done'
    child = next(bot for bot in fabric.bots.list() if bot['name'] == 'Research')
    assert child['instructions'] == child['job'] == ''


def test_role_change_needs_a_saved_configuration_card_not_browser(fabric):
    def respond(body, n):
        if n == 1:
            return answer("I don't have live browser access, but I am your chief of staff now.")
        args = {key: '' for key in next(t for t in TOOLS if t['name'] == 'configure_bot')['parameters']['properties']}
        args.update(bot_id=state['home_bot_id'], job='Chief of staff', instructions='Coordinate the team and report to the user.')
        return answer('', [call('configure_bot', args)])
    with provider_server(respond) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'You are my chief of staff. Remember this role.'})
    assert result['status'] == 'waiting_for_user'
    cards = fabric.storage.chat_cards(state['home_bot_id'])
    assert len(cards) == 1 and cards[0]['kind'] == 'bot_change'
    fabric.bots.workspace.resolve_card(cards[0]['card_id'], {'approve': True})
    assert fabric.bots.get(state['home_bot_id'])['job'] == 'Chief of staff'


def test_secure_card_prose_without_action_is_retried(fabric):
    def respond(body, n):
        return answer('The secure entry card is ready.') if n == 1 else answer('', [call('request_secret', {'service': 'QA', 'purpose': 'Test'})])
    with provider_server(respond) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'Show a secure entry card for QA'})
    assert result['status'] == 'waiting_for_user'
    assert len(requests) == 2
    assert fabric.storage.chat_cards(state['home_bot_id'])[0]['kind'] == 'credential'


def test_delegation_configuration_card_applies_allowed_target(fabric):
    with provider_server(lambda *_: answer('OK')) as (url, requests):
        state = bootstrap(fabric, url)
        home = fabric.bots.get(state['home_bot_id'])
        child = fabric.bots.workspace.host_tool(home, 'create_bot', {'name': 'Worker', 'job': '', 'instructions': ''}, 'create-worker')
        args = {'bot_id': home['bot_id'], 'delegate_to': child['bot_id'], 'tools': 'bots_list,delegate_bot'}
        card = fabric.bots.workspace.host_tool(home, 'configure_bot', args, 'configure-worker')
        fabric.bots.workspace.resolve_card(card['card_id'], {'approve': True})
        assert fabric.bots.get(home['bot_id'])['delegate_to'] == [child['bot_id']]


def test_explicit_create_tool_request_cannot_claim_success_without_receipt(fabric):
    with provider_server(lambda *_: answer('Done. QA Native is ready.')) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'Use create_bot now to create QA Native.'})
    assert result['status'] == 'blocked'
    assert requests[-1]['body']['tool_choice'] == {'type': 'function', 'function': {'name': 'create_bot'}}
    assert not any(b['name'] == 'QA Native' for b in fabric.bots.list())


def test_how_to_create_question_does_not_force_creation(fabric):
    with provider_server(lambda *_: answer('Describe the bot you want in chat.')) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'How do I create a bot?'})
    assert result['status'] == 'done'
    assert not any(bot['name'] == 'QA Native' for bot in fabric.bots.list())


def test_anthropic_repair_requests_specific_tool():
    from synkraken.providers import ProviderClient
    client = ProviderClient({'protocol': 'anthropic', 'base_url': 'https://api.minimax.io/anthropic/v1'}, 'test-only')
    captured = []
    def request(path, payload, timeout):
        captured.append(payload)
        return {'content': [{'type': 'tool_use', 'id': 'c1', 'name': 'create_bot', 'input': {'name': 'QA', 'job': '', 'instructions': ''}}], 'stop_reason': 'tool_use'}
    client.request = request
    schema = next(t for t in TOOLS if t['name'] == 'create_bot')
    reply = client.complete('test', [{'role': 'user', 'content': 'Create QA'}], [schema], 2, required_tool='create_bot')
    assert captured[0]['tool_choice'] == {'type': 'tool', 'name': 'create_bot'}
    assert reply.message['tool_calls'][0]['function']['name'] == 'create_bot'


def test_action_repair_excludes_unverified_assistant_prose(fabric):
    def respond(body, n):
        if n == 1:
            return answer('QA Native was created and is ready in your sidebar.')
        if n > 2:
            return answer('Created.')
        return answer('', [call('create_bot', {'name': 'QA Native', 'job': '', 'instructions': ''})])
    with provider_server(respond) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'Create a bot called QA Native'})
    assert result['status'] == 'done'
    assert any(bot['name'] == 'QA Native' for bot in fabric.bots.list())


def test_workspace_roster_reply_uses_tool_authority(fabric):
    def respond(body, n):
        if n == 1:
            return answer('', [call('workspace_bots', {})])
        return answer('Saved bots: SynKraken, Scout, Pa, QA Native.')
    with provider_server(respond) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(state['home_bot_id'], {'body': 'Call workspace_bots and report saved bot names.'})
    assert result['status'] == 'done'
    body = result['result']['deliveries'][-1]['body']
    assert 'QA Native' not in body
    assert body.strip().endswith('- SynKraken')


def test_workspace_roster_is_precomputed_when_model_skips_tool(fabric):
    with provider_server(lambda *_: answer('Saved bots: QA Native, Daily Driver Check.')) as (url, requests):
        state = bootstrap(fabric, url)
        result = fabric.bots.send(
            state['home_bot_id'],
            {'body': 'Call workspace_bots and report only the currently saved bot names.'},
        )
    assert result['status'] == 'done'
    body = result['result']['deliveries'][-1]['body']
    assert body.strip().endswith('- SynKraken')
    assert 'QA Native' not in body and 'Daily Driver Check' not in body
    assert requests == []
