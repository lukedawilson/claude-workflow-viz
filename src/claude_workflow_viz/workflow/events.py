"""Normalised event schema shared by every event source.

Every adapter (the hook adapter now, the transcript-tail adapter later) turns what it observes
into an `Event` and hands it to an `EventSink`. The server and UI only ever see `Event`.

Timestamp: `ts` is a float of Unix epoch seconds (UTC). One numeric form keeps ordering and
JSON round-tripping trivial; an integer is accepted on input and converted to float.

Summary cap: `summary` is truncated to `SUMMARY_MAXIMUM_LENGTH` characters rather than rejected,
because a long agent message must not cause a progress event to be dropped.

Workflow fields: `agent_id`, `run_id`, `slice`, `stage` and `phase` are optional strings
(default empty), `round` is an optional non-boolean integer (default None) and `result` is an
optional structured JSON value (default None). Events without them stay valid, and `to_dict`
omits unset ones so existing payloads are unchanged. Like `summary`, `result` is bounded rather
than rejected: if its compact JSON serialisation exceeds `RESULT_MAXIMUM_BYTES` (well under the
server's request body limit) it is stored as None, so an oversized result never causes a
progress event to be dropped.

`Event.from_dict` never raises: every validation failure is returned as an `EventError` carrying
a typed `EventErrorCode` and a human-readable message. A `result` nested so deeply that
serialising it exceeds the recursion limit is returned as `RESULT_TOO_DEEP`.
"""

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SUMMARY_MAXIMUM_LENGTH = 500
RESULT_MAXIMUM_BYTES = 16 * 1024


class EventErrorCode(StrEnum):
    NOT_MAPPING = "not_mapping"
    MISSING_FIELD = "missing_field"
    EMPTY = "empty"
    NOT_STRING = "not_string"
    BAD_KIND = "bad_kind"
    BAD_STATUS = "bad_status"
    BAD_TIMESTAMP = "bad_timestamp"
    NON_FINITE_TIMESTAMP = "non_finite_timestamp"
    TIMESTAMP_TOO_LARGE = "timestamp_too_large"
    BAD_ROUND = "bad_round"
    BAD_RESULT = "bad_result"
    RESULT_TOO_DEEP = "result_too_deep"


@dataclass(frozen=True)
class EventError:
    """A validation failure returned by `Event.from_dict` instead of an exception."""

    code: EventErrorCode
    message: str


class EventKind(StrEnum):
    RUN_START = "run_start"
    RUN_STOP = "run_stop"
    STEP_START = "step_start"
    STEP_STOP = "step_stop"


class EventStatus(StrEnum):
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Event:
    session_id: str
    ts: float
    kind: EventKind
    step_key: str
    status: EventStatus
    summary: str
    agent_id: str = ""
    run_id: str = ""
    slice: str = ""
    stage: str = ""
    round: int | None = None
    phase: str = ""
    result: Any = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EventResult":
        """Validate `data` and build an Event, or return an `EventError` on any problem."""
        if not isinstance(data, Mapping):
            return EventError(EventErrorCode.NOT_MAPPING, "event must be a mapping")
        session_id = _string(data, "session_id")
        if isinstance(session_id, EventError):
            return session_id
        if not session_id.strip():
            return EventError(EventErrorCode.EMPTY, "session_id must not be empty")
        ts = _timestamp(data)
        if isinstance(ts, EventError):
            return ts
        kind = _enum(data, "kind", EventKind, EventErrorCode.BAD_KIND)
        if isinstance(kind, EventError):
            return kind
        step_key = _string(data, "step_key")
        if isinstance(step_key, EventError):
            return step_key
        status = _enum(data, "status", EventStatus, EventErrorCode.BAD_STATUS)
        if isinstance(status, EventError):
            return status
        summary = _string(data, "summary")
        if isinstance(summary, EventError):
            return summary
        agent_id = _optional_string(data, "agent_id")
        if isinstance(agent_id, EventError):
            return agent_id
        run_id = _optional_string(data, "run_id")
        if isinstance(run_id, EventError):
            return run_id
        slice_ = _optional_string(data, "slice")
        if isinstance(slice_, EventError):
            return slice_
        stage = _optional_string(data, "stage")
        if isinstance(stage, EventError):
            return stage
        round_ = _optional_round(data)
        if isinstance(round_, EventError):
            return round_
        phase = _optional_string(data, "phase")
        if isinstance(phase, EventError):
            return phase
        result = _bounded_result(data.get("result"))
        if isinstance(result, EventError):
            return result
        return cls(
            session_id=session_id,
            ts=ts,
            kind=kind,
            step_key=step_key,
            status=status,
            summary=summary[:SUMMARY_MAXIMUM_LENGTH],
            agent_id=agent_id,
            run_id=run_id,
            slice=slice_,
            stage=stage,
            round=round_,
            phase=phase,
            result=result,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping that `from_dict` accepts."""
        data: dict[str, Any] = {
            "session_id": self.session_id,
            "ts": self.ts,
            "kind": self.kind.value,
            "step_key": self.step_key,
            "status": self.status.value,
            "summary": self.summary,
        }
        optional = {
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "slice": self.slice,
            "stage": self.stage,
            "round": self.round,
            "phase": self.phase,
            "result": self.result,
        }
        data.update({key: value for key, value in optional.items() if value not in ("", None)})
        return data


EventResult = Event | EventError
"""What `Event.from_dict` returns: a valid event or a typed validation error."""


EventSink = Callable[[Event], None]
"""What an event source emits into. Both the hook adapter and the future transcript-tail
adapter are fed a sink and call it once per normalised event."""


def _required(data: Mapping[str, Any], field: str) -> Any | EventError:
    if field not in data:
        return EventError(EventErrorCode.MISSING_FIELD, f"missing field: {field}")
    return data[field]


def _string(data: Mapping[str, Any], field: str) -> str | EventError:
    value = _required(data, field)
    if isinstance(value, EventError):
        return value
    if not isinstance(value, str):
        return EventError(EventErrorCode.NOT_STRING, f"{field} must be a string")
    return value


def _optional_string(data: Mapping[str, Any], field: str) -> str | EventError:
    return _string(data, field) if field in data else ""


def _optional_round(data: Mapping[str, Any]) -> int | None | EventError:
    value = data.get("round")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return EventError(EventErrorCode.BAD_ROUND, "round must be an integer or null")
    return value


def _bounded_result(value: Any) -> Any:
    try:
        encoded = json.dumps(value, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return EventError(EventErrorCode.BAD_RESULT, "result must be a JSON value")
    except RecursionError:
        return EventError(EventErrorCode.RESULT_TOO_DEEP, "result is nested too deeply")
    return value if len(encoded.encode()) <= RESULT_MAXIMUM_BYTES else None


def _timestamp(data: Mapping[str, Any]) -> float | EventError:
    value = _required(data, "ts")
    if isinstance(value, EventError):
        return value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return EventError(EventErrorCode.BAD_TIMESTAMP, "ts must be a number of epoch seconds")
    try:
        seconds = float(value)
    except OverflowError:
        return EventError(EventErrorCode.TIMESTAMP_TOO_LARGE, "ts is too large")
    if not math.isfinite(seconds):
        return EventError(EventErrorCode.NON_FINITE_TIMESTAMP, "ts must be finite")
    return seconds


def _enum[E: StrEnum](
    data: Mapping[str, Any], field: str, enum_type: type[E], code: EventErrorCode
) -> E | EventError:
    value = _string(data, field)
    if isinstance(value, EventError):
        return value
    try:
        return enum_type(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_type)
        return EventError(code, f"{field} must be one of: {allowed}")
