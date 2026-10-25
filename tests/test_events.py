import itertools
import json

import pytest

from claude_workflow_viz.workflow.events import (
    RESULT_MAXIMUM_BYTES,
    SUMMARY_MAXIMUM_LENGTH,
    Event,
    EventError,
    EventErrorCode,
    EventKind,
    EventSink,
    EventStatus,
)


def _valid_data() -> dict[str, object]:
    return {
        "session_id": "session-1",
        "ts": 1700000000.5,
        "kind": "step_start",
        "step_key": "slice-1/develop:r1",
        "status": "running",
        "summary": "developer started",
    }


def _error(data: object) -> EventError:
    error = Event.from_dict(data)  # type: ignore[arg-type]
    assert isinstance(error, EventError)
    return error


@pytest.mark.parametrize(
    ("kind", "status"), list(itertools.product(EventKind, EventStatus)), ids=str
)
def test_round_trip_for_every_kind_and_status(kind: EventKind, status: EventStatus) -> None:
    event = Event("session-1", 1700000000.25, kind, "step", status, "summary")

    assert Event.from_dict(event.to_dict()) == event


def test_to_dict_is_json_serialisable_and_round_trips_through_json() -> None:
    event = Event.from_dict(_valid_data())

    assert Event.from_dict(json.loads(json.dumps(event.to_dict()))) == event


def test_event_is_frozen() -> None:
    event = Event.from_dict(_valid_data())

    with pytest.raises(AttributeError):
        event.summary = "changed"  # type: ignore[misc]


def test_integer_timestamp_is_accepted_as_seconds() -> None:
    data = _valid_data() | {"ts": 1700000000}

    event = Event.from_dict(data)

    assert isinstance(event, Event)
    assert event.ts == 1700000000.0


def test_integer_timestamp_too_large_for_a_float_is_rejected() -> None:
    error = _error(_valid_data() | {"ts": 10**400})

    assert error.code == EventErrorCode.TIMESTAMP_TOO_LARGE
    assert "ts is too large" in error.message


@pytest.mark.parametrize("field", list(_valid_data()))
def test_missing_field_is_rejected(field: str) -> None:
    data = _valid_data()
    del data[field]

    error = _error(data)

    assert error.code == EventErrorCode.MISSING_FIELD
    assert field in error.message


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("session_id", 5, EventErrorCode.NOT_STRING),
        ("ts", "2023-11-14T22:13:20Z", EventErrorCode.BAD_TIMESTAMP),
        ("ts", True, EventErrorCode.BAD_TIMESTAMP),
        ("ts", float("nan"), EventErrorCode.NON_FINITE_TIMESTAMP),
        ("kind", 1, EventErrorCode.NOT_STRING),
        ("step_key", None, EventErrorCode.NOT_STRING),
        ("status", ["running"], EventErrorCode.NOT_STRING),
        ("summary", 3, EventErrorCode.NOT_STRING),
    ],
)
def test_wrong_typed_field_is_rejected(field: str, value: object, code: EventErrorCode) -> None:
    error = _error(_valid_data() | {field: value})

    assert error.code == code
    assert field in error.message


def test_empty_session_id_is_rejected() -> None:
    error = _error(_valid_data() | {"session_id": ""})

    assert error.code == EventErrorCode.EMPTY
    assert "session_id" in error.message


def test_unknown_kind_is_rejected() -> None:
    error = _error(_valid_data() | {"kind": "explode"})

    assert error.code == EventErrorCode.BAD_KIND
    assert "kind" in error.message


def test_unknown_status_is_rejected() -> None:
    error = _error(_valid_data() | {"status": "sideways"})

    assert error.code == EventErrorCode.BAD_STATUS
    assert "status" in error.message


def test_non_mapping_input_is_rejected() -> None:
    error = _error(["not", "a", "mapping"])

    assert error.code == EventErrorCode.NOT_MAPPING
    assert error.message == "event must be a mapping"


def test_invalid_event_is_a_typed_result_not_an_exception() -> None:
    error = _error(_valid_data() | {"session_id": ""})

    assert isinstance(error, EventError)
    assert isinstance(error.code, EventErrorCode)
    assert "session_id" in error.message


def test_summary_at_the_cap_is_kept() -> None:
    summary = "x" * SUMMARY_MAXIMUM_LENGTH

    event = Event.from_dict(_valid_data() | {"summary": summary})

    assert isinstance(event, Event)
    assert event.summary == summary


def test_summary_one_over_the_cap_is_truncated_to_the_cap() -> None:
    summary = "x" * (SUMMARY_MAXIMUM_LENGTH + 1)

    event = Event.from_dict(_valid_data() | {"summary": summary})

    assert isinstance(event, Event)
    assert event.summary == "x" * SUMMARY_MAXIMUM_LENGTH


def test_event_sink_is_a_plain_callable_that_receives_events() -> None:
    received: list[Event] = []
    sink: EventSink = received.append

    event = Event.from_dict(_valid_data())
    assert isinstance(event, Event)
    sink(event)

    assert received == [event]


def _workflow_data() -> dict[str, object]:
    return {
        **_valid_data(),
        "agent_id": "agent-7",
        "run_id": "run-3",
        "slice": "s1-event-schema",
        "stage": "develop",
        "round": 2,
        "phase": "build",
        "result": {"verdict": "PASS", "note": "probe"},
    }


def test_workflow_fields_default_to_empty_and_are_emitted() -> None:
    event = Event.from_dict(_valid_data())

    assert isinstance(event, Event)
    assert (event.agent_id, event.run_id, event.slice, event.stage, event.phase) == ("",) * 5
    assert event.round is None
    assert event.result is None
    assert Event.from_dict(event.to_dict()) == event


def test_workflow_fields_round_trip() -> None:
    event = Event.from_dict(_workflow_data())

    assert isinstance(event, Event)
    assert event.round == 2
    assert event.result == {"verdict": "PASS", "note": "probe"}
    assert Event.from_dict(event.to_dict()) == event
    assert Event.from_dict(json.loads(json.dumps(event.to_dict()))) == event


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("agent_id", 5, EventErrorCode.NOT_STRING),
        ("run_id", None, EventErrorCode.NOT_STRING),
        ("slice", ["x"], EventErrorCode.NOT_STRING),
        ("stage", 1.5, EventErrorCode.NOT_STRING),
        ("phase", {}, EventErrorCode.NOT_STRING),
        ("round", True, EventErrorCode.BAD_ROUND),
        ("round", "2", EventErrorCode.BAD_ROUND),
        ("round", 1.5, EventErrorCode.BAD_ROUND),
    ],
)
def test_wrong_typed_workflow_fields_are_rejected(
    field: str, value: object, code: EventErrorCode
) -> None:
    error = _error({**_valid_data(), field: value})

    assert error.code == code
    assert field in error.message


def test_null_round_is_accepted() -> None:
    event = Event.from_dict({**_valid_data(), "round": None})

    assert isinstance(event, Event)
    assert event.round is None


def test_oversized_result_is_dropped_not_rejected() -> None:
    oversized = {"blob": "x" * RESULT_MAXIMUM_BYTES}

    event = Event.from_dict({**_valid_data(), "result": oversized})

    assert isinstance(event, Event)
    assert event.result is None


def test_result_at_the_maximum_is_kept() -> None:
    overhead = len(json.dumps({"blob": ""}, separators=(",", ":")))
    exact = {"blob": "x" * (RESULT_MAXIMUM_BYTES - overhead)}

    event = Event.from_dict({**_valid_data(), "result": exact})

    assert isinstance(event, Event)
    assert event.result == exact


def test_non_json_result_is_rejected() -> None:
    error = _error({**_valid_data(), "result": object()})

    assert error.code == EventErrorCode.BAD_RESULT
    assert "result must be a JSON value" in error.message


@pytest.mark.parametrize("session_id", ["   ", "\t\n", "\u00a0"])
def test_whitespace_only_session_id_is_rejected(session_id: str) -> None:
    error = _error(_valid_data() | {"session_id": session_id})

    assert error.code == EventErrorCode.EMPTY
    assert "session_id" in error.message


def test_session_id_with_surrounding_whitespace_is_stored_unchanged() -> None:
    event = Event.from_dict(_valid_data() | {"session_id": " abc "})

    assert isinstance(event, Event)
    assert event.session_id == " abc "


def test_deeply_nested_result_is_rejected_as_an_invalid_event() -> None:
    nested: list[object] = []
    for _ in range(100_000):
        nested = [nested]

    error = _error({**_valid_data(), "result": nested})

    assert error.code == EventErrorCode.RESULT_TOO_DEEP
    assert "result" in error.message


def test_moderately_nested_result_is_kept() -> None:
    nested: list[object] = []
    for _ in range(200):
        nested = [nested]

    event = Event.from_dict({**_valid_data(), "result": nested})

    assert isinstance(event, Event)
    assert event.result == nested
