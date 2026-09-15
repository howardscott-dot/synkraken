from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import stat
from threading import Event, Thread
import time

import pytest

from synkraken.bot_engine import RunBudget
from synkraken.fabric import AgentFabric
from synkraken.providers import ProviderError
from synkraken.storage import Storage


@contextmanager
def provider_server(respond):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = {"data": [{"id": "test-model"}]}
            self.reply(data)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
            self.reply(respond(body, len(requests)))

        def reply(self, data):
            payload = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()


def answer(text="Finished", calls=None):
    return {"choices": [{"message": {"role": "assistant", "content": text,
                                      **({"tool_calls": calls} if calls else {})},
                         "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def call(name, args, call_id="call-1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.fixture
def fabric(tmp_path):
    storage = Storage(tmp_path / "engine.db")
    value = AgentFabric({"adapters": {}, "routing": {}}, storage)
    yield value
    value.bots._executor.shutdown(wait=True)
    storage._conn.close()


def native_bot(fabric, endpoint, protocol="openai_compatible", **fields):
    provider = fabric.bots.providers.save({"name": protocol, "protocol": protocol, "base_url": endpoint})
    return fabric.bots.save({"name": "Helper", "job": "Help with work", "provider_id": provider["provider_id"],
                             "model": "test-model", **fields})


def wait_run(fabric, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = fabric.storage.get_bot_run(run_id)
        if run["status"] in {"done", "blocked", "cancelled", "interrupted"}:
            return run
        time.sleep(.01)
    raise AssertionError("Run did not finish")


def test_native_loop_executes_tools_and_persists_memory_and_usage(fabric):
    def respond(body, count):
        if count == 1:
            return answer("", [call("memory_write", {"key": "preference", "body": "Use concise prose"}),
                               call("write_file", {"path": "draft.txt", "content": "Useful draft"}, "call-2")])
        assert [item["role"] for item in body["messages"]][-3:] == ["assistant", "tool", "tool"]
        return answer("Saved the draft and preference")

    with provider_server(respond) as (endpoint, requests):
        bot = native_bot(fabric, endpoint)
        result = fabric.bots.send(bot["bot_id"], {"body": "Write a draft and remember my preference"})
    assert result["status"] == "done"
    assert len(requests) == 2
    assert fabric.storage.read_bot_memory(bot["bot_id"])[0]["body"] == "Use concise prose"
    assert fabric.bots.engine.workspace_path(bot["bot_id"], "draft.txt").read_text() == "Useful draft"
    events = fabric.storage.bot_run_events(result["run_id"])
    assert sum(event["event_type"] == "tool_finished" for event in events) == 2
    assert any(event["data"].get("usage", {}).get("total_tokens") == 15 for event in events)
    assert fabric.storage.get_task(result["task_id"])["status"] == "done"


def test_anthropic_native_tool_round_trip(fabric):
    def respond(body, count):
        assert body["model"] == "test-model" and body["system"]
        if count == 1:
            assert body["tools"][0]["input_schema"]["type"] == "object"
            return {"content": [{"type": "tool_use", "id": "tool-1", "name": "memory_read", "input": {}}],
                    "stop_reason": "tool_use", "usage": {"input_tokens": 20, "output_tokens": 3}}
        assert body["messages"][-1]["content"][0]["tool_use_id"] == "tool-1"
        assert body["messages"][-2]["content"][0]["type"] == "tool_use"
        return {"content": [{"type": "text", "text": "Memory checked"}], "stop_reason": "end_turn"}

    with provider_server(respond) as (endpoint, requests):
        bot = native_bot(fabric, endpoint, "anthropic")
        result = fabric.bots.send(bot["bot_id"], {"body": "Read memory"})
    assert result["status"] == "done"
    assert requests[0]["path"] == "/v1/messages"
    assert requests[0]["headers"]["Anthropic-Version"] == "2023-06-01"


def test_bots_delegate_across_two_provider_protocols(fabric):
    child_calls = []

    def child_response(body, count):
        child_calls.append(body)
        return {"content": [{"type": "text", "text": "Specialist result"}], "stop_reason": "end_turn"}

    with provider_server(child_response) as (child_url, _):
        child = native_bot(fabric, child_url, "anthropic", name="Specialist", model="specialist-model")

        def parent_response(body, count):
            if count == 1:
                return answer("", [call("delegate_bot", {"bot_id": child["bot_id"], "prompt": "Investigate this"})])
            assert "Specialist result" in body["messages"][-1]["content"]
            return answer("Combined result")

        with provider_server(parent_response) as (parent_url, _):
            parent = native_bot(fabric, parent_url, tools=["delegate_bot", "bots_list"], delegate_to=[child["bot_id"]])
            result = fabric.bots.send(parent["bot_id"], {"body": "Delegate to the specialist"})
    assert result["status"] == "done"
    assert child_calls[0]["model"] == "specialist-model"
    child_run = fabric.storage.list_bot_runs(child["bot_id"])[0]
    assert child_run["parent_run_id"] == result["run_id"]
    assert child_run["status"] == "done"


def test_background_run_deduplicates_and_cancels_before_tool_side_effect(fabric):
    started, release = Event(), Event()

    def respond(body, count):
        started.set()
        release.wait(3)
        return answer("", [call("write_file", {"path": "should-not-exist", "content": "bad"})])

    with provider_server(respond) as (endpoint, requests):
        bot = native_bot(fabric, endpoint)
        payload = {"body": "Do work", "request_key": "one-request"}
        run = fabric.bots.submit(bot["bot_id"], payload)
        assert started.wait(2)
        assert fabric.bots.submit(bot["bot_id"], payload)["run_id"] == run["run_id"]
        with pytest.raises(ValueError, match="another message"):
            fabric.bots.submit(bot["bot_id"], {**payload, "body": "Other work"})
        assert fabric.bots.cancel(run["run_id"])["cancellation_requested"]
        release.set()
        assert wait_run(fabric, run["run_id"])["status"] == "cancelled"
    assert len(requests) == 1
    assert not fabric.bots.engine.workspace_path(bot["bot_id"], "should-not-exist").exists()


def test_scope_permissions_and_cycles_are_enforced(fabric, tmp_path):
    bot = native_bot(fabric, "http://localhost:12345/v1", tools=["read_file", "memory_read", "delegate_bot"])
    other = native_bot(fabric, "http://localhost:12345/v1", name="Other")
    fabric.storage.write_bot_memory(other["bot_id"], "private", "other bot memory")
    engine = fabric.bots.engine
    budget = RunBudget()
    assert engine.execute_tool(bot, "memory_read", {}, "unused", budget, ()) == {"memories": []}
    with pytest.raises(ValueError, match="not permitted"):
        engine.execute_tool(bot, "write_file", {"path": "a", "content": "b"}, "unused", budget, ())
    with pytest.raises(ValueError, match="escapes"):
        engine.workspace_path(bot["bot_id"], "../../private")
    root = engine.workspace_path(bot["bot_id"], ".")
    (root / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        engine.workspace_path(bot["bot_id"], "escape/private")
    bot["delegate_to"] = [other["bot_id"]]
    with pytest.raises(ValueError, match="cycle"):
        engine.execute_tool(bot, "delegate_bot", {"bot_id": other["bot_id"], "prompt": "loop"},
                            "unused", budget, (other["bot_id"], bot["bot_id"]))


def test_credentials_are_separate_and_model_discovery_is_explicit(fabric):
    with provider_server(lambda body, count: answer()) as (endpoint, requests):
        provider = fabric.bots.providers.save({"name": "Private", "protocol": "openai_compatible",
                                               "base_url": endpoint, "api_key": "test-private-key"})
        assert "test-private-key" not in json.dumps(fabric.bots.providers.list())
        assert "test-private-key" not in json.dumps(fabric.storage.list_providers())
        path = fabric.bots.providers.credentials / (provider["provider_id"] + ".enc")
        assert "test-private-key" not in path.read_text()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert fabric.bots.providers.probe(provider["provider_id"])["models"] == ["test-model"]
        fabric.bots.providers.client(provider["provider_id"]).complete("test-model", [{"role": "user", "content": "hi"}], [], 2)
        assert requests[0]["headers"]["Authorization"] == "Bearer test-private-key"
        with pytest.raises(ValueError, match="new key"):
            fabric.bots.providers.save({"base_url": "https://different.example/v1"}, provider["provider_id"])


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://user:secret@api.example", "https://api.example?key=secret"])
def test_invalid_provider_urls_rejected(fabric, url):
    with pytest.raises(ValueError):
        fabric.bots.providers.save({"name": "Invalid", "protocol": "openai_compatible", "base_url": url})


def test_missing_credentials_do_not_route_elsewhere(fabric):
    bot = native_bot(fabric, "https://api.example/v1")
    result = fabric.bots.send(bot["bot_id"], {"body": "Work"})
    assert result["status"] == "blocked"
    assert "API key is missing" in result["result"]["deliveries"][0]["error"]


def test_restart_marks_unfinished_runs_without_replaying(fabric):
    bot = native_bot(fabric, "http://localhost:12345/v1")
    run = fabric.bots._new_run(bot["bot_id"], "unfinished", "restart-test")
    fabric.storage.interrupt_bot_runs()
    assert fabric.storage.get_bot_run(run["run_id"])["status"] == "interrupted"
    assert fabric.storage.find_bot_run(bot["bot_id"], "restart-test")["run_id"] == run["run_id"]


def test_loop_limit_reports_failure_instead_of_claiming_success(fabric):
    with provider_server(lambda body, count: answer("", [call("memory_read", {}, f"call-{count}")])) as (endpoint, requests):
        bot = native_bot(fabric, endpoint, tools=["memory_read"])
        result = fabric.bots.send(bot["bot_id"], {"body": "Work"})
    assert result["status"] == "blocked"
    assert len(requests) == 16
    assert "16-step limit" in result["result"]["deliveries"][0]["error"]


def test_shared_budget_limits_model_calls():
    budget = RunBudget()
    for _ in range(24):
        budget.consume("model")
    with pytest.raises(ProviderError, match="budget"):
        budget.consume("model")


@pytest.mark.parametrize('response', [
    {'choices': [{'message': []}]},
    answer(calls=[{'id': 'bad', 'function': ['invalid']}]),
    {**answer(), 'usage': {'input_tokens': None}},
])
def test_malformed_provider_reply_is_visible_failure(fabric, response):
    with provider_server(lambda *_: response) as (endpoint, _):
        bot = native_bot(fabric, endpoint)
        result = fabric.bots.send(bot['bot_id'], {'body': 'Hello'})
        assert result['status'] == 'blocked'
        assert fabric.storage.get_bot_run(result['run_id'])['status'] == 'blocked'
        assert result['result']['deliveries'][0]['ok'] is False


def test_native_http_routes_are_authenticated_and_idempotent(fabric):
    from synkraken.api import FabricRequestHandler
    from test_bots import request

    class Handler(FabricRequestHandler):
        auth_token = 'test-token'

        def log_message(self, *args):
            pass

    Handler.fabric = fabric
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    try:
        with provider_server(lambda *_: answer()) as (endpoint, _):
            assert request(port, '/v1/providers', token='wrong')[0] == 401
            status, body = request(port, '/v1/providers', 'POST', {
                'name': 'HTTP test', 'protocol': 'openai_compatible', 'base_url': endpoint})
            assert status == 200
            provider = json.loads(body)['provider']
            assert request(port, f"/v1/providers/{provider['provider_id']}/probe", 'POST', {})[0] == 200
            _, body = request(port, '/v1/bots', 'POST', {
                'name': 'HTTP bot', 'job': 'Test', 'provider_id': provider['provider_id'], 'model': 'test-model'})
            bot = json.loads(body)['bot']
            route = f"/v1/bots/{bot['bot_id']}/runs"
            status, body = request(port, route, 'POST', {'body': 'Hello', 'request_key': 'same-request'})
            assert status == 200
            run = json.loads(body)['run']
            assert wait_run(fabric, run['run_id'])['status'] == 'done'
            _, repeated = request(port, route, 'POST', {'body': 'Hello', 'request_key': 'same-request'})
            assert json.loads(repeated)['run']['run_id'] == run['run_id']
            run_route = f"/v1/bot-runs/{run['run_id']}"
            assert request(port, run_route, token='wrong')[0] == 401
            assert request(port, run_route)[0] == 200
            assert request(port, run_route + '/cancel', 'POST', {}, token='wrong')[0] == 401
            assert request(port, route, 'POST', {'body': 'Different', 'request_key': 'same-request'})[0] == 400
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('host,expected', [
    ('https://api.minimax.io/anthropic/v1', 'Subscription Key'),
    ('https://api.other.example/v1', 'billing or credit limit'),
])
def test_payment_error_is_actionable_without_exposing_provider_body(monkeypatch, host, expected):
    import io
    from urllib.error import HTTPError
    from synkraken import providers

    class Denied:
        def open(self, *args, **kwargs):
            raise HTTPError(host, 402, 'Payment required', {}, io.BytesIO(b'secret-key-in-untrusted-error'))

    monkeypatch.setattr(providers, 'build_opener', lambda *_: Denied())
    client = providers.ProviderClient({'protocol': 'anthropic', 'base_url': host}, 'test-key')
    with pytest.raises(providers.ProviderError) as caught:
        client.request('/messages', {}, 1)
    assert expected in str(caught.value)
    assert 'secret-key' not in str(caught.value)


@pytest.mark.parametrize("failed", [False, True])
def test_native_delegation_reuses_runtime_fabric(fabric, failed):
    from test_bots import RecordingAdapter
    adapter = RecordingAdapter("research-runtime")
    adapter.fail = failed
    fabric.retry_limit = 0
    fabric.adapters[adapter.adapter_id] = adapter
    fabric.storage.sync_agents([adapter.health()])
    worker = fabric.bots.save({"name": "Research worker", "runtime_id": adapter.adapter_id})

    def respond(body, count):
        if count == 1:
            return answer("", [call("delegate_bot", {"bot_id": worker["bot_id"], "prompt": "Check current sources"})])
        receipt = json.loads(body["messages"][-1]["content"])
        assert receipt["status"] == ("blocked" if failed else "done")
        assert receipt["error"] == ("runtime unavailable" if failed else None)
        return answer("Research failed" if failed else receipt["reply"])

    with provider_server(respond) as (endpoint, requests):
        parent = native_bot(fabric, endpoint, tools=["delegate_bot"], delegate_to=[worker["bot_id"]])
        budget = RunBudget()
        result = fabric.bots.send(parent["bot_id"], {"body": "Research this"}, _budget=budget)
    assert len(adapter.messages) == 1
    delivered = adapter.messages[0]
    assert delivered.source == "bot:" + parent["bot_id"]
    assert delivered.metadata["parent_run_id"] == result["run_id"]
    child_run = fabric.storage.get_bot_run(delivered.metadata["run_id"])
    assert child_run["parent_run_id"] == result["run_id"]
    assert child_run["status"] == ("blocked" if failed else "done")
    assert budget.requests == 3
    assert fabric.bots.get(parent["bot_id"])["provider_id"] == parent["provider_id"]
    forbidden = dict(parent, delegate_to=[])
    with pytest.raises(ValueError, match="not allowed"):
        fabric.bots.engine.execute_tool(forbidden, "delegate_bot", {"bot_id": worker["bot_id"], "prompt": "No"},
                                        result["run_id"], RunBudget(), ())
    assert len(adapter.messages) == 1
