import json
import shutil
from pathlib import Path

import pytest

from claude_workflow_viz.workflow.events import (
    Event,
    EventError,
    EventErrorCode,
    EventKind,
    EventStatus,
)
from claude_workflow_viz.workflow.hook_adapter import FALLBACK_STEP_KEY, normalise, step_key_for

NOW = 1700000000.5


def _clock() -> float:
    return NOW


def _common(hook_event_name: str) -> dict[str, object]:
    return {
        "session_id": "session-1",
        "transcript_path": "/home/user/.claude/projects/p/session-1.jsonl",
        "cwd": "/home/user/project",
        "hook_event_name": hook_event_name,
    }


def _subagent_stop(**overrides: object) -> dict[str, object]:
    payload = _common("SubagentStop") | {
        "agent_id": "a1b2c3",
        "agent_type": "developer",
        "agent_transcript_path": "/home/user/.claude/projects/p/subagents/agent-a1b2c3.jsonl",
        "last_assistant_message": "Implemented the change. All tests pass.",
        "stop_hook_active": False,
    }
    return payload | overrides


def _agent_pre(**tool_input: object) -> dict[str, object]:
    return _common("PreToolUse") | {
        "tool_name": "Agent",
        "tool_input": {
            "prompt": "Implement slice 1",
            "description": "slice-1 developer",
            "subagent_type": "general-purpose",
            "model": "sonnet",
        }
        | tool_input,
    }


def _agent_post(**tool_response: object) -> dict[str, object]:
    return _common("PostToolUse") | {
        "tool_name": "Agent",
        "tool_input": {"description": "slice-1 developer", "subagent_type": "general-purpose"},
        "tool_response": {
            "status": "completed",
            "agentId": "a1b2c3",
            "content": "Slice done.",
            "totalDurationMs": 4200,
            "totalTokens": 1234,
        }
        | tool_response,
    }


# Acceptance criterion 1: each documented event normalises to the documented kind and status.


def test_subagent_start() -> None:
    payload = _common("SubagentStart") | {"agent_id": "a1b2c3", "agent_type": "developer"}

    assert normalise(payload, _clock) == Event(
        "session-1", NOW, EventKind.STEP_START, "developer", EventStatus.RUNNING, "", "a1b2c3"
    )


def test_subagent_stop() -> None:
    event = normalise(_subagent_stop(), _clock)

    assert event == Event(
        "session-1",
        NOW,
        EventKind.STEP_STOP,
        "developer",
        EventStatus.UNKNOWN,
        "Implemented the change. All tests pass.",
        "a1b2c3",
    )


def test_pre_tool_use_agent() -> None:
    assert normalise(_agent_pre(), _clock) == Event(
        "session-1", NOW, EventKind.STEP_START, "slice-1 developer", EventStatus.RUNNING, ""
    )


def test_post_tool_use_agent() -> None:
    assert normalise(_agent_post(), _clock) == Event(
        "session-1", NOW, EventKind.STEP_STOP, "slice-1 developer", EventStatus.PASS, "Slice done."
    )


def test_pre_tool_use_workflow() -> None:
    payload = _common("PreToolUse") | {"tool_name": "Workflow", "tool_input": {"name": "implement"}}

    event = normalise(payload, _clock)

    assert event is not None
    assert (event.kind, event.status, event.step_key) == (
        EventKind.RUN_START,
        EventStatus.RUNNING,
        step_key_for(payload),
    )


def test_pre_tool_use_workflow_has_no_run_id() -> None:
    payload = _common("PreToolUse") | {"tool_name": "Workflow", "tool_input": {"name": "implement"}}

    event = normalise(payload, _clock)

    assert event is not None
    assert event.run_id == ""


def test_post_tool_use_workflow_launch_starts_the_run_with_its_id() -> None:
    payload = _common("PostToolUse") | {
        "tool_name": "Workflow",
        "tool_input": {"name": "implement"},
        "tool_response": {
            "status": "async_launched",
            "runId": "wf_5bafa1d7-817",
            "transcriptDir": "/x/subagents/workflows/wf_5bafa1d7-817",
            "workflowName": "implement",
        },
    }

    event = normalise(payload, _clock)

    assert event is not None
    assert (event.kind, event.status, event.run_id, event.step_key) == (
        EventKind.RUN_START,
        EventStatus.RUNNING,
        "wf_5bafa1d7-817",
        step_key_for(payload),
    )


@pytest.mark.parametrize("response_status", ["completed", "failed", "error", None])
def test_post_tool_use_workflow_without_async_launched_emits_no_run_start(
    response_status: str | None,
) -> None:
    response = {"content": "Run finished."}
    if response_status is not None:
        response["status"] = response_status
    payload = _common("PostToolUse") | {"tool_name": "Workflow", "tool_response": response}

    assert normalise(payload, _clock) is None


@pytest.mark.parametrize(
    "tool_response",
    ["text", 7, ["x"], None, {"runId": 7}, {"runId": ""}, {"runId": ["wf_1"]}],
)
def test_post_tool_use_workflow_with_malformed_response_leaves_run_id_empty(
    tool_response: object,
) -> None:
    if isinstance(tool_response, dict):
        tool_response = {"status": "async_launched"} | tool_response
    payload = _common("PostToolUse") | {"tool_name": "Workflow", "tool_response": tool_response}

    event = normalise(payload, _clock)
    if not isinstance(tool_response, dict):
        assert event is None
        return

    assert event is not None
    assert (event.kind, event.run_id) == (EventKind.RUN_START, "")


def test_workflow_events_share_one_run_level_key_regardless_of_other_fields() -> None:
    start = _common("PreToolUse") | {"tool_name": "Workflow", "tool_input": {"description": "x"}}
    stop = _common("PostToolUse") | {"tool_name": "Workflow", "agent_type": "y"}

    assert step_key_for(start) == step_key_for(stop)


@pytest.mark.parametrize(
    ("response_status", "expected"),
    [
        ("completed", EventStatus.PASS),
        ("failed", EventStatus.FAIL),
        ("error", EventStatus.FAIL),
        ("something-new", EventStatus.UNKNOWN),
        (None, EventStatus.UNKNOWN),
        (7, EventStatus.UNKNOWN),
    ],
)
def test_post_tool_use_agent_status_comes_from_tool_response(
    response_status: object, expected: EventStatus
) -> None:
    event = normalise(_agent_post(status=response_status), _clock)

    assert event is not None
    assert event.status is expected


@pytest.mark.parametrize(
    ("message", "expected_status", "expected_summary"),
    [
        ('{"status": "pass", "summary": "All green"}', EventStatus.PASS, "All green"),
        ('{"status": "fail", "summary": "2 tests red"}', EventStatus.FAIL, "2 tests red"),
        ('{"status": "pass"}', EventStatus.PASS, '{"status": "pass"}'),
        ('{"status": "maybe", "summary": "hm"}', EventStatus.UNKNOWN, "hm"),
        ("[1, 2, 3]", EventStatus.UNKNOWN, "[1, 2, 3]"),
        ("{not json", EventStatus.UNKNOWN, "{not json"),
    ],
)
def test_subagent_stop_parses_last_assistant_message_defensively(
    message: str, expected_status: EventStatus, expected_summary: str
) -> None:
    event = normalise(_subagent_stop(last_assistant_message=message), _clock)

    assert event is not None
    assert (event.status, event.summary) == (expected_status, expected_summary)


# Acceptance criterion 2: step identity fallback order.


def test_key_prefers_transcript_basename_label() -> None:
    payload = _subagent_stop(
        agent_transcript_path="/x/subagents/agent-slice-1-develop-a1b2c3.jsonl",
        agent_type="developer",
    )

    assert step_key_for(payload) == "slice-1-develop"


def test_key_label_with_encoded_slash_is_decoded() -> None:
    payload = _subagent_stop(agent_transcript_path="/x/agent-slice-1%2Fdevelop-a1b2c3.jsonl")

    assert step_key_for(payload) == "slice-1/develop"


def test_key_falls_back_to_agent_type_when_basename_does_not_match() -> None:
    for name in ("agent-a1b2c3.jsonl", "session-1.jsonl", "agent--a1b2c3.jsonl", "agent-x-y.txt"):
        payload = _subagent_stop(agent_transcript_path=f"/x/{name}", agent_type="developer")

        assert step_key_for(payload) == "developer", name


def test_key_falls_back_to_agent_type_without_transcript_path() -> None:
    payload = _common("SubagentStart") | {"agent_id": "a", "agent_type": "reviewer"}

    assert step_key_for(payload) == "reviewer"


def test_key_falls_back_to_description() -> None:
    payload = _agent_pre()

    assert step_key_for(payload) == "slice-1 developer"


def test_key_falls_back_to_subagent_type() -> None:
    payload = _agent_pre(description="")

    assert step_key_for(payload) == "general-purpose"


def test_key_uses_fixed_fallback_when_nothing_identifies_the_step() -> None:
    payload = _common("PreToolUse") | {"tool_name": "Agent", "tool_input": {"prompt": "p"}}

    assert step_key_for(payload) == "agent"
    assert step_key_for(_common("SubagentStart")) == "agent"


def test_key_ignores_wrong_typed_identity_fields() -> None:
    payload = _subagent_stop(agent_transcript_path=5, agent_type=["developer"])
    payload["tool_input"] = {"description": 3, "subagent_type": "general-purpose"}

    assert step_key_for(payload) == "general-purpose"


# Acceptance criterion 3: anything else is ignored.


@pytest.mark.parametrize(
    "hook_event_name", ["UserPromptSubmit", "Stop", "Notification", "SessionStart"]
)
def test_unrelated_hook_events_return_none(hook_event_name: str) -> None:
    assert normalise(_common(hook_event_name), _clock) is None


@pytest.mark.parametrize("hook_event_name", ["PreToolUse", "PostToolUse"])
@pytest.mark.parametrize("tool_name", ["Bash", "Read", "agent", None, 3])
def test_other_tools_return_none(hook_event_name: str, tool_name: object) -> None:
    payload = _common(hook_event_name) | {"tool_name": tool_name, "tool_input": {}}

    assert normalise(payload, _clock) is None


def test_tool_event_without_tool_name_returns_none() -> None:
    assert normalise(_common("PreToolUse"), _clock) is None


# Acceptance criterion 4: tolerant of optional fields, strict about required ones.


def test_subagent_stop_without_last_assistant_message() -> None:
    payload = _subagent_stop()
    del payload["last_assistant_message"]

    event = normalise(payload, _clock)

    assert event is not None
    assert (event.status, event.summary) == (EventStatus.UNKNOWN, "")


@pytest.mark.parametrize("message", [None, 5, ["a"], {"status": "pass"}])
def test_subagent_stop_with_wrong_typed_message(message: object) -> None:
    event = normalise(_subagent_stop(last_assistant_message=message), _clock)

    assert event is not None
    assert (event.status, event.summary) == (EventStatus.UNKNOWN, "")


def test_post_tool_use_agent_without_tool_response() -> None:
    payload = _agent_post()
    del payload["tool_response"]

    event = normalise(payload, _clock)

    assert event is not None
    assert (event.kind, event.status, event.summary) == (
        EventKind.STEP_STOP,
        EventStatus.UNKNOWN,
        "",
    )


@pytest.mark.parametrize("response", [None, "text", ["a"], 5])
def test_post_tool_use_agent_with_wrong_typed_tool_response(response: object) -> None:
    payload = _agent_post()
    payload["tool_response"] = response

    event = normalise(payload, _clock)

    assert event is not None
    assert (event.status, event.summary) == (EventStatus.UNKNOWN, "")


def test_non_string_content_never_raises() -> None:
    for content in (None, 5, {"a": 1}, [1, None], [{"type": "image"}]):
        event = normalise(_agent_post(content=content), _clock)

        assert event is not None
        assert event.summary == ""


def test_content_blocks_with_text_are_joined_into_the_summary() -> None:
    content = [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]

    event = normalise(_agent_post(content=content), _clock)

    assert event is not None
    assert event.summary == "first\nsecond"


def test_wrong_typed_tool_input_never_raises() -> None:
    payload = _common("PreToolUse") | {"tool_name": "Agent", "tool_input": "oops"}

    event = normalise(payload, _clock)

    assert event is not None
    assert event.step_key == "agent"


def test_long_summary_is_truncated_not_rejected() -> None:
    event = normalise(_agent_post(content="x" * 10_000), _clock)

    assert event is not None
    assert len(event.summary) == 500


@pytest.mark.parametrize("missing", ["session_id", "hook_event_name"])
def test_missing_required_common_field_returns_error(missing: str) -> None:
    payload = _common("SubagentStart")
    del payload[missing]

    result = normalise(payload, _clock)

    assert isinstance(result, EventError)
    assert result.code == EventErrorCode.MISSING_FIELD
    assert missing in result.message


@pytest.mark.parametrize("missing", ["session_id", "hook_event_name"])
def test_missing_required_field_returns_error_even_for_unrelated_events(missing: str) -> None:
    payload = _common("Stop")
    del payload[missing]

    result = normalise(payload, _clock)

    assert isinstance(result, EventError)
    assert result.code == EventErrorCode.MISSING_FIELD
    assert missing in result.message


@pytest.mark.parametrize("field", ["session_id", "hook_event_name"])
@pytest.mark.parametrize("value", [None, 5, "", " ", "\t\n  "])
def test_wrong_typed_or_empty_required_field_returns_error(field: str, value: object) -> None:
    payload = _common("SubagentStart") | {field: value}

    result = normalise(payload, _clock)

    assert isinstance(result, EventError)
    assert result.code in (EventErrorCode.NOT_STRING, EventErrorCode.EMPTY)
    assert field in result.message


def test_subagent_stop_with_deeply_nested_message_does_not_raise() -> None:
    message = "[" * 100000

    event = normalise(_subagent_stop(last_assistant_message=message), _clock)

    assert event is not None
    assert event.status == EventStatus.UNKNOWN


# --- workflow agent step identity (agent_id and the run directory meta.json) ---

FIXTURES = Path(__file__).parent / "fixtures"
RUN_DIRECTORY = "session/subagents/workflows/wf_ec22ed24-66b"
EXPECTED_STEPS = {
    "aaf76f0408301cfd4": ("s1/develop:r1", "develop", 1),
    "a05394394b07d3387": ("s1/review:r1", "review", 1),
    "a3f0816c669459462": ("s1/code-review:r1", "code-review", 1),
    "a917b3019e249e3e6": ("s1/develop:r2", "develop", 2),
}


@pytest.fixture
def workflow_tree(tmp_path):
    shutil.copytree(FIXTURES / "tree", tmp_path, dirs_exist_ok=True)
    return tmp_path


def _probe_payloads(cwd: Path) -> list[dict[str, object]]:
    lines = (FIXTURES / "probe_payloads.jsonl").read_text().splitlines()
    return [json.loads(line) | {"cwd": str(cwd)} for line in lines]


def _workflow_payload(cwd: Path, agent_id: str, event: str, **overrides: object):
    payload: dict[str, object] = {
        "session_id": "probe-session",
        "transcript_path": "session.jsonl",
        "cwd": str(cwd),
        "agent_id": agent_id,
        "agent_type": "workflow-subagent",
        "hook_event_name": event,
    }
    if event == "SubagentStop":
        payload["agent_transcript_path"] = f"{RUN_DIRECTORY}/agent-{agent_id}.jsonl"
    return payload | overrides


def _write_meta(cwd: Path, agent_id: str, content: str) -> None:
    (cwd / RUN_DIRECTORY / f"agent-{agent_id}.meta.json").write_text(content)


def test_replayed_probe_events_carry_label_run_phase_and_parsed_fields(workflow_tree):
    events = [
        normalise(payload, _clock)
        for payload in _probe_payloads(workflow_tree)
        if "wf_ec22ed24-66b" in str(payload.get("agent_transcript_path", ""))
        or payload["hook_event_name"] == "SubagentStart"
    ]
    probe_two = [e for e in events if e and e.agent_id in EXPECTED_STEPS]
    assert len(probe_two) == 8
    for event in probe_two:
        step_key, stage, round_number = EXPECTED_STEPS[event.agent_id]
        assert (event.step_key, event.run_id, event.phase) == (
            step_key,
            "wf_ec22ed24-66b",
            "Probe",
        )
        assert (event.slice, event.stage, event.round) == ("s1", stage, round_number)


def test_start_and_stop_of_one_agent_share_step_key_and_agent_id(workflow_tree):
    for agent_id in EXPECTED_STEPS:
        start = normalise(_workflow_payload(workflow_tree, agent_id, "SubagentStart"), _clock)
        stop = normalise(_workflow_payload(workflow_tree, agent_id, "SubagentStop"), _clock)
        assert start.step_key == stop.step_key == EXPECTED_STEPS[agent_id][0]
        assert start.agent_id == stop.agent_id == agent_id


def test_workflow_events_never_use_the_agent_type_as_step_key(workflow_tree):
    for payload in _probe_payloads(workflow_tree):
        event = normalise(payload, _clock)
        assert event.step_key != "workflow-subagent"
        assert event.agent_id == payload["agent_id"]


def test_label_outside_the_slice_stage_round_form_is_used_verbatim(workflow_tree):
    _write_meta(
        workflow_tree,
        "aaf76f0408301cfd4",
        json.dumps({"description": "probe-alpha", "workflowPhase": "Probe"}),
    )
    for event_name in ("SubagentStart", "SubagentStop"):
        event = normalise(_workflow_payload(workflow_tree, "aaf76f0408301cfd4", event_name), _clock)
        assert event.step_key == "probe-alpha"
        assert (event.slice, event.stage, event.round) == ("", "", None)
        assert (event.run_id, event.phase) == ("wf_ec22ed24-66b", "Probe")


@pytest.mark.parametrize(
    "content",
    [None, "", "{not json", "[1, 2]", '"text"', '{"description": 7}', '{"description": ""}'],
    ids=["missing", "empty", "invalid", "array", "string", "non-string", "blank"],
)
@pytest.mark.parametrize("event_name", ["SubagentStart", "SubagentStop"])
def test_unusable_meta_falls_back_to_agent_id_key(workflow_tree, content, event_name):
    meta = workflow_tree / RUN_DIRECTORY / "agent-aaf76f0408301cfd4.meta.json"
    if content is None:
        meta.unlink()
    else:
        meta.write_text(content)
    event = normalise(_workflow_payload(workflow_tree, "aaf76f0408301cfd4", event_name), _clock)
    assert event.step_key == "agent-aaf76f0408301cfd4"
    assert event.agent_id == "aaf76f0408301cfd4"


def test_unreadable_meta_falls_back_to_agent_id_key(workflow_tree):
    meta = workflow_tree / RUN_DIRECTORY / "agent-aaf76f0408301cfd4.meta.json"
    meta.unlink()
    meta.mkdir()
    event = normalise(_workflow_payload(workflow_tree, "aaf76f0408301cfd4", "SubagentStop"), _clock)
    assert event.step_key == "agent-aaf76f0408301cfd4"


def test_oversized_meta_falls_back_to_agent_id_key(workflow_tree):
    padding = "x" * 200_000
    _write_meta(
        workflow_tree,
        "aaf76f0408301cfd4",
        json.dumps({"description": "s1/develop:r1", "padding": padding}),
    )
    event = normalise(_workflow_payload(workflow_tree, "aaf76f0408301cfd4", "SubagentStop"), _clock)
    assert event.step_key == "agent-aaf76f0408301cfd4"


@pytest.mark.parametrize("agent_id", ["../x", "a/b", "a\\b", "..", "", "a.b", "a b", "*", "a*"])
def test_agent_id_that_could_escape_the_directory_is_not_used_in_a_path(workflow_tree, agent_id):
    (workflow_tree / "x.meta.json").write_text(json.dumps({"description": "s1/evil:r1"}))
    (workflow_tree / "session/subagents/workflows/agent-.meta.json").write_text(
        json.dumps({"description": "s1/evil:r1"})
    )
    start = normalise(_workflow_payload(workflow_tree, agent_id, "SubagentStart"), _clock)
    stop = normalise(
        _workflow_payload(
            workflow_tree,
            agent_id,
            "SubagentStop",
            agent_transcript_path=f"{RUN_DIRECTORY}/agent-{agent_id}.jsonl",
        ),
        _clock,
    )
    for event in (start, stop):
        assert "evil" not in event.step_key
        assert event.step_key != "workflow-subagent"


def test_workflow_stop_without_a_cwd_still_normalises(workflow_tree):
    payload = _workflow_payload(workflow_tree, "aaf76f0408301cfd4", "SubagentStop")
    del payload["cwd"]
    event = normalise(payload, _clock)
    assert event.step_key == "agent-aaf76f0408301cfd4"


def test_start_without_meta_and_with_other_agent_type_keeps_existing_order(workflow_tree):
    payload = _workflow_payload(workflow_tree, "zzz", "SubagentStart", agent_type="planner")
    assert normalise(payload, _clock).step_key == "planner"


# Workflow SubagentStop: the plain return text is the summary and the journal carries the
# structured result.


def _write_journal(run_directory: Path, *lines: str) -> None:
    run_directory.mkdir(parents=True, exist_ok=True)
    (run_directory / "journal.jsonl").write_text("\n".join(lines) + "\n")


def _result_line(agent_id: str, result: object) -> str:
    return json.dumps({"type": "result", "key": "v2:k", "agentId": agent_id, "result": result})


def _workflow_stop(run_directory: Path, agent_id: str, **overrides: object) -> dict[str, object]:
    payload = _common("SubagentStop") | {
        "agent_id": agent_id,
        "agent_type": "workflow-subagent",
        "agent_transcript_path": str(run_directory / f"agent-{agent_id}.jsonl"),
        "stop_hook_active": False,
    }
    return payload | overrides


def test_workflow_stop_carries_plain_text_summary_and_journal_result(tmp_path: Path) -> None:
    run_directory = tmp_path / "wf_5bafa1d7-817"
    _write_journal(run_directory, _result_line("aa40e04dc34ef5608", "ALPHA"))

    event = normalise(
        _workflow_stop(run_directory, "aa40e04dc34ef5608", last_assistant_message="ALPHA"), _clock
    )

    assert event is not None
    assert (event.summary, event.result, event.agent_id) == ("ALPHA", "ALPHA", "aa40e04dc34ef5608")


def test_workflow_stop_without_message_has_empty_summary_and_object_result(
    tmp_path: Path,
) -> None:
    run_directory = tmp_path / "wf_5bafa1d7-817"
    _write_journal(
        run_directory,
        _result_line("aa40e04dc34ef5608", "ALPHA"),
        _result_line("a6ed92d3c1d664b07", {"verdict": "PASS", "note": "probe"}),
    )

    event = normalise(_workflow_stop(run_directory, "a6ed92d3c1d664b07"), _clock)

    assert event is not None
    assert event.summary == ""
    assert event.result == {"verdict": "PASS", "note": "probe"}


def test_workflow_stop_json_message_is_carried_verbatim_not_parsed(tmp_path: Path) -> None:
    event = normalise(
        _workflow_stop(tmp_path, "a1", last_assistant_message='{"status": "pass"}'), _clock
    )

    assert event is not None
    assert event.summary == '{"status": "pass"}'
    assert event.status == EventStatus.UNKNOWN


def test_workflow_stop_relative_transcript_path_resolves_against_cwd(tmp_path: Path) -> None:
    _write_journal(tmp_path / "runs" / "wf_1", _result_line("a1", "OK"))

    event = normalise(
        _workflow_stop(
            tmp_path,
            "a1",
            cwd=str(tmp_path),
            agent_transcript_path="runs/wf_1/agent-a1.jsonl",
        ),
        _clock,
    )

    assert event is not None
    assert event.result == "OK"


def test_workflow_stop_uses_the_last_matching_result_line(tmp_path: Path) -> None:
    _write_journal(tmp_path, _result_line("a1", "first"), _result_line("a1", "second"))

    event = normalise(_workflow_stop(tmp_path, "a1"), _clock)

    assert event is not None
    assert event.result == "second"


def test_workflow_stop_skips_malformed_lines_and_still_finds_a_later_match(
    tmp_path: Path,
) -> None:
    _write_journal(tmp_path, "{not json", "[1, 2]", '{"type": "result"', _result_line("a1", "OK"))

    event = normalise(_workflow_stop(tmp_path, "a1"), _clock)

    assert event is not None
    assert event.result == "OK"


def test_workflow_stop_keeps_the_stop_event_when_the_journal_result_is_not_valid_json_data(
    tmp_path: Path,
) -> None:
    nan_line = '{"type": "result", "agentId": "a1", "result": {"x": NaN}}'
    _write_journal(tmp_path, nan_line)

    event = normalise(_workflow_stop(tmp_path, "a1", last_assistant_message="done"), _clock)

    assert event is not None
    assert event.summary == "done"
    assert event.result is None


def test_workflow_stop_keeps_the_stop_event_when_the_journal_result_is_too_deeply_nested(
    tmp_path: Path,
) -> None:
    depth = 990
    nested = "[" * depth + "]" * depth
    _write_journal(tmp_path, f'{{"type": "result", "agentId": "a1", "result": {nested}}}')

    event = normalise(_workflow_stop(tmp_path, "a1", last_assistant_message="done"), _clock)

    assert event is not None
    assert event.summary == "done"


def test_workflow_stop_result_is_none_when_journal_is_unusable(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    unreadable = tmp_path / "unreadable"
    _write_journal(unreadable, _result_line("a1", "OK"))
    (unreadable / "journal.jsonl").chmod(0)
    directory_journal = tmp_path / "directory"
    (directory_journal / "journal.jsonl").mkdir(parents=True)
    other_agent = tmp_path / "other"
    _write_journal(other_agent, _result_line("a2", "OK"), json.dumps({"type": "started"}))

    try:
        for run_directory in (missing, unreadable, directory_journal, other_agent):
            event = normalise(_workflow_stop(run_directory, "a1"), _clock)
            assert event is not None
            assert event.result is None
    finally:
        (unreadable / "journal.jsonl").chmod(0o600)


def test_workflow_stop_reads_a_bounded_amount_of_the_journal(tmp_path: Path) -> None:
    padding = json.dumps({"type": "started", "agentId": "a1", "label": "x" * 1000})
    _write_journal(tmp_path, *([padding] * 2000), _result_line("a1", "too far away"))

    event = normalise(_workflow_stop(tmp_path, "a1"), _clock)

    assert event is not None
    assert event.result is None


def test_non_workflow_stop_ignores_the_journal(tmp_path: Path) -> None:
    _write_journal(tmp_path, _result_line("a1b2c3", "ALPHA"))

    event = normalise(
        _subagent_stop(
            agent_transcript_path=str(tmp_path / "agent-a1b2c3.jsonl"),
            last_assistant_message='{"status": "pass", "summary": "done"}',
        ),
        _clock,
    )

    assert event is not None
    assert (event.status, event.summary, event.result) == (EventStatus.PASS, "done", None)


def test_recorded_probe_stops_carry_summary_and_journal_result(workflow_tree):
    stops = {
        payload["agent_id"]: normalise(payload, _clock)
        for payload in _probe_payloads(workflow_tree)
        if payload["hook_event_name"] == "SubagentStop"
    }

    alpha = stops["aa40e04dc34ef5608"]
    assert (alpha.summary, alpha.result) == ("ALPHA", "ALPHA")
    structured = stops["a6ed92d3c1d664b07"]
    assert structured.summary == ""
    assert structured.result == {"verdict": "PASS", "note": "probe"}


@pytest.mark.parametrize("digits", [10, 5000])
@pytest.mark.parametrize("event_name", ["SubagentStart", "SubagentStop"])
def test_oversized_round_keeps_the_label_and_drops_the_parsed_fields(
    workflow_tree, digits, event_name
):
    label = f"s1/develop:r{'9' * digits}"
    _write_meta(workflow_tree, "aaf76f0408301cfd4", json.dumps({"description": label}))
    event = normalise(_workflow_payload(workflow_tree, "aaf76f0408301cfd4", event_name), _clock)
    assert event.step_key == label
    assert event.run_id == "wf_ec22ed24-66b"
    assert (event.slice, event.stage, event.round) == ("", "", None)


@pytest.mark.parametrize("agent_id", ["", "../", "---"])
@pytest.mark.parametrize("event_name", ["SubagentStart", "SubagentStop"])
def test_workflow_agent_without_alphanumeric_id_uses_the_fallback_key(
    workflow_tree, agent_id, event_name
):
    event = normalise(_workflow_payload(workflow_tree, agent_id, event_name), _clock)
    assert event is not None
    assert event.step_key == FALLBACK_STEP_KEY


def test_pre_tool_use_workflow_carries_the_workflow_name() -> None:
    payload = _common("PreToolUse") | {"tool_name": "Workflow", "tool_input": {"name": "implement"}}

    event = normalise(payload, _clock)

    assert event is not None
    assert event.workflow == "implement"


def test_pre_tool_use_workflow_without_a_name_leaves_workflow_empty() -> None:
    payload = _common("PreToolUse") | {"tool_name": "Workflow", "tool_input": {}}

    event = normalise(payload, _clock)

    assert event is not None
    assert event.workflow == ""


def test_step_events_do_not_carry_a_workflow() -> None:
    start = normalise(_subagent_stop(), _clock)

    assert start is not None
    assert start.workflow == ""
    assert "workflow" not in start.to_dict()
