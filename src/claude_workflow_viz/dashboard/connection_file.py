"""Ingest token generation and the connection file that lets `hook` find `serve`.

Decision: `serve` generates a token with `secrets.token_urlsafe` and writes a JSON connection
file `{"port": ..., "token": ...}` to `server.json` in the state directory. `hook` reads the same
file to learn the port and token.

State directory, first match wins:

1. `$CLAUDE_WORKFLOW_VIZ_STATE_DIR` (used as is; tests point this at `tmp_path`)
2. `$XDG_STATE_HOME/claude-workflow-viz`
3. `~/.local/state/claude-workflow-viz`

The file has mode 0600 and a directory this module creates has mode 0700. The file is created
with that mode from the start in a temporary file next to the target and moved into place with
`os.replace`, so a reader never sees a partial file and the token is never briefly world readable.

`serve` removes the file on shutdown, but only while it still holds its own token.

The connection owns its persistence: `Connection.read()` reads the file (never raising — a
missing, unreadable or malformed file reads as `None`), `connection.write()` writes it, and
`Connection.remove_if_token_matches(token)` deletes it while it still holds `token`.
"""

import hmac
import json
import os
import secrets
import urllib.request
from dataclasses import dataclass
from pathlib import Path

STATE_DIR_ENVIRONMENT_VARIABLE = "CLAUDE_WORKFLOW_VIZ_STATE_DIR"
CONNECTION_FILE_NAME = "server.json"
LOOPBACK_ADDRESS = "127.0.0.1"
STOP_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class Connection:
    port: int
    token: str

    @classmethod
    def read(cls) -> "Connection | None":
        """Read the connection file; never raises — missing/unreadable/malformed reads as None."""
        try:
            data = json.loads(_connection_file_path().read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        if not isinstance(data, dict):
            return None
        port, token = data.get("port"), data.get("token")
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            return None
        if not isinstance(token, str) or not token:
            return None
        return cls(port=port, token=token)

    def write(self) -> Path:
        """Atomically write this connection to the connection file; returns its path."""
        path = _connection_file_path()
        directory = ensure_state_directory()
        temporary = directory / f".{CONNECTION_FILE_NAME}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"port": self.port, "token": self.token}, handle)
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return path

    @classmethod
    def stop_server(cls) -> None:
        """POST /shutdown to the running server; no-op without a connection file; never raises.

        The SessionEnd branch must never fail (NFR2), so every failure is swallowed here:
        a dead port, a non-2xx response, a timeout, or an unexpected exception.
        """
        connection = cls.read()
        if connection is None:
            return
        request = urllib.request.Request(
            f"http://{LOOPBACK_ADDRESS}:{connection.port}/shutdown",
            headers={"Authorization": f"Bearer {connection.token}"},
            method="POST",
        )
        # An empty ProxyHandler ignores HTTP_PROXY so the token only goes to the local server.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=STOP_TIMEOUT_SECONDS):
                pass
        except BaseException:
            return

    @classmethod
    def remove_if_token_matches(cls, token: str) -> None:
        """Delete the connection file only while it still holds `token`; never raises if missing."""
        connection = cls.read()
        if connection is None or not tokens_match(token, connection.token):
            return
        _connection_file_path().unlink(missing_ok=True)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(expected: str, provided: str | None) -> bool:
    """Constant-time comparison; an empty or missing token never matches."""
    if not expected or not provided:
        return False
    try:
        return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))
    except UnicodeError:
        return False


def state_directory() -> Path:
    override = os.environ.get(STATE_DIR_ENVIRONMENT_VARIABLE)
    if override:
        return Path(override)
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "claude-workflow-viz"


def ensure_state_directory() -> Path:
    """Create the state directory with mode 0700 and return it; never raises.

    Several writers may be the first to create the state dir (the bootstrap's cache write and
    detached spawn, the debug-log helper), so they share this helper rather than each repeating
    the mode. `mkdir(mode=0o700)` is enough for a new directory; the chmod tightens a directory
    an earlier run left at a permissive mode.
    """
    directory = state_directory()
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
    except OSError:
        pass
    return directory


def _connection_file_path() -> Path:
    return state_directory() / CONNECTION_FILE_NAME
