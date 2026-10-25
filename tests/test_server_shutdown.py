"""`POST /shutdown` and the preferred-port bind with EADDRINUSE fallback."""

import http.client
import socket
import sys
import threading
import time
from collections.abc import Iterator

import pytest

from claude_workflow_viz.dashboard.connection_file import Connection
from claude_workflow_viz.dashboard.server import PREFERRED_PORT, VisualiserServer, start_server


@pytest.fixture(autouse=True)
def state_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def running() -> Iterator["tuple[object, int, str]"]:
    server = start_server(port=0, keepalive_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, server.port, server.token
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _post(port, token=None, path="/shutdown", host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if host is not None:
        headers["Host"] = host
    connection.request("POST", path, headers=headers)
    response = connection.getresponse()
    response.read()
    connection.close()
    return response.status


def _get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def test_preferred_port_is_8322():
    assert PREFERRED_PORT == 8322


def test_allow_reuse_address_is_false_only_on_windows():
    assert VisualiserServer.allow_reuse_address == (sys.platform != "win32")


def test_explicit_zero_port_still_binds_an_ephemeral_port(running):
    server, port, _ = running
    assert server.server_address[0] == "127.0.0.1"
    assert port != 0


def test_default_port_binds_8322_or_falls_back_when_busy(tmp_path, monkeypatch):
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", PREFERRED_PORT))
    blocker.listen(1)
    try:
        server = start_server()
        assert server.port != PREFERRED_PORT
        server.server_close()
        Connection.remove_if_token_matches(server.token)
    finally:
        blocker.close()


def test_shutdown_with_bad_token_is_401_and_keeps_running(running):
    server, port, token = running
    assert _post(port, "wrong") == 401
    assert _post(port, None) == 401
    assert Connection.read() is not None
    status, _ = _get(port, f"/graph?token={token}")
    assert status == 200


def test_shutdown_requires_the_allowed_host(running):
    _, port, _ = running
    assert _post(port, "wrong", host=f"evil.example:{port}") == 421


def test_shutdown_with_valid_token_stops_the_server_and_removes_the_file(tmp_path):
    server = start_server(port=0, keepalive_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / "server.json"
    assert path.exists()
    assert _post(server.port, server.token) == 204
    thread.join(timeout=5)
    assert not thread.is_alive()
    deadline = time.monotonic() + 5
    while path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not path.exists()


def test_shutdown_leaves_a_newer_servers_file(tmp_path):
    server = start_server(port=0, keepalive_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    Connection(port=4321, token="newer").write()
    assert _post(server.port, server.token) == 204
    thread.join(timeout=5)
    deadline = time.monotonic() + 5
    while (tmp_path / "server.json").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert Connection.read() == Connection(port=4321, token="newer")
