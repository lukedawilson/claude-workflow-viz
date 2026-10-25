"""The platform open-command selector and the port sweep helper."""

from hypothesis import given
from hypothesis import strategies as st

from claude_workflow_viz.invoke import _platform
from claude_workflow_viz.invoke._platform import (
    SWEEP_DEADLINE_SECONDS,
    SWEEP_MATCH,
    SWEEP_RECHECK_SECONDS,
    _alive,
    _listener_pids,
    _owned_listener,
    open_command,
    open_url,
    sweep_preferred_port,
)


def test_open_command_maps_the_three_platforms():
    assert open_command("darwin") == "open"
    assert open_command("win32") == "os.startfile"
    assert open_command("linux") == "xdg-open"


@given(st.text())
def test_open_command_is_total_over_platform_ids(platform):
    assert open_command(platform) in {"open", "os.startfile", "xdg-open"}


def test_open_url_uses_xdg_open_on_unknown_platforms(monkeypatch):
    calls = []
    monkeypatch.setattr(_platform.sys, "platform", "linux")
    monkeypatch.setattr(_platform.subprocess, "run", lambda command, check: calls.append(command))
    open_url("http://127.0.0.1:1/")
    assert calls == [["xdg-open", "http://127.0.0.1:1/"]]


def test_open_url_uses_os_startfile_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(_platform.sys, "platform", "win32")
    monkeypatch.setattr(_platform, "_startfile", lambda url: calls.append(url))
    open_url("http://127.0.0.1:1/")
    assert calls == ["http://127.0.0.1:1/"]


def test_open_url_swallows_a_missing_open_command(monkeypatch):
    def explode(*_arguments, **_keywords):
        raise FileNotFoundError("no such command")

    monkeypatch.setattr(_platform.sys, "platform", "linux")
    monkeypatch.setattr(_platform.subprocess, "run", explode)
    open_url("http://127.0.0.1:1/")  # must not raise


def test_listener_pids_is_empty_without_lsof(monkeypatch):
    monkeypatch.setattr(_platform.shutil, "which", lambda _name: None)
    assert _listener_pids(8322) == []


def test_listener_pids_parses_lsof_output(monkeypatch):
    class Result:
        stdout = "123\n456\n"

    monkeypatch.setattr(_platform.shutil, "which", lambda _name: "/usr/sbin/lsof")
    monkeypatch.setattr(
        _platform.subprocess,
        "run",
        lambda *_a, **_k: Result(),
    )
    assert _listener_pids(8322) == [123, 456]


def test_listener_pids_swallows_lsof_failure(monkeypatch):
    def explode(*_a, **_k):
        raise OSError("lsof failed")

    monkeypatch.setattr(_platform.shutil, "which", lambda _name: "/usr/sbin/lsof")
    monkeypatch.setattr(_platform.subprocess, "run", explode)
    assert _listener_pids(8322) == []


def test_owned_listener_requires_the_match_and_a_known_matching_cwd(monkeypatch):
    monkeypatch.setattr(
        _platform, "_command_line", lambda pid: "python -m claude_workflow_viz serve"
    )
    monkeypatch.setattr(_platform, "_cwd_of", lambda pid: "/repo")
    monkeypatch.setattr(_platform.os, "getcwd", lambda: "/repo")
    assert _owned_listener(42, "/repo") is True


def test_owned_listener_spares_an_unknown_cwd(monkeypatch):
    monkeypatch.setattr(
        _platform, "_command_line", lambda pid: "python -m claude_workflow_viz serve"
    )
    monkeypatch.setattr(_platform, "_cwd_of", lambda pid: None)
    assert _owned_listener(42, "/repo") is False


def test_owned_listener_spares_a_foreign_command(monkeypatch):
    monkeypatch.setattr(_platform, "_command_line", lambda pid: "other-server")
    monkeypatch.setattr(_platform, "_cwd_of", lambda pid: "/repo")
    assert _owned_listener(42, "/repo") is False


def test_sweep_is_a_silent_no_op_without_lsof(monkeypatch):
    monkeypatch.setattr(_platform.shutil, "which", lambda _name: None)
    sweep_preferred_port(8322)  # must not raise


def test_sweep_swallows_unexpected_errors(monkeypatch):
    def explode(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(_platform, "_listener_pids", explode)
    sweep_preferred_port(8322)  # must not raise


def test_alive_reports_a_dead_pid_as_false(monkeypatch):
    def dead(*_a, **_k):
        raise OSError("no such process")

    monkeypatch.setattr(_platform.os, "kill", dead)
    assert _alive(1234) is False


def test_sweep_constants_have_the_documented_bounds():
    assert SWEEP_DEADLINE_SECONDS == 3.0
    assert SWEEP_RECHECK_SECONDS == 0.05
    assert SWEEP_MATCH == "claude-workflow-viz"
