"""Thread-safe in-memory state for every observed workflow run.

`ThreadingHTTPServer` handles ingest and SSE on separate threads, so all data sits behind one
`threading.Lock`. Per session, `RunState` keeps:

- `steps`: per step key, the ordered status history and the summary of the most recent event
  that carried a non-empty summary. Only step events (`step_start`, `step_stop`) create steps.
  Each step also carries `finished` (a stop was seen), `agent_id`, `run_id`, `slice`, `stage`,
  `round`, `phase` (latest non-empty value seen, `round` None until one is seen) and `result`
  (latest non-None value seen). The snapshot adds `node_status` per step (see `node_status.py`).
  An event with an `agent_id` finds its step by that id first, so a
  start and stop pair even when one resolved its label and the other fell back to
  `agent-<agent_id>`; the step then takes the more specific key. A stop with no prior start
  creates a finished step. A start with an `agent_id` arriving after its stop does not reopen
  the step and adds no status. A start without an `agent_id` on a finished step is a retry round
  reusing the step key: it appends its status and clears `finished`.
- `runs`: per `run_id`, `{"status": "running" | "finished", "step_keys": [...]}`. A run is
  created by a run-level event or by its first step, is `running` while any of its steps has not
  stopped, `finished` once it has steps and all have stopped, and `finished` on an explicit
  `run_stop`. A step start that opens an unfinished step returns a finished run to `running`,
  unless the run was explicitly stopped: an explicit `run_stop` is final for that run id, a later
  `run_start` does not clear it, and later step events still update step fields but never move
  the run back to `running`.
- `events`: a bounded log (oldest dropped first) used to replay recent history over SSE.

Limits bound memory against a misbehaving or hostile client:

- at most 64 sessions; a new session beyond that evicts the least recently updated one (every
  applied event counts as an update, so this is not the oldest created);
- at most 5000 steps per session; once full, an event that resolves to a new step key creates no
  step and does not refresh run status, but is still logged in `events` and delivered to
  subscribers. Existing steps keep updating;
- each step keeps only its last 100 statuses, oldest dropped first.

Subscribers get a `queue.Queue` that receives every event applied after `subscribe()`. The queues
are unbounded, so a subscriber that never drains grows without limit; the server must
unsubscribe when its connection closes.
"""

import copy
import queue
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

from claude_workflow_viz.graph.node_status import verdict_status
from claude_workflow_viz.workflow.events import Event, EventKind

DEFAULT_EVENT_LOG_MAXIMUM = 1000
"""Events retained per session when no maximum is given to `RunState`."""

DEFAULT_SESSION_MAXIMUM = 64
"""Sessions retained when no maximum is given; the least recently updated is evicted first."""

DEFAULT_STEP_MAXIMUM = 5000
"""Steps retained per session when no maximum is given; further new step keys are ignored."""

DEFAULT_STATUS_HISTORY_MAXIMUM = 100
"""Statuses retained per step when no maximum is given; the oldest is dropped first."""

_STEP_KINDS = frozenset({EventKind.STEP_START, EventKind.STEP_STOP})


RUNNING = "running"
FINISHED = "finished"


@dataclass
class _Step:
    statuses: deque[str]
    summary: str = ""
    finished: bool = False
    agent_id: str = ""
    run_id: str = ""
    slice: str = ""
    stage: str = ""
    round: int | None = None
    phase: str = ""
    result: Any = None

    def display_status(self) -> str:
        """Return 'pending', 'running', 'pass', 'fail' or 'retry' for this step.

        - unfinished: running, or retry when `round` is greater than 1
        - finished: the first recognised verdict found in `result` (fields in rule order,
          case-insensitive) when `result` is a mapping; otherwise the last entry of `statuses`
          when it is pass or fail; otherwise pass (a bare stop with unknown status counts as
          success).
        """
        if not self.finished:
            return "retry" if isinstance(self.round, int) and self.round > 1 else "running"
        from_result = verdict_status(self.result)
        if from_result is not None:
            return from_result
        statuses = self.statuses
        return statuses[-1] if statuses and statuses[-1] in ("pass", "fail") else "pass"

    def to_dict(self) -> dict[str, Any]:
        """Serialise this step (with a deep copy of `result`) for the snapshot."""
        return {
            "statuses": list(self.statuses),
            "summary": self.summary,
            "finished": self.finished,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "slice": self.slice,
            "stage": self.stage,
            "round": self.round,
            "phase": self.phase,
            "result": copy.deepcopy(self.result),
            "node_status": self.display_status(),
        }


class _Session:
    def __init__(self, event_log_maximum: int) -> None:
        self.steps: dict[str, _Step] = {}
        self.run_statuses: dict[str, str] = {}
        self.stopped_run_ids: set[str] = set()
        self.events: deque[Event] = deque(maxlen=event_log_maximum)


class RunState:
    def __init__(
        self,
        event_log_maximum: int = DEFAULT_EVENT_LOG_MAXIMUM,
        session_maximum: int = DEFAULT_SESSION_MAXIMUM,
        step_maximum: int = DEFAULT_STEP_MAXIMUM,
        status_history_maximum: int = DEFAULT_STATUS_HISTORY_MAXIMUM,
    ) -> None:
        for name, value in (
            ("event_log_maximum", event_log_maximum),
            ("session_maximum", session_maximum),
            ("step_maximum", step_maximum),
            ("status_history_maximum", status_history_maximum),
        ):
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
        self._event_log_maximum = event_log_maximum
        self._session_maximum = session_maximum
        self._step_maximum = step_maximum
        self._status_history_maximum = status_history_maximum
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._subscribers: list[queue.Queue[Event]] = []

    def apply(self, event: Event) -> None:
        """Record `event` and deliver it to every current subscriber."""
        with self._lock:
            session = self._sessions.get(event.session_id)
            if session is None:
                while len(self._sessions) >= self._session_maximum:
                    self._sessions.popitem(last=False)
                session = _Session(self._event_log_maximum)
                self._sessions[event.session_id] = session
            else:
                self._sessions.move_to_end(event.session_id)
            session.events.append(event)
            if event.kind in _STEP_KINDS:
                self._apply_step(session, event)
            elif event.run_id:
                if event.kind == EventKind.RUN_STOP:
                    session.stopped_run_ids.add(event.run_id)
                    session.run_statuses[event.run_id] = FINISHED
                else:
                    session.run_statuses.setdefault(event.run_id, RUNNING)
            for subscriber in self._subscribers:
                subscriber.put_nowait(event)

    def _apply_step(self, session: _Session, event: Event) -> None:
        key = _step_key_for(session, event)
        step = session.steps.get(key)
        if step is None:
            if len(session.steps) >= self._step_maximum:
                return
            step = _Step(statuses=deque(maxlen=self._status_history_maximum))
            session.steps[key] = step
        is_late_start = (
            bool(event.agent_id) and event.kind == EventKind.STEP_START and step.finished
        )
        if not is_late_start:
            step.statuses.append(event.status.value)
        if event.kind == EventKind.STEP_STOP:
            step.finished = True
        elif not is_late_start:
            step.finished = False
        if event.summary:
            step.summary = event.summary
        if event.result is not None:
            step.result = copy.deepcopy(event.result)
        if event.round is not None:
            step.round = event.round
        for name in ("agent_id", "run_id", "slice", "stage", "phase"):
            value = getattr(event, name)
            if value:
                setattr(step, name, value)
        if step.run_id:
            _refresh_run_status(session, step.run_id)

    def snapshot(self, session_id: str | None = None) -> dict[str, Any]:
        """Return a JSON-serialisable copy of one session, or of all when `session_id` is None."""
        with self._lock:
            return self._snapshot_locked(session_id)

    def subscribe_with_snapshot(
        self, session_id: str | None = None
    ) -> tuple[queue.Queue[Event], dict[str, Any]]:
        """Subscribe and snapshot under one lock, so each event is in exactly one of the two.

        An event applied before this call is in the snapshot; one applied after is in the queue.
        """
        subscriber: queue.Queue[Event] = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, self._snapshot_locked(session_id)

    def _snapshot_locked(self, session_id: str | None) -> dict[str, Any]:
        """Build the snapshot; the caller must hold `self._lock`."""
        selected = (
            self._sessions
            if session_id is None
            else {k: v for k, v in self._sessions.items() if k == session_id}
        )
        return {
            "sessions": {
                identifier: {
                    "steps": {key: step.to_dict() for key, step in session.steps.items()},
                    "runs": {
                        run_id: {
                            "status": status,
                            "stopped": run_id in session.stopped_run_ids,
                            "step_keys": [
                                key for key, step in session.steps.items() if step.run_id == run_id
                            ],
                        }
                        for run_id, status in session.run_statuses.items()
                    },
                    "events": [event.to_dict() for event in session.events],
                }
                for identifier, session in selected.items()
            }
        }

    def subscribe(self) -> queue.Queue[Event]:
        """Return a queue that receives each event applied from now on."""
        subscriber: queue.Queue[Event] = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[Event]) -> None:
        """Stop delivering to `subscriber`; unknown queues are ignored."""
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)


def _step_key_for(session: _Session, event: Event) -> str:
    """Find or name the step for `event`, re-keying an agent's step to a more specific key."""
    if not event.agent_id:
        return event.step_key
    fallback = f"agent-{event.agent_id}"
    current = next(
        (key for key, step in session.steps.items() if step.agent_id == event.agent_id), None
    )
    if current is None:
        return event.step_key
    if current == fallback and event.step_key != fallback and event.step_key not in session.steps:
        session.steps = {
            (event.step_key if key == current else key): step for key, step in session.steps.items()
        }
        return event.step_key
    return current


def _refresh_run_status(session: _Session, run_id: str) -> None:
    steps = [step for step in session.steps.values() if step.run_id == run_id]
    if run_id in session.stopped_run_ids:
        session.run_statuses[run_id] = FINISHED
        return
    session.run_statuses[run_id] = RUNNING if any(not step.finished for step in steps) else FINISHED
