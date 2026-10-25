import io
import json
import socket
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from claude_workflow_viz.cli import main
from claude_workflow_viz.dashboard.connection_file import Connection
from claude_workflow_viz.dashboard.server import start_server
from claude_workflow_viz.workflow import hook_command

SUBAGENT_START = {
    "session_id": "s1",
    "hook_event_name": "SubagentStart",
    "agent_id": "a1",
    "agent_type": "planner",
}


@pytest.fixture(autouse=True)
def state_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    return tmp_path


def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def _assert_silent_success(capsys) -> None:
    assert main(["hook"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def running():
    server = start_server(port=0, keepalive_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_valid_payload_reaches_server_state(running, monkeypatch, capsys):
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    _assert_silent_success(capsys)
    steps = running.state.snapshot()["sessions"]["s1"]["steps"]
    assert steps["planner"]["statuses"] == ["running"]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[1, 2]",
        '"text"',
        json.dumps({"session_id": "s1", "hook_event_name": "Notification"}),
        json.dumps({"hook_event_name": "SubagentStart"}),
    ],
)
def test_unusable_stdin_is_silent(running, monkeypatch, capsys, text):
    _stdin(monkeypatch, text)
    _assert_silent_success(capsys)
    assert running.state.snapshot()["sessions"] == {}


def test_missing_connection_file_is_silent(monkeypatch, capsys):
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    _assert_silent_success(capsys)


def test_closed_port_is_silent(monkeypatch, capsys):
    Connection(_closed_port(), "token").write()
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    _assert_silent_success(capsys)


def test_unauthorised_response_is_silent(running, monkeypatch, capsys):
    Connection(running.port, "wrong-token").write()
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    _assert_silent_success(capsys)
    assert running.state.snapshot()["sessions"] == {}


def test_unexpected_exception_is_silent(monkeypatch, capsys):
    def explode(*_arguments, **_keywords):
        raise RuntimeError("boom")

    monkeypatch.setattr(hook_command, "normalise", explode)
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    _assert_silent_success(capsys)


def test_unreadable_stdin_is_silent(monkeypatch, capsys):
    class Broken:
        def read(self):
            raise OSError("closed")

    monkeypatch.setattr(sys, "stdin", Broken())
    _assert_silent_success(capsys)


def test_extra_arguments_do_not_reach_argparse(monkeypatch, capsys):
    _stdin(monkeypatch, "")
    assert main(["hook", "--bogus"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_proxy_environment_is_ignored_for_loopback_post(running, monkeypatch, capsys):
    # urlopen caches its default opener (and so the proxy settings) on first use.
    monkeypatch.setattr(urllib.request, "_opener", None)
    dead_proxy = f"http://127.0.0.1:{_closed_port()}"
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, dead_proxy)
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    _assert_silent_success(capsys)
    steps = running.state.snapshot()["sessions"]["s1"]["steps"]
    assert steps["planner"]["statuses"] == ["running"]


def test_timeout_is_one_second_or_less():
    assert 0 < hook_command.POST_TIMEOUT_SECONDS <= 1.0


def test_post_carries_token_and_timeout(monkeypatch, capsys):
    seen = {}

    class Recorder(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["authorization"] = self.headers.get("Authorization")
            seen["path"] = self.path
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_arguments):
            pass

    recorder = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=recorder.serve_forever, daemon=True)
    thread.start()
    timeouts = []
    real_open = urllib.request.OpenerDirector.open

    def spy(self, request, data=None, timeout=None):
        timeouts.append(timeout)
        return real_open(self, request, data, timeout)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", spy)
    Connection(recorder.server_address[1], "secret-token").write()
    _stdin(monkeypatch, json.dumps(SUBAGENT_START))
    try:
        _assert_silent_success(capsys)
    finally:
        recorder.shutdown()
        recorder.server_close()
    assert seen == {"authorization": "Bearer secret-token", "path": "/ingest"}
    assert timeouts and all(t is not None and t <= 1.0 for t in timeouts)


def test_subprocess_with_bad_stdin_is_silent(state_directory):
    result = subprocess.run(
        [sys.executable, "-m", "claude_workflow_viz", "hook"],
        input="}{ not json",
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "CLAUDE_WORKFLOW_VIZ_STATE_DIR": str(state_directory),
            "PYTHONPATH": str(__import__("pathlib").Path(__file__).parents[1] / "src"),
            "PATH": "/usr/bin",
        },
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_workflow_stop_with_missing_meta_is_silent(tmp_path, monkeypatch, capsys):
    run_directory = tmp_path / "session" / "subagents" / "workflows" / "wf_missing-meta"
    run_directory.mkdir(parents=True)
    payload = {
        "session_id": "s1",
        "hook_event_name": "SubagentStop",
        "cwd": str(tmp_path),
        "transcript_path": "session.jsonl",
        "agent_id": "abc123",
        "agent_type": "workflow-subagent",
        "agent_transcript_path": "session/subagents/workflows/wf_missing-meta/agent-abc123.jsonl",
    }
    _stdin(monkeypatch, json.dumps(payload))
    _assert_silent_success(capsys)
