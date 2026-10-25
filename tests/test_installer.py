"""Installer behaviour: verify, idempotent settings merge, /viz deployment, summary (FR1/R1-R14).

The verify step runs the real `claude-workflow-viz hook` from the sandbox venv on the real PATH,
and the failure path runs a fake executable script (the sandbox mounts `/tmp` noexec, so the
fake binary lives in an exec-capable temporary directory under the repository root). Everything
else uses `tmp_path` and real file I/O, per the mock policy.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from claude_workflow_viz.install.installer import (
    DEFAULT_VIZ_DIR,
    FIVE_REGISTRATIONS,
    HOOK_COMMAND,
    CommandOutcome,
    Installer,
    InstallError,
)

from _platform import assert_private_mode, path_with_console_scripts

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def on_real_path(monkeypatch):
    monkeypatch.setenv("PATH", path_with_console_scripts())


@pytest.fixture
def failing_binary(monkeypatch):
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as directory:
        if os.name == "nt":
            # `shutil.which` only finds extension-bearing names on Windows
            # (PATHEXT); a `.cmd` file is findable and CreateProcess runs it.
            binary = Path(directory) / "claude-workflow-viz.cmd"
            binary.write_text("@echo boom 1>&2\r\n@exit /b 3\r\n", encoding="utf-8")
        else:
            binary = Path(directory) / "claude-workflow-viz"
            binary.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
            binary.chmod(0o755)
        monkeypatch.setenv("PATH", directory)
        yield binary


def _settings_path(repo: Path) -> Path:
    return repo / ".claude" / "settings.local.json"


def _command_path(repo: Path) -> Path:
    return repo / ".claude" / "commands" / "viz.md"


def test_fresh_install_writes_five_registrations_and_command(tmp_path, on_real_path):
    summary = Installer().run(tmp_path, None, False)

    assert summary.binary_path == shutil.which("claude-workflow-viz")
    assert summary.hooks_added == tuple(registration.event for registration in FIVE_REGISTRATIONS)
    assert summary.hooks_present == 0
    assert summary.command_outcome == CommandOutcome.CREATED
    assert summary.viz_dir == str(DEFAULT_VIZ_DIR)

    settings = json.loads(_settings_path(tmp_path).read_text(encoding="utf-8"))
    assert set(settings) == {"hooks"}
    hooks = settings["hooks"]
    assert set(hooks) == {registration.event for registration in FIVE_REGISTRATIONS}
    assert hooks["PreToolUse"][0]["matcher"] == "Workflow"
    assert hooks["PreToolUse"][0]["hooks"][0]["command"] == HOOK_COMMAND
    assert hooks["PostToolUse"][0]["matcher"] == "Workflow"
    assert hooks["SubagentStart"][0]["hooks"][0]["command"] == HOOK_COMMAND
    assert hooks["SubagentStop"][0]["hooks"][0]["command"] == HOOK_COMMAND
    assert hooks["SessionEnd"][0]["hooks"][0]["command"] == HOOK_COMMAND

    assert str(DEFAULT_VIZ_DIR) in _command_path(tmp_path).read_text(encoding="utf-8")
    assert_private_mode(_settings_path(tmp_path), 0o600)


def test_second_install_writes_nothing(tmp_path, on_real_path):
    Installer().run(tmp_path, None, False)
    settings_bytes = _settings_path(tmp_path).read_bytes()
    command_bytes = _command_path(tmp_path).read_bytes()

    summary = Installer().run(tmp_path, None, False)

    assert summary.hooks_added == ()
    assert summary.hooks_present == 5
    assert summary.command_outcome == CommandOutcome.SKIPPED
    assert _settings_path(tmp_path).read_bytes() == settings_bytes
    assert _command_path(tmp_path).read_bytes() == command_bytes


def test_merge_preserves_unrelated_hooks_and_appends_only_missing(tmp_path, on_real_path):
    (tmp_path / ".claude").mkdir()
    _settings_path(tmp_path).write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Edit", "hooks": [{"type": "command", "command": "lint"}]},
                        {
                            "matcher": "Workflow",
                            "hooks": [{"type": "command", "command": HOOK_COMMAND, "async": True}],
                        },
                    ],
                    "SubagentStart": [{"hooks": [{"type": "command", "command": "other"}]}],
                },
                "permissions": {"allow": ["Read"]},
            }
        ),
        encoding="utf-8",
    )

    summary = Installer().run(tmp_path, None, False)

    assert summary.hooks_added == ("PostToolUse", "SubagentStart", "SubagentStop", "SessionEnd")
    assert summary.hooks_present == 1

    merged = json.loads(_settings_path(tmp_path).read_text(encoding="utf-8"))
    assert merged["permissions"] == {"allow": ["Read"]}
    pre = merged["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "Edit"
    assert pre[0]["hooks"][0]["command"] == "lint"
    assert sum(HOOK_COMMAND in json.dumps(entry) for entry in pre) == 1
    subagent = merged["hooks"]["SubagentStart"]
    assert subagent[0]["hooks"][0]["command"] == "other"
    assert subagent[1]["hooks"][0]["command"] == HOOK_COMMAND


def test_all_present_preserves_bytes_and_skips_command(tmp_path, on_real_path):
    (tmp_path / ".claude").mkdir()
    entry = {"command": HOOK_COMMAND, "type": "command", "async": True}
    settings_text = (
        json.dumps(
            {
                "hooks": {
                    "SessionEnd": [{"hooks": [entry]}],
                    "PreToolUse": [{"matcher": "Workflow", "hooks": [entry]}],
                    "SubagentStop": [{"hooks": [entry]}],
                    "SubagentStart": [{"hooks": [entry]}],
                    "PostToolUse": [{"matcher": "Workflow", "hooks": [entry]}],
                }
            },
            indent=2,
        )
        + "\n"
    )
    _settings_path(tmp_path).write_text(settings_text, encoding="utf-8")
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    _command_path(tmp_path).write_text("existing", encoding="utf-8")

    summary = Installer().run(tmp_path, None, False)

    assert summary.hooks_added == ()
    assert summary.command_outcome == CommandOutcome.SKIPPED
    assert _settings_path(tmp_path).read_text(encoding="utf-8") == settings_text
    assert _command_path(tmp_path).read_text(encoding="utf-8") == "existing"


def test_invalid_settings_json_raises_and_writes_nothing(tmp_path, on_real_path):
    (tmp_path / ".claude").mkdir()
    _settings_path(tmp_path).write_text("{ not json", encoding="utf-8")

    with pytest.raises(InstallError) as error:
        Installer().run(tmp_path, None, False)

    assert "settings.local.json" in str(error.value)
    assert not (tmp_path / ".claude" / "commands").exists()


def test_unreadable_settings_raises_and_writes_nothing(tmp_path, on_real_path):
    (tmp_path / ".claude").mkdir()
    _settings_path(tmp_path).write_bytes(b'{"hooks": "\xff"}')

    with pytest.raises(InstallError) as error:
        Installer().run(tmp_path, None, False)

    assert "settings.local.json" in str(error.value)
    assert not (tmp_path / ".claude" / "commands").exists()


def test_missing_binary_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(InstallError) as error:
        Installer().run(tmp_path, None, False)
    assert "not on PATH" in str(error.value)


def test_verify_nonzero_exit_raises_with_output(tmp_path, failing_binary):
    with pytest.raises(InstallError) as error:
        Installer().run(tmp_path, None, False)
    message = str(error.value)
    assert "exited 3" in message
    assert "boom" in message
    assert not (tmp_path / ".claude").exists()


def test_existing_command_is_skipped_without_force(tmp_path, on_real_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    _command_path(tmp_path).write_text("old", encoding="utf-8")

    summary = Installer().run(tmp_path, None, False)

    assert summary.command_outcome == CommandOutcome.SKIPPED
    assert _command_path(tmp_path).read_text(encoding="utf-8") == "old"


def test_force_overwrites_an_existing_command(tmp_path, on_real_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    _command_path(tmp_path).write_text("old", encoding="utf-8")

    summary = Installer().run(tmp_path, None, True)

    assert summary.command_outcome == CommandOutcome.FORCED
    command = _command_path(tmp_path).read_text(encoding="utf-8")
    assert str(DEFAULT_VIZ_DIR) in command
    assert "old" not in command


def test_viz_dir_flag_is_recorded_in_the_command_and_summary(tmp_path, on_real_path):
    summary = Installer().run(tmp_path, Path("custom/viz"), False)

    assert summary.viz_dir == "custom/viz"
    assert "custom/viz" in _command_path(tmp_path).read_text(encoding="utf-8")
