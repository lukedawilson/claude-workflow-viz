"""`Connection.stop_server`: authenticated POST /shutdown, silent no-op without a file."""

import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from claude_workflow_viz.dashboard import connection_file
from claude_workflow_viz.dashboard.connection_file import (
    LOOPBACK_ADDRESS,
    STOP_TIMEOUT_SECONDS,
    Connection,
)


@pytest.fixture(autouse=True)
def state_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    return tmp_path


def test_loopback_address_lives_on_the_connection_module():
    assert LOOPBACK_ADDRESS == "127.0.0.1"


def test_stop_server_is_available_as_a_connection_method():
    assert callable(Connection.stop_server)


def test_stop_server_no_ops_without_a_connection_file():
    Connection.stop_server()


def test_stop_server_posts_bearer_token_to_shutdown_and_reads_204():
    seen = {}

    class Recorder(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["authorization"] = self.headers.get("Authorization")
            seen["content_length"] = self.headers.get("Content-Length")
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_arguments):
            pass

    recorder = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=recorder.serve_forever, daemon=True)
    thread.start()
    try:
        Connection(recorder.server_address[1], "stop-token").write()
        Connection.stop_server()
    finally:
        recorder.shutdown()
        recorder.server_close()
        thread.join(timeout=5)
    assert seen == {
        "path": "/shutdown",
        "authorization": "Bearer stop-token",
        "content_length": "0",
    }


def test_stop_server_swallows_a_dead_port():
    with __import__("socket").socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    Connection(port, "token").write()
    Connection.stop_server()


def test_stop_server_swallows_a_non_2xx_response():
    class Rejecting(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_arguments):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Rejecting)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        Connection(server.server_address[1], "token").write()
        Connection.stop_server()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_stop_server_uses_a_one_second_timeout():
    assert 0 < STOP_TIMEOUT_SECONDS <= 1.0


def test_stop_server_ignores_proxy_environment(monkeypatch):
    def fail_open(*_arguments, **_keywords):
        raise AssertionError("proxy must not be consulted")

    seen = {}

    class Recorder(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_arguments):
            pass

    recorder = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=recorder.serve_forever, daemon=True)
    thread.start()
    try:
        Connection(recorder.server_address[1], "token").write()
        monkeypatch.setattr(urllib.request, "_opener", None)
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("all_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        Connection.stop_server()
    finally:
        recorder.shutdown()
        recorder.server_close()
        thread.join(timeout=5)
    assert seen == {"path": "/shutdown"}


def test_state_directory_is_exposed_for_graphs(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    assert connection_file.state_directory() == tmp_path
