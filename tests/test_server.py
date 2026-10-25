import http.client
import json
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from _platform import assert_private_mode
from claude_workflow_viz.dashboard.connection_file import Connection
from claude_workflow_viz.dashboard.server import MAXIMUM_BODY_BYTES, start_server

EVENT = {
    "session_id": "s1",
    "ts": 1.0,
    "kind": "step_start",
    "step_key": "plan",
    "status": "running",
    "summary": "planning",
}


@pytest.fixture
def running(tmp_path, monkeypatch) -> Iterator["tuple[object, int, str]"]:
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    running_server = start_server(port=0, keepalive_seconds=0.2)
    thread = threading.Thread(target=running_server.serve_forever, daemon=True)
    thread.start()
    yield running_server, running_server.port, running_server.token
    running_server.shutdown()
    running_server.server_close()
    thread.join(timeout=5)


def _post(port, body, token=None, path="/ingest"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
    connection.request("POST", path, body=payload, headers=headers)
    response = connection.getresponse()
    response.read()
    connection.close()
    return response.status


def test_bound_to_loopback_only(running):
    server, port, _ = running
    assert server.server_address[0] == "127.0.0.1"
    assert server.server_address[1] == port != 0


def test_valid_ingest_is_applied(running):
    server, port, token = running
    assert _post(port, EVENT, token) in (202, 204)
    assert server.state.snapshot()["sessions"]["s1"]["steps"]["plan"]["statuses"] == ["running"]


@pytest.mark.parametrize("token", [None, "wrong"])
def test_ingest_without_valid_token_is_rejected_and_state_unchanged(running, token):
    server, port, _ = running
    assert _post(port, EVENT, token) == 401
    assert server.state.snapshot() == {"sessions": {}}


def test_malformed_json_is_400(running):
    _, port, token = running
    assert _post(port, b"{not json", token) == 400


def test_non_utf8_body_is_400(running):
    _, port, token = running
    assert _post(port, b"\xff\xfe", token) == 400


def test_schema_invalid_event_is_400(running):
    server, port, token = running
    assert _post(port, {**EVENT, "kind": "bogus"}, token) == 400
    assert _post(port, [1, 2], token) == 400
    assert server.state.snapshot() == {"sessions": {}}


def test_oversize_body_is_413(running):
    _, port, token = running
    assert _post(port, b" " * (MAXIMUM_BODY_BYTES + 1), token) == 413


def test_unknown_paths_are_404(running):
    _, port, token = running
    assert _post(port, EVENT, token, path="/nope") == 404
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/nope")
    assert connection.getresponse().status == 404


def test_connection_file_has_bound_port_and_token_mode_0600(running):
    _, port, token = running
    connection = Connection.read()
    assert connection is not None
    assert (connection.port, connection.token) == (port, token)
    path = Path(os.environ["CLAUDE_WORKFLOW_VIZ_STATE_DIR"]) / "server.json"
    assert_private_mode(Path(path), 0o600)


@pytest.mark.parametrize("query", ["", "?token=wrong"])
def test_stream_without_valid_token_is_401(running, query):
    _, port, _ = running
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/stream{query}")
    assert connection.getresponse().status == 401


def _read_sse(response, wanted_events, deadline_seconds=5):
    """Collect (event name, data) pairs, skipping comments, until `wanted_events` are read."""
    collected = []
    name = None
    deadline = time.monotonic() + deadline_seconds
    while len(collected) < wanted_events and time.monotonic() < deadline:
        line = response.fp.readline().decode().rstrip("\n")
        if line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            collected.append((name, json.loads(line[len("data: ") :])))
    return collected


def test_stream_replays_snapshot_then_new_events(running):
    server, port, token = running
    assert _post(port, EVENT, token) in (202, 204)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/stream?token={token}")
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("text/event-stream")
    first = _read_sse(response, 1)
    assert first[0][0] == "snapshot"
    assert first[0][1]["sessions"]["s1"]["steps"]["plan"]["statuses"] == ["running"]
    later = {**EVENT, "kind": "step_stop", "status": "pass", "ts": 2.0}
    assert _post(port, later, token) in (202, 204)
    second = _read_sse(response, 1)
    assert second[0][0] == "event"
    assert second[0][1] == later
    connection.close()


def test_stream_sends_keepalive_comment_and_unsubscribes_on_disconnect(running):
    server, port, token = running
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/stream?token={token}")
    response = connection.getresponse()
    _read_sse(response, 1)
    assert response.fp.readline() == b"\n"  # end of the snapshot frame
    assert response.fp.readline().decode().startswith(": keep-alive")
    response.close()
    connection.close()
    deadline = time.monotonic() + 5
    while server.state._subscribers and time.monotonic() < deadline:
        # Keep-alive writes to the closed socket fail and trigger the unsubscribe.
        time.sleep(0.1)
    assert not server.state._subscribers


def test_no_host_option_exists():
    from claude_workflow_viz.cli import main

    with pytest.raises(SystemExit):
        main(["serve", "--host", "0.0.0.0"])


def test_serve_subcommand_starts_and_shuts_down_cleanly_on_interrupt(tmp_path):
    import json
    import signal
    import subprocess
    import sys

    environment = {**os.environ, "CLAUDE_WORKFLOW_VIZ_STATE_DIR": str(tmp_path)}
    process = subprocess.Popen(
        [sys.executable, "-c", "from claude_workflow_viz.cli import main; raise SystemExit(main())"]
        + ["serve", "--port", "0"],
        env={**environment, "PYTHONPATH": "src"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / "server.json").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (tmp_path / "server.json").exists()
        if os.name == "nt":
            # Windows has no POSIX signals; the SessionEnd stop path (POST /shutdown)
            # is the product's shutdown mechanism there and cleans up the same way.
            connection_file = json.loads((tmp_path / "server.json").read_text("utf-8"))
            conn = http.client.HTTPConnection("127.0.0.1", connection_file["port"], timeout=5)
            conn.request(
                "POST",
                "/shutdown",
                headers={"Authorization": f"Bearer {connection_file['token']}"},
            )
            response = conn.getresponse()
            response.read()
            conn.close()
            assert response.status == 204
        else:
            process.send_signal(signal.SIGINT)
        assert process.wait(timeout=10) == 0
        assert b"Traceback" not in process.stderr.read()
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.stderr.close()


# --- /graph and static UI -------------------------------------------------------------------


def _get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response, body


@pytest.fixture
def running_with_graph(tmp_path, monkeypatch) -> Iterator["tuple[object, int, str]"]:
    from claude_workflow_viz.graph.graph import Graph

    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    graph = Graph.load(Path(__file__).parent.parent / "examples" / "implement.viz.yaml")
    running_server = start_server(port=0, keepalive_seconds=0.2, graph=graph)
    thread = threading.Thread(target=running_server.serve_forever, daemon=True)
    thread.start()
    yield running_server, running_server.port, running_server.token
    running_server.shutdown()
    running_server.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize("query", ["", "?token=wrong"])
def test_graph_without_valid_token_is_401(running, query):
    _, port, _ = running
    response, _ = _get(port, f"/graph{query}")
    assert response.status == 401


def test_graph_from_config(running_with_graph):
    _, port, token = running_with_graph
    response, body = _get(port, f"/graph?token={token}")
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("application/json")
    payload = json.loads(body)
    assert payload["source"] == "config"
    assert payload["graph"]["name"]
    assert payload["graph"]["nodes"]
    assert "verdicts" in payload["status_rules"]


def test_graph_without_config_is_linear_and_follows_ingested_stages(running):
    _, port, token = running
    _, body = _get(port, f"/graph?token={token}")
    payload = json.loads(body)
    assert payload["source"] == "linear"
    assert [node["id"] for node in payload["graph"]["nodes"]] == ["done"]
    _post(port, {**EVENT, "stage": "plan"}, token)
    _post(port, {**EVENT, "step_key": "build", "stage": "build"}, token)
    _post(port, {**EVENT, "step_key": "lonely"}, token)
    _, body = _get(port, f"/graph?token={token}")
    ids = [node["id"] for node in json.loads(body)["graph"]["nodes"]]
    assert ids == ["plan", "build", "lonely", "done"]


def test_graph_without_config_has_unique_ids_for_a_done_stage(running):
    _, port, token = running
    _post(port, {**EVENT, "stage": "done"}, token)
    _, body = _get(port, f"/graph?token={token}")
    ids = [node["id"] for node in json.loads(body)["graph"]["nodes"]]
    assert len(ids) == len(set(ids))
    assert ids[-1] == "done"


def test_index_is_served_with_security_headers(running):
    _, port, _ = running
    response, body = _get(port, "/")
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("text/html")
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Content-Security-Policy") == (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
    )
    assert int(response.getheader("Content-Length")) == len(body) > 0


def test_index_is_served_when_query_carries_the_token(running):
    _, port, token = running
    response, _ = _get(port, f"/?token={token}")
    assert response.status == 200


def test_static_file_is_served_with_content_type(running):
    _, port, _ = running
    response, body = _get(port, "/static/status_rules.json")
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("application/json")
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert "verdicts" in json.loads(body)


@pytest.mark.parametrize(
    "path",
    ["/static/../server.py", "/static/%2e%2e/server.py", "/static/missing.js", "/static/"],
)
def test_static_outside_the_allowlist_is_404(running, path):
    _, port, _ = running
    response, _ = _get(port, path)
    assert response.status == 404


def test_package_data_lists_every_static_file_type():
    from importlib import resources

    names = {
        entry.name for entry in resources.files("claude_workflow_viz").joinpath("static").iterdir()
    }
    assert {"index.html", "status_rules.json"} <= names


# --- static types, Host header and read timeout ---------------------------------------------


@pytest.mark.parametrize("path", ["/static/VENDORED.md", "/static/mermaid.LICENSE"])
def test_vendoring_notes_and_licence_are_not_served(running, path):
    _, port, _ = running
    response, _ = _get(port, path)
    assert response.status == 404


def _request_with_host(port, method, path, host, token=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host}
    body = None
    if method == "POST":
        headers["Authorization"] = f"Bearer {token}"
        body = json.dumps(EVENT).encode()
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    content = response.read()
    connection.close()
    return response, content


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/"), ("GET", "/graph"), ("GET", "/stream"), ("POST", "/ingest")],
)
def test_foreign_host_is_421_before_the_token_check(running, method, path):
    server, port, token = running
    response, content = _request_with_host(port, method, path, f"evil.example:{port}", token)
    assert response.status == 421
    assert response.getheader("Content-Length") == "0"
    assert content == b""
    assert server.state.snapshot() == {"sessions": {}}


def test_wrong_port_in_host_is_421(running):
    _, port, _ = running
    response, _ = _request_with_host(port, "GET", "/", f"127.0.0.1:{port + 1}")
    assert response.status == 421


def test_ipv6_host_form_is_421(running):
    _, port, _ = running
    response, _ = _request_with_host(port, "GET", "/", f"[::1]:{port}")
    assert response.status == 421


def test_localhost_host_is_accepted(running):
    _, port, token = running
    response, _ = _request_with_host(port, "GET", f"/graph?token={token}", f"localhost:{port}")
    assert response.status == 200
    response, _ = _request_with_host(port, "POST", "/ingest", f"localhost:{port}", token)
    assert response.status == 204


def test_missing_host_header_is_421(running):
    import socket

    _, port, _ = running
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.sendall(b"GET / HTTP/1.0\r\n\r\n")
        reply = b""
        while chunk := client.recv(4096):
            reply += chunk
    assert reply.startswith(b"HTTP/1.0 421 ")


def test_stalled_body_releases_the_connection_and_server_keeps_serving(tmp_path, monkeypatch):
    import socket

    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    server = start_server(port=0, keepalive_seconds=0.2, request_timeout_seconds=0.5)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=5) as client:
            client.sendall(
                f"POST /ingest HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
                f"Authorization: Bearer {server.token}\r\nContent-Length: 100\r\n\r\n"
                "0123456789".encode()
            )
            started = time.monotonic()
            assert client.recv(4096) == b""  # server closed the connection
            assert time.monotonic() - started < 3
        response, _ = _get(server.port, f"/graph?token={server.token}")
        assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
