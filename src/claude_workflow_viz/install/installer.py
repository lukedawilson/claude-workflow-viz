"""Install-time bootstrap for one repo (FR1/FR7/D9).

The installer writes the five hook registrations into `.claude/settings.local.json` and deploys
the `/viz` command into `.claude/commands/viz.md`. It runs only at a human's terminal (UEC4-A):
the hook path never imports it, so an install can never disturb a session.

Hard stops (invalid settings JSON, a failing or missing verification binary) raise `InstallError`
at the boundary; `cli` catches and prints (D8-B, UC5-B). Every repo write is atomic
(temp file in the same directory + `os.replace`, NFRC1-A), the fresh settings file is 0600
(NFRC3-A), and the merge appends only the missing registrations (NFRC4-A, UC2-C).
"""

import json
import os
import secrets
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from claude_workflow_viz.graph_source.parse_failures import (
    VIZ_COMMAND_TEMPLATE,
    VIZ_DIR_PLACEHOLDER,
)

HOOK_COMMAND = "claude-workflow-viz hook"
DEFAULT_VIZ_DIR = Path(".claude-local", "viz")
CLAUDE_DIR = Path(".claude")
COMMANDS_DIR = Path(".claude", "commands")
SETTINGS_FILE_NAME = "settings.local.json"
COMMAND_FILE_NAME = "viz.md"
VERIFY_TIMEOUT_SECONDS = 30.0
_SETTINGS_MODE = 0o600
_COMMAND_MODE = 0o644


class InstallError(Exception):
    """A terminal install failure at the interactive boundary (D8-B)."""


@dataclass(frozen=True)
class HookRegistration:
    """One hook registration; identity for the merge is its event name (NFRC4-A)."""

    event: str
    matcher: str | None = None

    @property
    def command(self) -> str:
        return HOOK_COMMAND

    def settings_entry(self) -> dict[str, Any]:
        """The settings.local.json list entry this registration contributes (R2)."""
        entry: dict[str, Any] = {
            "hooks": [{"type": "command", "command": self.command, "async": True}],
        }
        if self.matcher is not None:
            entry["matcher"] = self.matcher
        return entry


FIVE_REGISTRATIONS: tuple[HookRegistration, ...] = (
    HookRegistration("PreToolUse", "Workflow"),
    HookRegistration("PostToolUse", "Workflow"),
    HookRegistration("SubagentStart"),
    HookRegistration("SubagentStop"),
    HookRegistration("SessionEnd"),
)


class CommandOutcome(StrEnum):
    CREATED = "created"
    SKIPPED = "skipped"
    FORCED = "forced"


@dataclass(frozen=True)
class InstallSummary:
    """The record of what an install did; rendered as the UC6-A output."""

    binary_path: str
    hooks_added: tuple[str, ...]
    hooks_present: int
    command_outcome: CommandOutcome
    viz_dir: str

    def render(self) -> str:
        lines = [f"verified: {self.binary_path}"]
        if self.hooks_added:
            line = "hooks: added " + ", ".join(self.hooks_added)
            if self.hooks_present:
                line += f" ({self.hooks_present} already present)"
            lines.append(line)
        else:
            lines.append(f"hooks: already present ({self.hooks_present})")
        lines.append(f"command: {self.command_outcome.value} {COMMANDS_DIR / COMMAND_FILE_NAME}")
        lines.append(f"viz-dir: {self.viz_dir}")
        lines.append("run a workflow to see the dashboard")
        return "\n".join(lines)


def _contains_registration(value: Any) -> bool:
    """Whether `value` holds a registration whose command is `claude-workflow-viz hook` (R1)."""
    if isinstance(value, Mapping):
        if value.get("command") == HOOK_COMMAND:
            return True
        return any(_contains_registration(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_registration(item) for item in value)
    return False


def _missing_registrations(settings: Mapping[str, Any]) -> list[HookRegistration]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, Mapping):
        hooks = {}
    return [
        registration
        for registration in FIVE_REGISTRATIONS
        if not _contains_registration(hooks.get(registration.event))
    ]


def _merge(settings: Mapping[str, Any], missing: Sequence[HookRegistration]) -> dict[str, Any]:
    """Append the missing registrations to their hook lists, touching nothing else (UC2-C)."""
    merged = dict(settings)
    hooks = settings.get("hooks")
    merged_hooks = dict(hooks) if isinstance(hooks, Mapping) else {}
    for registration in missing:
        entries = merged_hooks.get(registration.event)
        existing = entries if isinstance(entries, list) else []
        merged_hooks[registration.event] = [*existing, registration.settings_entry()]
    merged["hooks"] = merged_hooks
    return merged


def _settings_text(settings: Mapping[str, Any]) -> str:
    return json.dumps(settings, indent=2) + "\n"


def _load_settings(path: Path) -> dict[str, Any] | None:
    """Read and parse the settings file; `None` when absent, `InstallError` when unmergeable."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise InstallError(f"cannot read {path}: {error}") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InstallError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(data, dict):
        raise InstallError(f"{path} must be a JSON object with a top-level 'hooks' key")
    return data


def _atomic_write(path: Path, text: str, *, mode: int) -> None:
    """Write `text` to `path` via a temp file in the same directory + `os.replace` (NFRC1-A)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _captured_output(stdout: str, stderr: str) -> str:
    parts = []
    if stdout.strip():
        parts.append(f"stdout: {stdout.strip()}")
    if stderr.strip():
        parts.append(f"stderr: {stderr.strip()}")
    return "; ".join(parts) if parts else "no output"


def _verify_hook(binary: str) -> None:
    """Run `binary hook` with empty stdin and require exit 0 (UC3-B); failures raise loudly."""
    try:
        result = subprocess.run(
            [binary, "hook"],
            input="",
            capture_output=True,
            text=True,
            errors="replace",
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InstallError(f"`{binary} hook` failed to run: {error}") from error
    if result.returncode != 0:
        detail = _captured_output(result.stdout, result.stderr)
        raise InstallError(f"`{binary} hook` exited {result.returncode}: {detail}")


def _render_viz_command(viz_dir: str) -> str:
    """Substitute the viz-dir into the imported template (UEC2-A); the file is the only record."""
    return VIZ_COMMAND_TEMPLATE.replace(VIZ_DIR_PLACEHOLDER, viz_dir)


class Installer:
    """Application service at the interactive boundary; may raise on a terminal failure (D8-B)."""

    def run(self, target_repo: Path, viz_dir: Path | None, force: bool) -> InstallSummary:
        binary = shutil.which("claude-workflow-viz")
        if binary is None:
            raise InstallError("claude-workflow-viz is not on PATH; install it first")
        _verify_hook(binary)

        resolved_viz_dir = str(viz_dir) if viz_dir is not None else str(DEFAULT_VIZ_DIR)
        settings_path = target_repo / CLAUDE_DIR / SETTINGS_FILE_NAME
        settings = _load_settings(settings_path)
        existing = settings if settings is not None else {}
        missing = _missing_registrations(existing)

        # Missing `.claude` dirs are created silently (UC5-B), never a failure.
        (target_repo / COMMANDS_DIR).mkdir(parents=True, exist_ok=True)

        if missing:
            _atomic_write(
                settings_path, _settings_text(_merge(existing, missing)), mode=_SETTINGS_MODE
            )

        outcome = self._deploy_command(target_repo, resolved_viz_dir, force)
        return InstallSummary(
            binary_path=binary,
            hooks_added=tuple(registration.event for registration in missing),
            hooks_present=len(FIVE_REGISTRATIONS) - len(missing),
            command_outcome=outcome,
            viz_dir=resolved_viz_dir,
        )

    def _deploy_command(self, target_repo: Path, viz_dir: str, force: bool) -> CommandOutcome:
        command_path = target_repo / COMMANDS_DIR / COMMAND_FILE_NAME
        if command_path.exists():
            if not force:
                return CommandOutcome.SKIPPED
            _atomic_write(command_path, _render_viz_command(viz_dir), mode=_COMMAND_MODE)
            return CommandOutcome.FORCED
        _atomic_write(command_path, _render_viz_command(viz_dir), mode=_COMMAND_MODE)
        return CommandOutcome.CREATED


__all__ = [
    "InstallError",
    "Installer",
    "InstallSummary",
    "HookRegistration",
    "CommandOutcome",
    "FIVE_REGISTRATIONS",
    "HOOK_COMMAND",
    "DEFAULT_VIZ_DIR",
]
