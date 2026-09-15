"""End-to-end checks of the daemon HTTP security gate."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from synkraken.api import FabricRequestHandler
from synkraken.fabric import AgentFabric
from synkraken.storage import Storage


def _make_server(tmp_path, token=None):
    storage = Storage(tmp_path / "api.db")
    config = {
        "server": {"host": "127.0.0.1", "port": 0},
        "adapters": {"echo": {"type": "claude", "command": ["true"], "enabled": True}},
        "routing": {},
    }
    fabric = AgentFabric(config, storage)

    class Handler(FabricRequestHandler):
        pass

    Handler.fabric = fabric
    Handler.allowed_hosts = frozenset({"127.0.0.1", "localhost", "::1"})
    Handler.auth_token = token
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    return httpd, httpd.server_address[1]


def _get(port, path="/health", host=None, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if host is not None:
        req.add_header("Host", host)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_loopback_request_allowed(tmp_path):
    httpd, port = _make_server(tmp_path)
    try:
        assert _get(port, host="127.0.0.1") == 200
        assert _get(port, host="localhost") == 200
    finally:
        httpd.shutdown()


def test_spoofed_host_rejected(tmp_path):
    httpd, port = _make_server(tmp_path)
    try:
        # DNS-rebinding defense: a foreign Host header is refused.
        assert _get(port, host="evil.example.com") == 403
    finally:
        httpd.shutdown()


def test_token_enforced_when_configured(tmp_path):
    httpd, port = _make_server(tmp_path, token="s3cr3t")
    try:
        assert _get(port, host="127.0.0.1") == 401
        assert _get(port, host="127.0.0.1", token="wrong") == 401
        assert _get(port, host="127.0.0.1", token="s3cr3t") == 200
    finally:
        httpd.shutdown()


def test_oversized_body_rejected(tmp_path):
    httpd, port = _make_server(tmp_path)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/messages",
            data=b"a" * (5 * 1024 * 1024),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # The server refuses the oversized body without processing it — either a
        # clean 400 or an early connection close (reset) before the full body is
        # drained. Both prove the body was never parsed into memory.
        with pytest.raises((urllib.error.HTTPError, urllib.error.URLError)) as exc:
            urllib.request.urlopen(req, timeout=5)
        if isinstance(exc.value, urllib.error.HTTPError):
            assert exc.value.code == 400
    finally:
        httpd.shutdown()
