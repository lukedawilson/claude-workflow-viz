"""Per-workflow graph registry served by `/graph?workflow=<name>` (R15)."""

import http.client
import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from claude_workflow_viz.dashboard.connection_file import state_directory
from claude_workflow_viz.dashboard.server import start_server

GRAPH = """name: wf-one
entry: plan
nodes:
  - {id: plan, label: Plan, stage: plan, on_pass: done}
  - {id: done, label: Done, terminal: true}
"""

OTHER_GRAPH = """name: wf-two
entry: scan
nodes:
  - {id: scan, label: Scan, step_key: scan, on_pass: done}
  - {id: done, label: Done, terminal: true}
"""


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
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


def _get(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, json.loads(body)


def _write_graph(name, text):
    directory = state_directory() / "graphs"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.viz.yaml").write_text(text, encoding="utf-8")


def test_workflow_graph_is_loaded_from_the_graphs_directory(running, state_dir):
    _, port, token = running
    _write_graph("wf-one", GRAPH)
    status, document = _get(port, f"/graph?token={token}&workflow=wf-one")
    assert status == 200
    assert document["source"] == "config"
    assert document["graph"]["name"] == "wf-one"
    assert [node["id"] for node in document["graph"]["nodes"]] == ["plan", "done"]


def test_workflow_graph_is_cached_in_memory(running, state_dir):
    _, port, token = running
    _write_graph("wf-one", GRAPH)
    _get(port, f"/graph?token={token}&workflow=wf-one")
    _write_graph("wf-one", OTHER_GRAPH)  # overwrite after the first load
    _, document = _get(port, f"/graph?token={token}&workflow=wf-one")
    assert document["graph"]["name"] == "wf-one"
    assert [node["id"] for node in document["graph"]["nodes"]] == ["plan", "done"]


def test_unknown_workflow_is_a_linear_response(running):
    _, port, token = running
    status, document = _get(port, f"/graph?token={token}&workflow=nope")
    assert status == 200
    assert document["source"] == "linear"
    assert [node["id"] for node in document["graph"]["nodes"]] == ["done"]


def test_no_workflow_parameter_serves_the_default_linear_graph(running):
    _, port, token = running
    status, document = _get(port, f"/graph?token={token}")
    assert status == 200
    assert document["source"] == "linear"


def test_workflow_parameter_still_requires_the_token(running):
    _, port, _ = running
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", "/graph?workflow=wf-one")
    assert connection.getresponse().status == 401


def test_workflow_parameter_does_not_displace_the_default_graph(tmp_path):
    from claude_workflow_viz.graph.graph import Graph

    default = Graph.load(Path(__file__).parent.parent / "examples" / "implement.viz.yaml")
    assert isinstance(default, Graph)
    server = start_server(port=0, keepalive_seconds=0.2, graph=default)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _write_graph("wf-one", GRAPH)
        status, no_param = _get(server.port, f"/graph?token={server.token}")
        assert no_param["source"] == "config"
        assert no_param["graph"]["name"] == "implement"
        status, with_param = _get(server.port, f"/graph?token={server.token}&workflow=wf-one")
        assert with_param["source"] == "config"
        assert with_param["graph"]["name"] == "wf-one"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_unsafe_workflow_names_are_a_linear_fallback(running):
    _, port, token = running
    status, document = _get(port, f"/graph?token={token}&workflow=..%2F..%2Fetc")
    assert status == 200
    assert document["source"] == "linear"
