"""Localhost server: token-guarded event ingest and a live server-sent events (SSE) stream.

The socket is bound to 127.0.0.1 only; there is deliberately no option to bind another address.
Every route accepts only a `Host` header of `127.0.0.1:<port>` or `localhost:<port>` (the IPv6
form `[::1]:<port>` is not accepted because the server binds IPv4 only); a missing or any other
Host answers 421 Misdirected Request with an empty body, before the token check. A connection
whose socket read stalls for `request_timeout_seconds` (10 by default) is closed.
On start the server generates a token and writes the connection file (see `connection_file`)
with the port it actually bound.

Endpoints
---------
`POST /ingest`
    Header `Authorization: Bearer <token>`. Body: one JSON event (see `events.Event`), at most
    `MAXIMUM_BODY_BYTES`. Responses: 204 applied, 400 bad JSON or invalid event, 401 missing or
    wrong token, 413 body too large. A body shorter than its Content-Length closes the connection
    once the read times out.

`GET /stream?token=<token>`
    The token is a query parameter because a browser `EventSource` cannot set headers. Responds
    `text/event-stream`: first one `snapshot` event holding the current run state, then one
    `event` per applied event, with a `: keep-alive` comment every `keepalive_seconds` when idle.
    The server subscribes and snapshots under one lock (`RunState.subscribe_with_snapshot`), so
    each event is in the snapshot or delivered afterwards: never lost, never in both.

`GET /graph?token=<token>`
    Same token check as `/stream`. JSON `{"graph", "source", "status_rules"}`; `source` is
    `config` when `serve --graph` supplied the graph, else `linear` (one node per stage, or step
    key when a step has no stage, seen so far in first-seen order).

`GET /` and `GET /static/<name>`
    The web UI from the package's `static` directory. Only names found by listing that directory
    at start with a `.html`, `.js`, `.css` or `.json` extension are served; anything else
    (including `VENDORED.md`, `mermaid.LICENSE` and traversal attempts) answers 404.

Any other path answers 404. The Host check runs first, then the token check, before the body
is read.
"""

import errno
import json
import queue
import signal
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlsplit

from claude_workflow_viz.dashboard.connection_file import (
    LOOPBACK_ADDRESS,
    Connection,
    generate_token,
    state_directory,
    tokens_match,
)
from claude_workflow_viz.graph.graph import Graph, GraphError, safe_workflow_name
from claude_workflow_viz.workflow.events import Event, EventError
from claude_workflow_viz.workflow.run_state import RunState

PREFERRED_PORT = 8322
MAXIMUM_BODY_BYTES = 64 * 1024
DEFAULT_KEEPALIVE_SECONDS = 15.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
_DRAIN_LIMIT_BYTES = 1024 * 1024
_BEARER_PREFIX = "Bearer "
_STATIC_PREFIX = "/static/"
_INDEX_NAME = "index.html"
_STATUS_RULES_NAME = "status_rules.json"
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
}
_CONTENT_SECURITY_POLICY = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"


def _static_directory() -> resources.abc.Traversable:
    return resources.files("claude_workflow_viz").joinpath("static")


class VisualiserServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"

    def __init__(
        self,
        port: int,
        token: str,
        keepalive_seconds: float,
        graph: Graph | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__((LOOPBACK_ADDRESS, port), _Handler)
        self.graph = graph
        self.static_names = frozenset(
            entry.name
            for entry in _static_directory().iterdir()
            if entry.is_file() and any(entry.name.endswith(suffix) for suffix in _CONTENT_TYPES)
        )
        self.state = RunState()
        self.workflow_graphs: dict[str, Graph] = {}
        self.token = token
        self.keepalive_seconds = keepalive_seconds
        self.request_timeout_seconds = request_timeout_seconds

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def graph_for(self, workflow: str | None = None) -> tuple[Graph, str]:
        """Return `(graph, source)` for a request: the registry entry, the default, or linear.

        `workflow` names a per-workflow graph loaded on demand from
        `<state>/graphs/<workflow>.viz.yaml` and cached in memory. An unknown name, or a file
        that fails to load, degrades to a linear graph for that request (R15).
        """
        if workflow:
            loaded = self._load_workflow_graph(workflow)
            if loaded is not None:
                return loaded, "config"
            return self._linear_graph(), "linear"
        if self.graph is not None:
            return self.graph, "config"
        return self._linear_graph(), "linear"

    def _load_workflow_graph(self, name: str) -> Graph | None:
        safe = safe_workflow_name(name)
        if not safe:
            return None
        cached = self.workflow_graphs.get(safe)
        if cached is not None:
            return cached
        loaded = Graph.load(state_directory() / "graphs" / f"{safe}.viz.yaml")
        if isinstance(loaded, GraphError):
            return None
        self.workflow_graphs[safe] = loaded
        return loaded

    def _linear_graph(self) -> Graph:
        seen = [
            step["stage"] or key
            for session in self.state.snapshot()["sessions"].values()
            for key, step in session["steps"].items()
        ]
        return Graph.linear(seen)


def start_server(
    port: int = PREFERRED_PORT,
    keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
    graph: Graph | None = None,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> VisualiserServer:
    """Bind, generate the token and write the connection file; the caller runs `serve_forever`.

    The preferred port 8322 is tried first; when it is busy the server rebinds port 0 so the
    OS picks a free one (a busy port degrades, never fails — NRB5). Any other explicit port
    that is busy still fails fast.
    """
    token = generate_token()
    try:
        server = VisualiserServer(port, token, keepalive_seconds, graph, request_timeout_seconds)
    except OSError as error:
        if port != PREFERRED_PORT or error.errno != errno.EADDRINUSE:
            raise
        server = VisualiserServer(0, token, keepalive_seconds, graph, request_timeout_seconds)
    try:
        Connection(server.port, server.token).write()
    except BaseException:
        server.server_close()
        raise
    return server


def serve(port: int = PREFERRED_PORT, graph: Graph | None = None) -> None:
    """Run until interrupted (SIGINT or SIGTERM), close the socket, remove our connection file."""
    server = start_server(port, graph=graph)
    address = f"http://{LOOPBACK_ADDRESS}:{server.port}"
    print(f"claude-workflow-viz listening on {address}", flush=True)
    # The token URL is only meaningful to a human at a terminal. A detached bootstrap spawn
    # redirects stdout to the state-dir debug log, so gating on the tty keeps the token out of
    # that log (SECURITY-03: the token is never logged).
    if sys.stdout is not None and sys.stdout.isatty():
        print(f"open the UI at {address}/?token={server.token}", flush=True)

    def interrupt(signal_number: int, frame: object) -> None:
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, interrupt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        server.server_close()
        Connection(server.port, server.token).remove_if_token_matches(server.token)


class _Handler(BaseHTTPRequestHandler):
    server: VisualiserServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence per-request logging; the request line can carry the stream token."""

    def setup(self) -> None:
        self.timeout = self.server.request_timeout_seconds
        super().setup()

    def _host_is_allowed(self) -> bool:
        port = self.server.port
        return self.headers.get("Host") in (f"{LOOPBACK_ADDRESS}:{port}", f"localhost:{port}")

    def do_POST(self) -> None:
        if not self._host_is_allowed():
            self._respond(HTTPStatus.MISDIRECTED_REQUEST)
            return
        location = urlsplit(self.path).path
        if location == "/shutdown":
            self._shutdown()
            return
        if location != "/ingest":
            self._respond(HTTPStatus.NOT_FOUND)
            return
        authorisation = self.headers.get("Authorization", "")
        provided = (
            authorisation[len(_BEARER_PREFIX) :]
            if authorisation.startswith(_BEARER_PREFIX)
            else None
        )
        if not tokens_match(self.server.token, provided):
            self._respond(HTTPStatus.UNAUTHORIZED)
            return
        body = self._read_body()
        if body is None:
            return
        try:
            event = Event.from_dict(json.loads(body.decode("utf-8")))
        except (ValueError, RecursionError):
            self._respond(HTTPStatus.BAD_REQUEST)
            return
        if isinstance(event, EventError):
            self._respond(HTTPStatus.BAD_REQUEST)
            return
        self.server.state.apply(event)
        self._respond(HTTPStatus.NO_CONTENT)

    def _shutdown(self) -> None:
        """Authenticated stop: deny on a bad or missing token, 204 and stop on success.

        Only a request carrying the server's own token stops it. `shutdown()` waits for the
        `serve_forever` loop (running on another thread) to finish, so it never deadlocks a
        handler thread. The connection file is removed with the same sequence as SIGINT.
        """
        authorisation = self.headers.get("Authorization", "")
        provided = (
            authorisation[len(_BEARER_PREFIX) :]
            if authorisation.startswith(_BEARER_PREFIX)
            else None
        )
        if not tokens_match(self.server.token, provided):
            self._respond(HTTPStatus.UNAUTHORIZED)
            return
        port, token = self.server.port, self.server.token
        self._respond(HTTPStatus.NO_CONTENT)
        # `server_close()` joins this server's request threads, so it must not run on the
        # handler thread itself (a self-join). A short-lived thread owns the stop instead.
        threading.Thread(target=self._stop_and_cleanup, args=(port, token), daemon=True).start()

    def _stop_and_cleanup(self, port: int, token: str) -> None:
        """Stop `serve_forever`, close the socket, remove our connection file (SIGINT sequence)."""
        self.server.shutdown()
        self.server.server_close()
        Connection(port, token).remove_if_token_matches(token)

    def do_GET(self) -> None:
        if not self._host_is_allowed():
            self._respond(HTTPStatus.MISDIRECTED_REQUEST)
            return
        location = urlsplit(self.path)
        if location.path == "/":
            self._serve_static(_INDEX_NAME)
        elif location.path.startswith(_STATIC_PREFIX):
            self._serve_static(location.path[len(_STATIC_PREFIX) :])
        elif location.path in ("/stream", "/graph"):
            provided = parse_qs(location.query).get("token", [None])[0]
            if not tokens_match(self.server.token, provided):
                self._respond(HTTPStatus.UNAUTHORIZED)
            elif location.path == "/stream":
                self._stream()
            else:
                workflow = parse_qs(location.query).get("workflow", [None])[0]
                self._graph(workflow)
        else:
            self._respond(HTTPStatus.NOT_FOUND)

    def _graph(self, workflow: str | None = None) -> None:
        graph, source = self.server.graph_for(workflow)
        rules = json.loads(_static_directory().joinpath(_STATUS_RULES_NAME).read_text("utf-8"))
        document = {
            "graph": graph.to_dict(),
            "source": source,
            "status_rules": rules,
        }
        self._send(HTTPStatus.OK, json.dumps(document).encode("utf-8"), _CONTENT_TYPES[".json"])

    def _serve_static(self, name: str) -> None:
        if name not in self.server.static_names:
            self._respond(HTTPStatus.NOT_FOUND)
            return
        content = _static_directory().joinpath(name).read_bytes()
        suffix = name[name.rindex(".") :]
        self._send(HTTPStatus.OK, content, _CONTENT_TYPES[suffix], hardened=True)

    def _send(
        self, status: HTTPStatus, body: bytes, content_type: str, hardened: bool = False
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if hardened:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes | None:
        """Return the body, or send the error response and return None."""
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            length = -1
        if length < 0:
            self._respond(HTTPStatus.BAD_REQUEST)
            return None
        if length > MAXIMUM_BODY_BYTES:
            # Discard a bounded amount so the client can finish sending and read the response.
            self.rfile.read(min(length, _DRAIN_LIMIT_BYTES))
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        try:
            return self.rfile.read(length)
        except OSError:  # includes the read timeout: the client sent fewer bytes than declared
            self.close_connection = True
            return None

    def _stream(self) -> None:
        state = self.server.state
        subscriber, snapshot = state.subscribe_with_snapshot()
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self._write(_sse("snapshot", snapshot))
            while True:
                try:
                    event = subscriber.get(timeout=self.server.keepalive_seconds)
                except queue.Empty:
                    self._write(": keep-alive\n\n")
                    continue
                self._write(_sse("event", event.to_dict()))
        except OSError:
            pass  # client disconnected
        finally:
            state.unsubscribe(subscriber)

    def _write(self, text: str) -> None:
        self.wfile.write(text.encode("utf-8"))
        self.wfile.flush()

    def _respond(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _sse(name: str, payload: object) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"
