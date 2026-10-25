import http.client
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from claude_workflow_viz.dashboard.connection_file import Connection

TIMEOUT_SECONDS = 15


def _start_serve(state_dir):
    """Start `serve` as a subprocess; return (process, connection-file path, connection)."""
    environment = {**os.environ, "CLAUDE_WORKFLOW_VIZ_STATE_DIR": str(state_dir)}
    process = subprocess.Popen(
        [sys.executable, "-m", "claude_workflow_viz", "serve"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    path = state_dir / "server.json"
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while not path.exists():
        if time.monotonic() > deadline or process.poll() is not None:
            process.kill()
            process.wait()
            pytest.fail("serve did not write the connection file")
        time.sleep(0.05)
    try:
        # Read the file the subprocess wrote: the test process has no
        # CLAUDE_WORKFLOW_VIZ_STATE_DIR env, so Connection.read() would look
        # in the default state directory and find nothing.
        data = json.loads(path.read_text(encoding="utf-8"))
        connection = Connection(port=data["port"], token=data["token"])
    except (OSError, ValueError, KeyError):
        process.kill()
        process.wait()
        pytest.fail("serve wrote an unreadable connection file")
    return process, path, connection


def _post_shutdown(port, token):
    """Stop the server the way the SessionEnd hook does (POST /shutdown).

    Windows has no POSIX signals; the product's stop mechanism there is the
    authenticated /shutdown endpoint, which runs the same connection-file
    cleanup sequence as SIGINT. The port and token are passed explicitly
    because a test may have overwritten the connection file by then.
    """
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/shutdown", headers={"Authorization": f"Bearer {token}"})
    response = conn.getresponse()
    response.read()
    conn.close()
    assert response.status == 204


def _stop(process, sent_signal, port, token):
    time.sleep(0.3)  # let serve_forever start
    if os.name == "nt":
        _post_shutdown(port, token)
    else:
        process.send_signal(sent_signal)
    try:
        process.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        pytest.fail("serve did not exit")
    finally:
        process.stdout.close()
        process.stderr.close()


def test_serve_does_not_print_the_token_to_a_non_terminal_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    process, _, connection = _start_serve(tmp_path)
    stdout = ""
    try:
        time.sleep(0.3)
        if os.name == "nt":
            _post_shutdown(connection.port, connection.token)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=TIMEOUT_SECONDS)
        stdout = process.stdout.read().decode("utf-8", "replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()
    assert connection.token not in stdout
    assert "listening on" in stdout


@pytest.mark.parametrize("sent_signal", [signal.SIGINT, signal.SIGTERM])
def test_serve_removes_its_connection_file_on_signal(tmp_path, sent_signal):
    process, path, connection = _start_serve(tmp_path)
    _stop(process, sent_signal, connection.port, connection.token)
    assert not path.exists()


def test_serve_leaves_a_newer_servers_connection_file(tmp_path, monkeypatch):
    process, path, connection = _start_serve(tmp_path)
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    Connection(port=4321, token="newer-server-token").write()
    _stop(process, signal.SIGINT, connection.port, connection.token)
    assert path.exists()
