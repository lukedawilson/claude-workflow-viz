"""Invoke-time bootstrap: parse, spawn or reuse the server, then open the dashboard.

`Bootstrap.run` is the Workflow PreToolUse branch (FR6/Q2). It reads the connection file and
probes `/graph` to decide reuse; it always parses the invoked workflow (Unit A) and, on a
`Graph`, overwrites that workflow's transient cache yaml (R2/R17/R18). A server is spawned only
when none is live; the spawn is detached with stdout/stderr going to the state-dir debug log
(NFRB3/R3). The connection-file wait is bounded at 10 seconds (R6), after which the dashboard
opens only if the file appeared (R7/R19/UEB6). Every failure is swallowed here or by the hook
dispatcher's silence wrapper (R13/NFR2).
"""

import contextlib
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from claude_workflow_viz.dashboard.connection_file import (
    LOOPBACK_ADDRESS,
    Connection,
    ensure_state_directory,
    state_directory,
)
from claude_workflow_viz.dashboard.server import PREFERRED_PORT
from claude_workflow_viz.graph.graph import Graph, safe_workflow_name
from claude_workflow_viz.graph_source.parse_failures import (
    DEBUG_LOG_NAME,
    ParseFailureReport,
    append_debug_log,
)
from claude_workflow_viz.graph_source.parser import WorkflowSource
from claude_workflow_viz.invoke._platform import open_url, sweep_preferred_port

CONNECTION_WAIT_SECONDS = 10.0
PROBE_TIMEOUT_SECONDS = 1.0
CONNECTION_POLL_SECONDS = 0.05


def _workflow_name(payload: Mapping[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return ""
    name = tool_input.get("name")
    return safe_workflow_name(name) if isinstance(name, str) else ""


def _workflow_source_path(payload: Mapping[str, Any], workflow: str) -> Path:
    cwd = payload.get("cwd")
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    return base / ".claude" / "workflows" / f"{workflow}.js"


def _cache_path(workflow: str) -> Path:
    return state_directory() / "graphs" / f"{workflow}.viz.yaml"


def _serve_arguments(workflow: str, parsed: Graph | ParseFailureReport | None) -> list[str]:
    arguments = [sys.executable, "-m", "claude_workflow_viz", "serve"]
    if isinstance(parsed, Graph) and workflow:
        arguments += ["--graph", str(_cache_path(workflow))]
    return arguments


def _dashboard_url(connection: Connection, workflow: str) -> str:
    url = f"http://{LOOPBACK_ADDRESS}:{connection.port}/?token={connection.token}"
    if workflow:
        url += f"&workflow={urllib.parse.quote(workflow, safe='')}"
    return url


def _probe_live(connection: Connection) -> bool:
    """Whether the connection's server answers `GET /graph` with the stored token (R11)."""
    try:
        request = urllib.request.Request(
            f"http://{LOOPBACK_ADDRESS}:{connection.port}/graph?token={connection.token}",
            method="GET",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            return response.status == 200
    except BaseException:
        return False


def _spawn_detached(arguments: list[str]) -> None:
    """Spawn the server detached, its output appended to the state-dir debug log (R3/NRB1).

    The state dir is created 0700 and the log handle 0600 (mirroring `Connection.write`), so a
    fresh XDG state dir never ends up world-readable. The stream goes straight to the file
    handle, bypassing `append_debug_log`'s ~1 MiB cap; accepted because the server's own output
    is a two-line startup banner and the log is a diagnosis channel.
    """
    try:
        directory = ensure_state_directory()
        log_path = directory / DEBUG_LOG_NAME
        with log_path.open("ab") as handle:
            os.chmod(log_path, 0o600)
            subprocess.Popen(
                arguments,
                stdout=handle,
                stderr=handle,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
    except OSError:
        return


def _wait_for_connection(previous: Connection | None = None) -> Connection | None:
    """Wait for the connection file to appear (or change), bounded at 10 seconds (R6).

    `previous` is the stale connection read before the spawn; a still-present stale file must
    not be mistaken for the new server's file, so it is excluded until it is replaced.
    """
    deadline = time.monotonic() + CONNECTION_WAIT_SECONDS
    while time.monotonic() < deadline:
        connection = Connection.read()
        if connection is not None and connection != previous:
            return connection
        time.sleep(CONNECTION_POLL_SECONDS)
    return None


class Bootstrap:
    """Invoke-time orchestrator; the seams (`spawn`, `probe`, `open_browser`, `wait`) are the
    external boundaries tests may replace with real local stand-ins."""

    def __init__(
        self,
        *,
        spawn: Callable[[list[str]], None] | None = None,
        probe: Callable[[Connection], bool] | None = None,
        open_browser: Callable[[str], None] | None = None,
        sweep: Callable[[int], None] | None = None,
        wait: Callable[[Connection | None], Connection | None] | None = None,
    ) -> None:
        self._spawn = spawn or _spawn_detached
        self._probe = probe or _probe_live
        self._open_browser = open_browser or open_url
        self._sweep = sweep or sweep_preferred_port
        self._wait = wait or _wait_for_connection

    def run(self, payload: Mapping[str, Any]) -> None:
        """Run the invoke-time bootstrap; never raises past the dispatcher."""
        with contextlib.suppress(BaseException):
            self._run(payload)

    def _run(self, payload: Mapping[str, Any]) -> None:
        workflow = _workflow_name(payload)
        connection = Connection.read()
        live = connection is not None and self._probe(connection)

        parsed = _parse_workflow(payload, workflow)
        if isinstance(parsed, Graph):
            self._write_cache(workflow, parsed)
        else:
            _log_parse_result(parsed, workflow)

        if not live:
            self._sweep(PREFERRED_PORT)
            self._spawn(_serve_arguments(workflow, parsed))
            connection = self._wait(connection)

        if connection is not None:
            self._open_browser(_dashboard_url(connection, workflow))

    def _write_cache(self, workflow: str, graph: Graph) -> None:
        if not workflow:
            return
        path = _cache_path(workflow)
        try:
            ensure_state_directory()
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_text(graph.to_yaml(), encoding="utf-8")
        except OSError as error:
            append_debug_log(f"cache write failed for {workflow}: {error}", state_directory())


def _parse_workflow(payload: Mapping[str, Any], workflow: str) -> Graph | ParseFailureReport | None:
    if not workflow:
        return None
    path = _workflow_source_path(payload, workflow)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return WorkflowSource(text, path).parse()


def _log_parse_result(parsed: ParseFailureReport | None, workflow: str) -> None:
    if isinstance(parsed, ParseFailureReport):
        append_debug_log(parsed.summarise(), state_directory())
    else:
        append_debug_log(
            f"workflow {workflow or '<unknown>'}: no parseable source; serving linearly",
            state_directory(),
        )


def run(payload: Mapping[str, Any]) -> None:
    """Module entry point: run the default Bootstrap."""
    Bootstrap().run(payload)
