from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import json
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from synkraken.adapters.base import BaseAdapter
from synkraken.api import FabricRequestHandler
from synkraken.bots import BotBusyError
from synkraken.fabric import AgentFabric
from synkraken.models import AdapterReply, FabricMessage
from synkraken.storage import Storage
from synkraken.web import CommandDeckHandler


class RecordingAdapter(BaseAdapter):
    def __init__(self, adapter_id):
        super().__init__(adapter_id, {"type": "test"})
        self.messages = []
        self.fail = False
        self.started = Event()
        self.release = Event()
        self.release.set()

    def send(self, message):
        self.messages.append(message)
        self.started.set()
        self.release.wait(3)
        return AdapterReply(self.adapter_id, not self.fail, "A useful reply" if not self.fail else "",
                            error="runtime unavailable" if self.fail else None)


@pytest.fixture
def fabric(tmp_path):
    config = {"adapters": {name: {"type": "ollama", "model": model} for name, model in
                           [("local", "local-model"), ("remote", "other-model")]},
              "routing": {"retry_limit": 0}}
    storage = Storage(tmp_path / "bots.db")
    fabric = AgentFabric(config, storage)
    fabric.adapters = {name: RecordingAdapter(name) for name in config["adapters"]}
    yield fabric
    storage._conn.close()


def create(fabric, **fields):
    return fabric.bots.save({"name": "Research", "job": "Investigate questions", "runtime_id": "local", **fields})


def test_identity_context_and_history_survive_rebinding_and_restart(fabric):
    bot = create(fabric, notes="Prefer primary evidence")
    first = fabric.bots.send(bot["bot_id"], {"body": "First question"})
    assert first["status"] == "done"
    assert first["result"]["message"]["body"] == "First question"
    assert "Prefer primary evidence" in fabric.adapters["local"].messages[0].body
    assert fabric.storage.get_task(first["task_id"])["source_message_id"]
    changed = fabric.bots.save({"runtime_id": "remote"}, bot["bot_id"])
    assert changed["conversation_id"] == bot["conversation_id"]
    fabric.bots.send(bot["bot_id"], {"body": "Second question"})
    prompt = fabric.adapters["remote"].messages[0].body
    assert "First question" in prompt and "A useful reply" in prompt
    reopened = Storage(fabric.storage.sqlite_path)
    try:
        fresh = AgentFabric(fabric.config, reopened)
        assert fresh.bots.get(bot["bot_id"])["notes"] == "Prefer primary evidence"
        assert len(fresh.bots.conversation(bot["bot_id"])["messages"]) == 4
        assert len(reopened._conn.execute("SELECT * FROM bot_profile_events").fetchall()) == 2
    finally:
        reopened._conn.close()


def test_two_bots_share_runtime_without_injecting_each_others_context(fabric):
    first = create(fabric, notes="ONLY_FIRST_BOT")
    second = create(fabric, name="Writer", notes="ONLY_SECOND_BOT")
    fabric.bots.send(first["bot_id"], {"body": "FIRST_BOT_PRIVATE_QUESTION"})
    fabric.bots.send(second["bot_id"], {"body": "Draft a title"})
    prompt = fabric.adapters["local"].messages[-1].body
    assert "ONLY_SECOND_BOT" in prompt
    assert "ONLY_FIRST_BOT" not in prompt and "FIRST_BOT_PRIVATE_QUESTION" not in prompt


def test_failure_is_persisted_with_blocked_task(fabric):
    bot = create(fabric)
    fabric.adapters["local"].fail = True
    result = fabric.bots.send(bot["bot_id"], {"body": "Try work"})
    assert result["status"] == "blocked"
    assert fabric.storage.get_task(result["task_id"])["status"] == "blocked"
    conversation = fabric.bots.conversation(bot["bot_id"])
    assert conversation["messages"][-1]["error"] == "runtime unavailable"
    assert conversation["activity"][-1]["task_id"] == result["task_id"]
    assert fabric.bots.get(bot["bot_id"])["status"] == "blocked"


def test_busy_bot_rejects_overlapping_turn_and_edit(fabric):
    bot = create(fabric)
    runtime = fabric.adapters["local"]
    runtime.release.clear()
    with ThreadPoolExecutor() as executor:
        result = executor.submit(fabric.bots.send, bot["bot_id"], {"body": "Long work"})
        assert runtime.started.wait(2)
        assert fabric.bots.get(bot["bot_id"])["status"] == "working"
        with pytest.raises(BotBusyError):
            fabric.bots.send(bot["bot_id"], {"body": "Overlapping work"})
        with pytest.raises(BotBusyError):
            fabric.bots.save({"runtime_id": "remote"}, bot["bot_id"])
        runtime.release.set()
        assert result.result()["status"] == "done"


def test_missing_runtime_does_not_silently_fall_back(fabric):
    bot = create(fabric)
    del fabric.adapters["local"]
    assert fabric.bots.get(bot["bot_id"])["status"] == "unavailable"
    with pytest.raises(ValueError, match="unavailable"):
        fabric.bots.send(bot["bot_id"], {"body": "Work"})
    assert fabric.adapters["remote"].messages == []


def test_accepted_turn_without_delivery_is_reported_as_interrupted(fabric):
    bot = create(fabric)
    fabric.storage.save_message(FabricMessage(
        "operator", "local", "Interrupted request", conversation_id=bot["conversation_id"],
    ).normalized())
    assert fabric.bots.get(bot["bot_id"])["status"] == "interrupted"


def test_additive_schema_keeps_legacy_conversation(tmp_path):
    path = tmp_path / "legacy.db"
    original = Storage(path)
    message = FabricMessage("operator", "runtime", "Existing work").normalized()
    original.save_message(message)
    original._conn.executescript("DROP TABLE bot_profile_events; DROP TABLE bot_profiles;")
    original._conn.close()
    upgraded = Storage(path)
    try:
        assert upgraded.get_message(message.message_id)["body"] == "Existing work"
        assert upgraded.list_bots() == []
    finally:
        upgraded._conn.close()


@pytest.mark.parametrize("payload", [[], {"name": ""}, {"name": 1}, {"notes": "x" * 4001},
                                      {"runtime_id": "missing"}, {"api_key": "secret"}])
def test_invalid_profiles_are_rejected(fabric, payload):
    bot = create(fabric)
    with pytest.raises(ValueError):
        fabric.bots.save(payload, bot["bot_id"])


def request(port, path, method="GET", payload=None, token="test-token"):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    req = Request(f"http://127.0.0.1:{port}{path}", method=method, headers=headers,
                  data=None if payload is None else json.dumps(payload).encode())
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def test_http_contract_and_security_gate(fabric):
    class Handler(FabricRequestHandler):
        pass
    Handler.fabric = fabric
    Handler.auth_token = "test-token"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    try:
        assert request(port, "/v1/bots", token="wrong")[0] == 401
        status, body = request(port, "/v1/bots", "POST", {
            "name": "Assistant", "job": "Help", "runtime_id": "local"})
        assert status == 200
        bot_id = json.loads(body)["bot"]["bot_id"]
        assert request(port, f"/v1/bots/{bot_id}", "PATCH", {"notes": "Remember this"})[0] == 200
        assert request(port, f"/v1/bots/{bot_id}/messages", "POST", {"body": "Hello"})[0] == 200
        status, conversation = request(port, f"/v1/bots/{bot_id}/conversation")
        assert status == 200 and "A useful reply" in conversation
        assert request(port, "/v1/bots/missing")[0] == 404
        assert request(port, "/v1/bots", "POST", [])[0] == 400
        assert request(port, f"/v1/bots/{bot_id}/messages", "POST", {"body": ""})[0] == 400
    finally:
        server.shutdown()
        server.server_close()


def test_new_shell_and_legacy_deck_are_both_served():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CommandDeckHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        for path, expected in [("/", "Search conversations"), ("/deck", "Command Deck"),
                               ("/bots.js", "state.selected"), ("/bots.css", ".sidebar")]:
            status, body = request(server.server_port, path)
            assert status == 200 and expected in body
        assert request(server.server_port, "/../config.local.json")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_avatar_survives_profile_updates_and_rejects_markup(fabric):
    bot = create(fabric, avatar_style='ray', avatar_color='coral')
    updated = fabric.bots.save({'name': 'Research companion'}, bot['bot_id'])
    assert updated['avatar_style'] == 'ray'
    assert updated['avatar_color'] == 'coral'
    persisted = fabric.storage.get_bot(bot['bot_id'])
    assert persisted['avatar_style'] == 'ray'
    assert persisted['instructions'] == ''
    with pytest.raises(ValueError, match='Unknown avatar_style'):
        fabric.bots.save({'avatar_style': '<svg onload=x>'}, bot['bot_id'])
    assert fabric.bots.get(bot['bot_id'])['avatar_style'] == 'ray'
