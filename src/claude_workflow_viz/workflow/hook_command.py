"""The `hook` subcommand: forward one Claude Code hook payload to the running server.

Claude Code runs this on every hook event, so it must never disturb the session: it always
returns 0 and writes nothing to stdout or stderr. Every failure (empty or invalid stdin, a payload
we do not track, no connection file, server down, timeout, a non-2xx response, any unexpected
exception) is swallowed by the single catch in `run_hook`.

The POST uses a timeout of `POST_TIMEOUT_SECONDS` (1 second) for connecting and for reading the
response, so a stuck server delays the hook by about a second at most.
"""

import contextlib
import json
import sys
import time
import urllib.request

from claude_workflow_viz.dashboard.connection_file import Connection
from claude_workflow_viz.dashboard.server import LOOPBACK_ADDRESS
from claude_workflow_viz.workflow.events import Event
from claude_workflow_viz.workflow.hook_adapter import normalise

POST_TIMEOUT_SECONDS = 1.0


def run_hook() -> int:
    # The hook must never raise to Claude Code, so even BaseException is swallowed.
    with contextlib.suppress(BaseException):
        _forward_stdin_payload()
    return 0


def _forward_stdin_payload() -> None:
    payload = json.loads(sys.stdin.read())
    event = normalise(payload, time.time)
    if not isinstance(event, Event):
        return
    connection = Connection.read()
    if connection is None:
        return
    request = urllib.request.Request(
        f"http://{LOOPBACK_ADDRESS}:{connection.port}/ingest",
        data=json.dumps(event.to_dict()).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {connection.token}",
        },
        method="POST",
    )
    # An empty ProxyHandler ignores HTTP_PROXY so the token only goes to the local server.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=POST_TIMEOUT_SECONDS):
        pass
