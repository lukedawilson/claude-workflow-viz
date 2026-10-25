import os
import signal
import subprocess
import sys
import time

import pytest

from claude_workflow_viz.dashboard.connection_file import Connection

TIMEOUT_SECONDS = 15


def _start_serve(state_dir):
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
    return process, path


def _stop(process, sent_signal):
    time.sleep(0.3)  # let serve_forever start
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
    process, path = _start_serve(tmp_path)
    token = Connection.read().token
    stdout = ""
    try:
        time.sleep(0.3)
        process.send_signal(signal.SIGINT)
        process.wait(timeout=TIMEOUT_SECONDS)
        stdout = process.stdout.read().decode("utf-8", "replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()
    assert token not in stdout
    assert "listening on" in stdout


@pytest.mark.parametrize("sent_signal", [signal.SIGINT, signal.SIGTERM])
def test_serve_removes_its_connection_file_on_signal(tmp_path, sent_signal):
    process, path = _start_serve(tmp_path)
    _stop(process, sent_signal)
    assert not path.exists()


def test_serve_leaves_a_newer_servers_connection_file(tmp_path, monkeypatch):
    process, path = _start_serve(tmp_path)
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))
    Connection(port=4321, token="newer-server-token").write()
    _stop(process, signal.SIGINT)
    assert path.exists()
