"""Turn a Claude Code hook payload into a normalised `Event`.

Plain subagents carry no documented step label, so their identity comes from `step_key_for`.
Workflow agents (`agent_type` is `workflow-subagent`) are identified differently: the label and
phase are in `agent-<agent_id>.meta.json` in the workflow run directory
(`<session>/subagents/workflows/<run id>/`). A SubagentStop carries `agent_transcript_path`, whose
parent is that directory; a SubagentStart carries only `agent_id` and the parent `transcript_path`,
so the directory is found under `<transcript_path without .jsonl>/subagents/workflows/`. Payload
paths are relative to the payload `cwd`. The `description` in meta.json is the step key and is
parsed as `<slice>/<stage>:r<round>`; a missing or malformed meta.json degrades to
`agent-<agent_id>` and never raises; an agent_id with no alphanumeric character degrades to
`FALLBACK_STEP_KEY` instead. A round of more than 9 digits is not parsed: the label stays the step
key with no slice, stage or round, as for any non-matching label. `agent_type` is never used as
workflow identity. A Workflow PostToolUse emits `run_start` only when `tool_response.status` is
`async_launched`; any other status emits nothing.

Optional fields are read defensively (a missing or wrong-typed field degrades to an empty
summary or an `unknown` status). `session_id` and `hook_event_name` are required and a payload
without them (or with a whitespace-only value) returns an `EventError` instead of an event.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from claude_workflow_viz.workflow.events import (
    Event,
    EventError,
    EventErrorCode,
    EventKind,
    EventStatus,
)

WORKFLOW_STEP_KEY = "workflow"
FALLBACK_STEP_KEY = "agent"
WORKFLOW_AGENT_TYPE = "workflow-subagent"
META_MAXIMUM_BYTES = 64 * 1024

_WORKFLOWS_PATH = ("subagents", "workflows")
_AGENT_ID = re.compile(r"[A-Za-z0-9]+")
_HAS_ALPHANUMERIC = re.compile(r"[A-Za-z0-9]")
_ROUND_MAXIMUM_DIGITS = 9
_STEP_LABEL = re.compile(r"(?P<slice>[^/]+)/(?P<stage>[^:]+):r(?P<round>\d+)")
JOURNAL_NAME = "journal.jsonl"
JOURNAL_MAXIMUM_BYTES = 1024 * 1024

_TRANSCRIPT_NAME = re.compile(r"agent-(?P<label>.+)-(?P<identifier>[^-]+)\.jsonl")

_RESPONSE_STATUSES = {
    "completed": EventStatus.PASS,
    "failed": EventStatus.FAIL,
    "error": EventStatus.FAIL,
}
_MESSAGE_STATUSES = {"pass": EventStatus.PASS, "fail": EventStatus.FAIL}


def normalise(payload: Mapping[str, Any], now: Callable[[], float]) -> Event | None | EventError:
    """Return the event for a hook payload, None when the payload is not one we track, or an
    `EventError` when the payload is malformed."""
    if not isinstance(payload, Mapping):
        return EventError(EventErrorCode.NOT_MAPPING, "hook payload must be a mapping")
    for field in ("session_id", "hook_event_name"):
        if field not in payload:
            return EventError(EventErrorCode.MISSING_FIELD, f"missing field: {field}")
    session_id = _text(payload.get("session_id"))
    hook_event_name = _text(payload.get("hook_event_name"))
    if not session_id.strip():
        return EventError(EventErrorCode.EMPTY, "session_id must be a non-empty string")
    if not hook_event_name.strip():
        return EventError(EventErrorCode.EMPTY, "hook_event_name must be a non-empty string")

    kind, status, summary = _classify(hook_event_name, payload)
    if kind is None:
        return None
    data: dict[str, Any] = {
        "session_id": session_id,
        "ts": now(),
        "kind": kind,
        "step_key": step_key_for(payload),
        "status": status,
        "summary": summary,
    }
    if hook_event_name in ("SubagentStart", "SubagentStop"):
        data["agent_id"] = _text(payload.get("agent_id"))
        workflow = _workflow_identity(payload, hook_event_name)
        if workflow is not None:
            data.update(workflow.fields(_text(payload.get("agent_id"))))
    if payload.get("tool_name") == "Workflow" and hook_event_name == "PostToolUse":
        data["run_id"] = _text(_mapping(payload.get("tool_response")).get("runId"))
    if _is_workflow_stop(hook_event_name, payload):
        data["result"] = _journal_result(payload, _text(payload.get("agent_id")))
    event = Event.from_dict(data)
    if isinstance(event, EventError):
        return event
    return event


def step_key_for(payload: Mapping[str, Any]) -> str:
    """Identify the step a payload belongs to.

    Order: label from the `agent-<label>-<id>.jsonl` transcript basename, `agent_type`,
    `tool_input.description`, `tool_input.subagent_type`, then a fixed fallback. Workflow
    events use one fixed run-level key.
    """
    if payload.get("tool_name") == "Workflow":
        return WORKFLOW_STEP_KEY
    tool_input = _mapping(payload.get("tool_input"))
    candidates = (
        _transcript_label(payload.get("agent_transcript_path")),
        _agent_type_identity(payload),
        _text(tool_input.get("description")),
        _text(tool_input.get("subagent_type")),
    )
    return next((candidate for candidate in candidates if candidate), FALLBACK_STEP_KEY)


def _agent_type_identity(payload: Mapping[str, Any]) -> str:
    agent_type = _text(payload.get("agent_type"))
    return "" if agent_type == WORKFLOW_AGENT_TYPE else agent_type


@dataclass(frozen=True)
class _WorkflowIdentity:
    run_id: str
    meta: Mapping[str, Any] | None

    def fields(self, agent_id: str) -> dict[str, Any]:
        label = _text(self.meta.get("description")) if self.meta is not None else ""
        phase = _text(self.meta.get("workflowPhase")) if self.meta is not None else ""
        if not label:
            step_key = (
                f"agent-{agent_id}" if _HAS_ALPHANUMERIC.search(agent_id) else FALLBACK_STEP_KEY
            )
            return {"step_key": step_key, "run_id": self.run_id}
        fields: dict[str, Any] = {"step_key": label, "run_id": self.run_id, "phase": phase}
        match = _STEP_LABEL.fullmatch(label)
        if match and len(match["round"]) <= _ROUND_MAXIMUM_DIGITS:
            fields |= {
                "slice": match["slice"],
                "stage": match["stage"],
                "round": int(match["round"]),
            }
        return fields


def _workflow_identity(
    payload: Mapping[str, Any], hook_event_name: str
) -> _WorkflowIdentity | None:
    """Return the workflow identity of a subagent event, or None for a plain subagent."""
    agent_id = _text(payload.get("agent_id"))
    safe_id = agent_id if _AGENT_ID.fullmatch(agent_id) else ""
    cwd = Path(_text(payload.get("cwd")))
    is_workflow_type = _text(payload.get("agent_type")) == WORKFLOW_AGENT_TYPE

    run_directory: Path | None = None
    if hook_event_name == "SubagentStop":
        transcript = _text(payload.get("agent_transcript_path"))
        if _under_workflows(transcript):
            run_directory = (cwd / transcript).parent
        elif not is_workflow_type:
            return None
    elif safe_id:
        run_directory = _find_run_directory(cwd, _text(payload.get("transcript_path")), safe_id)

    if run_directory is None and not is_workflow_type:
        return None
    if run_directory is None:
        return _WorkflowIdentity(run_id="", meta=None)
    meta = _read_meta(run_directory / f"agent-{safe_id}.meta.json") if safe_id else None
    return _WorkflowIdentity(run_id=run_directory.name, meta=meta)


def _under_workflows(path: str) -> bool:
    parts = re.split(r"[\\/]", path)
    return any(parts[i : i + 2] == list(_WORKFLOWS_PATH) for i in range(len(parts) - 1))


def _find_run_directory(cwd: Path, transcript_path: str, agent_id: str) -> Path | None:
    if not transcript_path:
        return None
    session_directory = cwd / transcript_path.removesuffix(".jsonl")
    workflows = session_directory.joinpath(*_WORKFLOWS_PATH)
    try:
        candidates = sorted(entry for entry in workflows.iterdir() if entry.is_dir())
    except OSError:
        return None
    return next(
        (entry for entry in candidates if (entry / f"agent-{agent_id}.meta.json").is_file()),
        None,
    )


def _read_meta(path: Path) -> Mapping[str, Any] | None:
    try:
        with path.open("rb") as handle:
            raw = handle.read(META_MAXIMUM_BYTES + 1)
        if len(raw) > META_MAXIMUM_BYTES:
            return None
        parsed = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _classify(
    hook_event_name: str, payload: Mapping[str, Any]
) -> tuple[EventKind | None, EventStatus, str]:
    if hook_event_name == "SubagentStart":
        return EventKind.STEP_START, EventStatus.RUNNING, ""
    if _is_workflow_stop(hook_event_name, payload):
        # The return text of a workflow agent is plain text: carry it verbatim, never parse it.
        return (
            EventKind.STEP_STOP,
            EventStatus.UNKNOWN,
            _text(payload.get("last_assistant_message")),
        )
    if hook_event_name == "SubagentStop":
        status, summary = _read_last_message(payload.get("last_assistant_message"))
        return EventKind.STEP_STOP, status, summary

    tool_name = payload.get("tool_name")
    if tool_name not in ("Agent", "Workflow"):
        return None, EventStatus.UNKNOWN, ""
    is_workflow = tool_name == "Workflow"
    if is_workflow and hook_event_name == "PreToolUse":
        return EventKind.RUN_START, EventStatus.RUNNING, ""
    if is_workflow and hook_event_name == "PostToolUse":
        # PostToolUse on Workflow fires at launch, never at completion. Only an
        # `async_launched` response means the run started; a failed launch emits nothing.
        response = _mapping(payload.get("tool_response"))
        if _text(response.get("status")) != "async_launched":
            return None, EventStatus.UNKNOWN, ""
        return EventKind.RUN_START, EventStatus.RUNNING, ""
    if hook_event_name == "PreToolUse":
        return EventKind.STEP_START, EventStatus.RUNNING, ""
    if hook_event_name == "PostToolUse":
        response = _mapping(payload.get("tool_response"))
        status = _RESPONSE_STATUSES.get(_text(response.get("status")), EventStatus.UNKNOWN)
        return EventKind.STEP_STOP, status, _content_text(response.get("content"))
    return None, EventStatus.UNKNOWN, ""


def _is_workflow_stop(hook_event_name: str, payload: Mapping[str, Any]) -> bool:
    return (
        hook_event_name == "SubagentStop"
        and _text(payload.get("agent_type")) == WORKFLOW_AGENT_TYPE
    )


def _journal_result(payload: Mapping[str, Any], agent_id: str) -> Any:
    """Return the structured result the run journal recorded for `agent_id`, else None.

    The journal is read here, not in the server: the hook process has the filesystem path, the
    server only receives events. The async Stop hook may run before the journal line is written;
    the result is then None. The read is capped at `JOURNAL_MAXIMUM_BYTES` because a run
    directory can grow large. Never raises.
    """
    transcript = _text(payload.get("agent_transcript_path"))
    if not agent_id or not transcript:
        return None
    try:
        directory = Path(transcript).parent
        if not directory.is_absolute():
            directory = Path(_text(payload.get("cwd"))) / directory
        with (directory / JOURNAL_NAME).open("rb") as journal:
            content = journal.read(JOURNAL_MAXIMUM_BYTES)
    except (OSError, ValueError):
        return None
    result = None
    for line in content.decode(errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if (
            isinstance(entry, dict)
            and entry.get("type") == "result"
            and entry.get("agentId") == agent_id
        ):
            result = entry.get("result")
    return result if _is_serialisable(result) else None


def _is_serialisable(value: Any) -> bool:
    """Whether `value` is strict JSON data, as `Event.from_dict` requires of a result."""
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return False
    return True


def _transcript_label(path: Any) -> str:
    if not isinstance(path, str):
        return ""
    match = _TRANSCRIPT_NAME.fullmatch(re.split(r"[\\/]", path)[-1])
    return unquote(match["label"]) if match else ""


def _read_last_message(message: Any) -> tuple[EventStatus, str]:
    """Return (status, summary) from a final assistant message.

    A message that is a JSON object may carry `status` ("pass"/"fail") and `summary`; anything
    else is used verbatim as the summary with status unknown.
    """
    if not isinstance(message, str):
        return EventStatus.UNKNOWN, ""
    try:
        parsed = json.loads(message)
    except (ValueError, RecursionError):
        return EventStatus.UNKNOWN, message
    if not isinstance(parsed, dict):
        return EventStatus.UNKNOWN, message
    status = _MESSAGE_STATUSES.get(_text(parsed.get("status")).lower(), EventStatus.UNKNOWN)
    return status, _text(parsed.get("summary")) or message


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return "\n".join(texts)
    return ""


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
