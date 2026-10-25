import json
import os

import pytest

from _platform import assert_private_mode
from claude_workflow_viz.dashboard.connection_file import (
    Connection,
    ensure_state_directory,
    generate_token,
    tokens_match,
)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(directory))
    return directory


def test_persistence_lives_on_the_connection_entity():
    assert callable(Connection.read)
    assert callable(Connection.remove_if_token_matches)
    assert callable(Connection(1, "t").write)


def test_written_file_is_private_and_directory_is_private(state_dir):
    path = Connection(port=8123, token="secret").write()
    assert_private_mode(path, 0o600)
    assert_private_mode(state_dir, 0o700)


def test_ensure_state_directory_creates_a_private_directory(state_dir):
    assert ensure_state_directory() == state_dir
    assert_private_mode(state_dir, 0o700)


def test_ensure_state_directory_tightens_an_existing_permissive_directory(state_dir):
    state_dir.mkdir()
    state_dir.chmod(0o755)
    ensure_state_directory()
    assert_private_mode(state_dir, 0o700)


def test_write_then_read_round_trips_port_and_token(state_dir):
    Connection(port=8123, token="secret").write()
    assert Connection.read() == Connection(port=8123, token="secret")


def test_second_write_replaces_first_and_leaves_no_temporary_files(state_dir):
    Connection(port=1, token="a").write()
    Connection(port=2, token="b").write()
    assert Connection.read() == Connection(port=2, token="b")
    assert [entry.name for entry in state_dir.iterdir()] == ["server.json"]


def test_state_dir_override_takes_precedence_over_xdg_state_home(state_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    path = Connection(port=1, token="a").write()
    assert path == state_dir / "server.json"


def test_xdg_state_home_is_honoured(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    path = Connection(port=1, token="a").write()
    assert path == tmp_path / "xdg" / "claude-workflow-viz" / "server.json"
    assert Connection.read() == Connection(port=1, token="a")


def test_default_location_is_under_home_local_state(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() on Windows
    path = Connection(port=1, token="a").write()
    assert path == tmp_path / ".local" / "state" / "claude-workflow-viz" / "server.json"


def test_missing_file_reads_as_none(state_dir):
    assert Connection.read() is None


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "",
        "[]",
        '{"token": "t"}',
        '{"port": 1}',
        '{"port": "1", "token": "t"}',
        '{"port": true, "token": "t"}',
        '{"port": 1, "token": 5}',
        '{"port": 1, "token": ""}',
        '{"port": 0, "token": "t"}',
    ],
)
def test_malformed_file_reads_as_none(state_dir, content):
    state_dir.mkdir()
    (state_dir / "server.json").write_text(content)
    assert Connection.read() is None


def test_non_utf8_file_reads_as_none(state_dir):
    state_dir.mkdir()
    (state_dir / "server.json").write_bytes(b"\xff\xfe\x00")
    assert Connection.read() is None


def test_unreadable_file_reads_as_none(state_dir):
    path = Connection(port=1, token="a").write()
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("running with privileges that ignore file modes")
        assert Connection.read() is None
    finally:
        path.chmod(0o600)


def test_directory_in_place_of_file_reads_as_none(state_dir):
    (state_dir / "server.json").mkdir(parents=True)
    assert Connection.read() is None


def test_file_content_is_json_with_port_and_token(state_dir):
    path = Connection(port=9, token="t").write()
    assert json.loads(path.read_text()) == {"port": 9, "token": "t"}


def test_generated_tokens_are_long_and_distinct():
    first, second = generate_token(), generate_token()
    assert first != second
    assert len(first) >= 32


def test_tokens_match_accepts_equal_and_rejects_wrong_or_empty():
    assert tokens_match("secret", "secret")
    assert not tokens_match("secret", "wrong")
    assert not tokens_match("secret", "")
    assert not tokens_match("secret", None)
    assert not tokens_match("", "")
    assert not tokens_match("secret", "sécret")


def test_deeply_nested_json_reads_as_none(state_dir):
    state_dir.mkdir()
    (state_dir / "server.json").write_text("[" * 100000)
    assert Connection.read() is None


def test_tokens_match_returns_false_for_unencodable_input_on_either_side():
    assert tokens_match("abc", "\ud800") is False
    assert tokens_match("\ud800", "abc") is False


def test_remove_deletes_file_holding_the_same_token(state_dir):
    path = Connection(port=8123, token="mine").write()
    Connection.remove_if_token_matches("mine")
    assert not path.exists()


def test_remove_leaves_file_holding_another_token(state_dir):
    path = Connection(port=8123, token="newer").write()
    Connection.remove_if_token_matches("mine")
    assert path.exists()
    assert Connection.read() == Connection(port=8123, token="newer")


def test_remove_tolerates_a_missing_file(state_dir):
    Connection.remove_if_token_matches("mine")
