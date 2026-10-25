"""Platform helpers for the invoke path: the browser-open command and the port sweep.

`open_command` is the one pure function the property tests target: a total mapping from a
platform id to the command that opens a URL in the default browser (NFRB4). `open_url` is its
effectful wrapper, best-effort and never raising. `sweep_preferred_port` recycles a stale
`claude-workflow-viz` server holding the preferred port before a spawn (NRB4); it is silent on
every failure and no-ops without `lsof` (Windows).
"""

import os
import shutil
import signal
import subprocess
import sys
import time

SWEEP_MATCH = "claude-workflow-viz"
SWEEP_DEADLINE_SECONDS = 3.0
SWEEP_RECHECK_SECONDS = 0.05
SWEEP_COMMAND_TIMEOUT_SECONDS = 2.0


def open_command(platform: str) -> str:
    """Return the open command for a platform id: darwin -> open, win32 -> os.startfile,
    else xdg-open."""
    if platform == "darwin":
        return "open"
    if platform == "win32":
        return "os.startfile"
    return "xdg-open"


def open_url(url: str) -> None:
    """Open `url` in the default browser; failures are swallowed (UEB5)."""
    try:
        command = open_command(sys.platform)
        if command == "os.startfile":
            _startfile(url)
        else:
            subprocess.run([command, url], check=False)
    except BaseException:
        return


def _startfile(url: str) -> None:
    """`os.startfile`, factored out so the win32 branch is testable off Windows (NFRB4)."""
    os.startfile(url)


def sweep_preferred_port(port: int) -> None:
    """Reclaim a stale `claude-workflow-viz` server holding `port`; best-effort, never raises."""
    try:
        _sweep(port, os.getcwd())
    except BaseException:
        return


def _sweep(port: int, cwd: str) -> None:
    own = os.getpid()
    for pid in _listener_pids(port):
        if pid != own and _owned_listener(pid, cwd):
            _terminate(pid)


def _listener_pids(port: int) -> list[int]:
    """PIDs listening on `port`, via lsof; an absent lsof or any failure reads as no listeners."""
    if shutil.which("lsof") is None:
        return []
    try:
        output = subprocess.run(
            ["lsof", "-nP", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=SWEEP_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(token) for token in output.stdout.split() if token.isdigit()]


def _owned_listener(pid: int, cwd: str) -> bool:
    """Whether `pid` is one of our servers: matching command line and a known, matching cwd."""
    command = _command_line(pid)
    # The process may be the pipx console script (`claude-workflow-viz`) or the module
    # (`python -m claude_workflow_viz`); either spelling identifies one of ours.
    if SWEEP_MATCH not in command and "claude_workflow_viz" not in command:
        return False
    process_cwd = _cwd_of(pid)
    if process_cwd is None:
        return False  # unknown cwd spared — multi-instance safety
    return os.path.realpath(process_cwd) == os.path.realpath(cwd)


def _command_line(pid: int) -> str:
    try:
        output = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=SWEEP_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return output.stdout.strip()


def _cwd_of(pid: int) -> str | None:
    try:
        output = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=SWEEP_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in output.stdout.splitlines():
        if line.startswith("n") and len(line) > 1:
            return line[1:]
    return None


def _terminate(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + SWEEP_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if not _alive(pid):
            return
        time.sleep(SWEEP_RECHECK_SECONDS)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
