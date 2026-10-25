import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from claude_workflow_viz.dashboard.server import start_server
from claude_workflow_viz.graph.graph import Graph

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def example_server(tmp_path, monkeypatch) -> Iterator["tuple[int, str]"]:
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    graph = Graph.load(ROOT / "examples" / "implement.viz.yaml")
    server = start_server(port=0, keepalive_seconds=0.2, graph=graph)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.port, server.token
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _post(port, body, token):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(
        "POST",
        "/ingest",
        body=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    response = connection.getresponse()
    response.read()
    connection.close()
    return response.status


def _read_sse(response, wanted_events, deadline_seconds=5):
    """Collect (event name, data) pairs, skipping comments, until `wanted_events` are read."""
    collected = []
    name = None
    deadline = time.monotonic() + deadline_seconds
    sock = response.fp.raw._sock
    while len(collected) < wanted_events:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(remaining)
        try:
            line = response.fp.readline().decode().rstrip("\n")
        except TimeoutError:
            break
        if line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            collected.append((name, json.loads(line[len("data: ") :])))
    if len(collected) < wanted_events:
        missing = wanted_events - len(collected)
        pytest.fail(
            f"stream sent {len(collected)} of {wanted_events} events before the "
            f"{deadline_seconds}s deadline; still awaiting {missing} more event(s)"
        )
    return collected


def test_read_sse_fails_within_the_deadline_when_the_stream_goes_silent():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    release = threading.Event()

    def serve_headers_then_nothing():
        client, _ = listener.accept()
        client.recv(4096)
        client.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n")
        release.wait(timeout=10)
        client.close()

    thread = threading.Thread(target=serve_headers_then_nothing, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", listener.getsockname()[1], timeout=5)
    connection.request("GET", "/stream")
    response = connection.getresponse()
    started = time.monotonic()
    try:
        with pytest.raises(pytest.fail.Exception, match="awaiting 1 more event"):
            _read_sse(response, 1, deadline_seconds=1)
        assert time.monotonic() - started < 2
    finally:
        release.set()
        connection.close()
        listener.close()
        thread.join(timeout=5)


def _get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read().decode()
    connection.close()
    return response.status, body


def test_graph_endpoint_returns_the_implement_graph_from_config(example_server):
    port, token = example_server
    status, body = _get(port, f"/graph?token={token}")
    assert status == 200
    document = json.loads(body)
    assert document["source"] == "config"
    node_ids = {node["id"] for node in document["graph"]["nodes"]}
    assert {"planner", "develop", "gate", "review", "code-review", "done", "blocked"} <= node_ids


def test_root_serves_the_ui_html_referencing_its_scripts(example_server):
    port, _ = example_server
    status, body = _get(port, "/")
    assert status == 200
    assert "/static/app.js" in body
    assert "/static/mermaid.min.js" in body


def test_posted_event_arrives_on_open_stream_after_the_snapshot(example_server):
    port, token = example_server
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/stream?token={token}")
    response = connection.getresponse()
    assert _read_sse(response, 1)[0][0] == "snapshot"
    event = {
        "session_id": "s1",
        "ts": 1.0,
        "kind": "step_start",
        "step_key": "S1/develop:r1",
        "status": "running",
        "summary": "developing",
        "stage": "develop",
        "slice": "S1",
        "round": 1,
    }
    assert _post(port, event, token) in (202, 204)
    name, data = _read_sse(response, 1)[0]
    assert name == "event"
    assert (data["stage"], data["slice"], data["round"]) == ("develop", "S1", 1)
    connection.close()


def test_readme_documents_the_serve_graph_flow_and_is_not_stale():
    readme = (ROOT / "README.md").read_text("utf-8")
    for stale in ("placeholders", "arrives in a later phase"):
        assert stale not in readme
    headings = {line for line in readme.splitlines() if line.startswith("#")}
    for heading in (
        "### Server endpoints",
        "### Graph configuration",
        "## Development environment",
    ):
        assert heading in headings, heading
    for command in ("serve --graph", "node --test tests/js"):
        assert command in readme, command
