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
from dataclasses import dataclass
from pathlib import Path

STATE_DIR_ENVIRONMENT_VARIABLE = "CLAUDE_WORKFLOW_VIZ_STATE_DIR"
CONNECTION_FILE_NAME = "server.json"


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
        directory = path.parent
        if not directory.exists():
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
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


def _state_directory() -> Path:
    override = os.environ.get(STATE_DIR_ENVIRONMENT_VARIABLE)
    if override:
        return Path(override)
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return base / "claude-workflow-viz"


def _connection_file_path() -> Path:
    return _state_directory() / CONNECTION_FILE_NAME
