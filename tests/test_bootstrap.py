"""`Bootstrap.run`: parse, spawn/reuse, and open the dashboard (FR6/Q2/R11/R18)."""

import sys
import threading
from pathlib import Path

import pytest

from _platform import assert_private_mode

from claude_workflow_viz.dashboard.connection_file import Connection
from claude_workflow_viz.dashboard.server import start_server
from claude_workflow_viz.invoke.bootstrap import Bootstrap

ROOT = Path(__file__).resolve().parent.parent
IMPLEMENT = (ROOT / "tests" / "fixtures" / "workflows" / "implement.js").read_text(encoding="utf-8")
RCA = (ROOT / "tests" / "fixtures" / "workflows" / "rca.js").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def state_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


def _workflow_dir(tmp_path):
    directory = tmp_path / "repo" / ".claude" / "workflows"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _payload(workflow, cwd):
    return {
        "session_id": "s1",
        "hook_event_name": "PreToolUse",
        "tool_name": "Workflow",
        "tool_input": {"name": workflow},
        "cwd": str(cwd),
    }


def _noop_sweep(_port):
    return None


def test_live_server_is_reused_without_spawn(tmp_path):
    cwd = tmp_path / "repo"
    (_workflow_dir(tmp_path) / "implement.js").write_text(IMPLEMENT, encoding="utf-8")
    server = start_server(port=0, keepalive_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    spawned = []
    opened = []
    try:
        Bootstrap(spawn=spawned.append, open_browser=opened.append).run(_payload("implement", cwd))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert spawned == []
    assert len(opened) == 1
    assert f"token={server.token}" in opened[0]
    assert "workflow=implement" in opened[0]
    cache = tmp_path / "state" / "graphs" / "implement.viz.yaml"
    assert cache.exists()
    assert "name: implement" in cache.read_text(encoding="utf-8")


def test_spawn_writes_the_cache_and_passes_graph(tmp_path):
    cwd = tmp_path / "repo"
    (_workflow_dir(tmp_path) / "implement.js").write_text(IMPLEMENT, encoding="utf-8")
    spawned = []
    opened = []
    Bootstrap(
        spawn=spawned.append,
        open_browser=opened.append,
        sweep=_noop_sweep,
        wait=lambda _previous: Connection(8123, "token"),
    ).run(_payload("implement", cwd))
    assert spawned == [
        [
            sys.executable,
            "-m",
            "claude_workflow_viz",
            "serve",
            "--graph",
            str(tmp_path / "state" / "graphs" / "implement.viz.yaml"),
        ]
    ]
    assert opened == ["http://127.0.0.1:8123/?token=token&workflow=implement"]


def test_parse_failure_spawns_linear_and_logs_the_summary(tmp_path):
    cwd = tmp_path / "repo"
    (_workflow_dir(tmp_path) / "rca.js").write_text(RCA, encoding="utf-8")
    spawned = []
    opened = []
    Bootstrap(
        spawn=spawned.append,
        open_browser=opened.append,
        sweep=_noop_sweep,
        wait=lambda _previous: Connection(8123, "token"),
    ).run(_payload("rca", cwd))
    assert spawned == [[sys.executable, "-m", "claude_workflow_viz", "serve"]]
    assert opened == ["http://127.0.0.1:8123/?token=token&workflow=rca"]
    log = (tmp_path / "state" / "debug.log").read_text(encoding="utf-8")
    assert "unsupported-label" in log
    assert not (tmp_path / "state" / "graphs" / "rca.viz.yaml").exists()


def test_connection_wait_timeout_opens_nothing(tmp_path):
    cwd = tmp_path / "repo"
    (_workflow_dir(tmp_path) / "implement.js").write_text(IMPLEMENT, encoding="utf-8")
    spawned = []
    opened = []
    Bootstrap(
        spawn=spawned.append,
        open_browser=opened.append,
        sweep=_noop_sweep,
        wait=lambda _previous: None,
    ).run(_payload("implement", cwd))
    assert len(spawned) == 1
    assert opened == []


def test_missing_workflow_name_spawns_linear_without_workflow_param(tmp_path):
    payload = {
        "session_id": "s1",
        "hook_event_name": "PreToolUse",
        "tool_name": "Workflow",
        "tool_input": {},
        "cwd": str(tmp_path / "repo"),
    }
    spawned = []
    opened = []
    Bootstrap(
        spawn=spawned.append,
        open_browser=opened.append,
        sweep=_noop_sweep,
        wait=lambda _previous: Connection(8123, "token"),
    ).run(payload)
    assert spawned == [[sys.executable, "-m", "claude_workflow_viz", "serve"]]
    assert opened == ["http://127.0.0.1:8123/?token=token"]


def test_stale_connection_file_is_excluded_by_the_wait(tmp_path):
    cwd = tmp_path / "repo"
    (_workflow_dir(tmp_path) / "implement.js").write_text(IMPLEMENT, encoding="utf-8")
    stale = Connection(port=1, token="stale")
    stale.write()
    seen = []

    def wait(previous):
        seen.append(previous)
        return None

    Bootstrap(
        spawn=lambda _a: None, sweep=_noop_sweep, wait=wait, open_browser=lambda _u: None
    ).run(_payload("implement", cwd))
    assert seen == [stale]


def test_detached_spawn_logs_no_token_and_keeps_the_state_dir_private(tmp_path):
    cwd = tmp_path / "repo"
    (_workflow_dir(tmp_path) / "implement.js").write_text(IMPLEMENT, encoding="utf-8")
    opened = []
    try:
        Bootstrap(open_browser=opened.append, sweep=_noop_sweep).run(_payload("implement", cwd))
        connection = Connection.read()
        assert connection is not None
        assert len(opened) == 1
        log = (tmp_path / "state" / "debug.log").read_text(encoding="utf-8")
        assert connection.token not in log
        assert "listening on" in log
        assert_private_mode((tmp_path / "state"), 0o700)
    finally:
        Connection.stop_server()


@pytest.mark.parametrize(
    "payload",
    [None, 5, "x", [], {}, {"hook_event_name": "PreToolUse", "tool_name": "Workflow"}],
)
def test_run_never_raises(payload):
    Bootstrap(
        spawn=lambda _a: None,
        probe=lambda _c: False,
        open_browser=lambda _u: None,
        sweep=_noop_sweep,
        wait=lambda _previous: None,
    ).run(payload)
