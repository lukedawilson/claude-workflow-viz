import json
import queue
import shutil
import threading
from pathlib import Path

import pytest

from claude_workflow_viz.workflow import run_state
from claude_workflow_viz.workflow.events import Event, EventKind, EventStatus
from claude_workflow_viz.workflow.hook_adapter import normalise
from claude_workflow_viz.workflow.run_state import DEFAULT_EVENT_LOG_MAXIMUM, RunState


def _event(
    session_id: str = "session-1",
    step_key: str = "develop",
    status: EventStatus = EventStatus.RUNNING,
    summary: str = "",
    kind: EventKind = EventKind.STEP_START,
    ts: float = 1.0,
) -> Event:
    return Event(
        session_id=session_id, ts=ts, kind=kind, step_key=step_key, status=status, summary=summary
    )


def test_sessions_are_kept_separate() -> None:
    state = RunState()
    state.apply(_event(session_id="a", step_key="plan", summary="plan a"))
    state.apply(_event(session_id="b", step_key="review", summary="review b"))

    everything = state.snapshot()["sessions"]
    assert set(everything) == {"a", "b"}
    assert set(everything["a"]["steps"]) == {"plan"}
    assert set(everything["b"]["steps"]) == {"review"}
    assert len(everything["a"]["events"]) == 1
    only_b = state.snapshot("b")["sessions"]
    assert set(only_b) == {"b"}


def test_snapshot_of_unknown_session_is_empty() -> None:
    assert RunState().snapshot("missing") == {"sessions": {}}


def test_status_history_preserves_order_and_summary_is_latest_non_empty() -> None:
    state = RunState()
    state.apply(_event(status=EventStatus.RUNNING, summary="started"))
    state.apply(_event(status=EventStatus.FAIL, summary="", kind=EventKind.STEP_STOP))
    state.apply(_event(status=EventStatus.RUNNING, summary="retrying"))
    state.apply(_event(status=EventStatus.PASS, summary="", kind=EventKind.STEP_STOP))

    step = state.snapshot()["sessions"]["session-1"]["steps"]["develop"]
    assert step["statuses"] == ["running", "fail", "running", "pass"]
    assert step["summary"] == "retrying"


def test_summary_is_empty_until_an_event_carries_one() -> None:
    state = RunState()
    state.apply(_event(summary=""))
    assert state.snapshot()["sessions"]["session-1"]["steps"]["develop"]["summary"] == ""


def test_event_log_is_bounded_and_drops_the_oldest() -> None:
    state = RunState(event_log_maximum=3)
    for index in range(4):
        state.apply(_event(step_key=f"step-{index}", ts=float(index)))

    log = state.snapshot()["sessions"]["session-1"]["events"]
    assert [entry["step_key"] for entry in log] == ["step-1", "step-2", "step-3"]


def test_default_event_log_maximum_is_documented_and_used() -> None:
    state = RunState()
    for index in range(DEFAULT_EVENT_LOG_MAXIMUM + 1):
        state.apply(_event(ts=float(index)))
    log = state.snapshot()["sessions"]["session-1"]["events"]
    assert len(log) == DEFAULT_EVENT_LOG_MAXIMUM
    assert log[0]["ts"] == 1.0


def test_snapshot_is_a_json_serialisable_copy() -> None:
    state = RunState()
    state.apply(_event(summary="hello"))

    snapshot = state.snapshot()
    json.dumps(snapshot)
    snapshot["sessions"]["session-1"]["steps"]["develop"]["statuses"].append("pass")
    snapshot["sessions"]["session-1"]["events"].clear()
    snapshot["sessions"].clear()

    fresh = state.snapshot()["sessions"]["session-1"]
    assert fresh["steps"]["develop"]["statuses"] == ["running"]
    assert len(fresh["events"]) == 1


def test_run_level_events_are_logged_without_creating_a_step() -> None:
    state = RunState()
    state.apply(_event(step_key="", kind=EventKind.RUN_START, status=EventStatus.RUNNING))

    session = state.snapshot()["sessions"]["session-1"]
    assert session["steps"] == {}
    assert len(session["events"]) == 1


def test_subscriber_receives_events_applied_after_subscribe_only() -> None:
    state = RunState()
    state.apply(_event(step_key="before"))
    subscription = state.subscribe()
    state.apply(_event(step_key="during"))
    state.unsubscribe(subscription)
    state.apply(_event(step_key="after"))

    received = []
    while True:
        try:
            received.append(subscription.get_nowait().step_key)
        except queue.Empty:
            break
    assert received == ["during"]


def test_unsubscribe_of_unknown_queue_is_harmless() -> None:
    RunState().unsubscribe(queue.Queue())


def test_concurrent_apply_loses_no_events() -> None:
    thread_count, per_thread = 8, 50
    state = RunState(event_log_maximum=thread_count * per_thread)
    subscription = state.subscribe()

    def worker(number: int) -> None:
        for index in range(per_thread):
            state.apply(_event(session_id=f"s{number}", step_key=f"step-{index}"))

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    sessions = state.snapshot()["sessions"]
    assert sum(len(session["events"]) for session in sessions.values()) == thread_count * per_thread
    assert subscription.qsize() == thread_count * per_thread


# --- agent pairing and run completion ---

RUN = "wf_ec22ed24-66b"


def _agent_event(
    kind: EventKind,
    agent_id: str = "x1",
    step_key: str = "s1/develop:r1",
    status: EventStatus | None = None,
    run_id: str = RUN,
    summary: str = "",
    **overrides: object,
) -> Event:
    if status is None:
        status = EventStatus.RUNNING if kind == EventKind.STEP_START else EventStatus.PASS
    return Event(
        session_id="session-1",
        ts=1.0,
        kind=kind,
        step_key=step_key,
        status=status,
        summary=summary,
        agent_id=agent_id,
        run_id=run_id,
        **overrides,  # type: ignore[arg-type]
    )


def _session(state: RunState) -> dict:
    return state.snapshot()["sessions"]["session-1"]


def test_start_and_stop_pair_by_agent_id_when_step_keys_differ() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START, step_key="agent-x1", run_id=""))
    state.apply(_agent_event(EventKind.STEP_STOP, slice="s1", stage="develop", round=1))

    steps = _session(state)["steps"]
    assert list(steps) == ["s1/develop:r1"]
    assert steps["s1/develop:r1"]["statuses"] == ["running", "pass"]
    assert steps["s1/develop:r1"]["run_id"] == RUN
    assert (steps["s1/develop:r1"]["slice"], steps["s1/develop:r1"]["round"]) == ("s1", 1)


def test_stop_resolved_less_specifically_keeps_the_specific_step_key() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START))
    state.apply(_agent_event(EventKind.STEP_STOP, step_key="agent-x1"))

    steps = _session(state)["steps"]
    assert list(steps) == ["s1/develop:r1"]
    assert steps["s1/develop:r1"]["statuses"] == ["running", "pass"]


def test_stop_without_a_start_creates_a_finished_step() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_STOP, status=EventStatus.FAIL))

    step = _session(state)["steps"]["s1/develop:r1"]
    assert step["statuses"] == ["fail"]
    assert step["finished"] is True
    assert _session(state)["runs"][RUN]["status"] == "finished"


def test_start_arriving_after_stop_leaves_the_step_finished() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_STOP))
    state.apply(_agent_event(EventKind.STEP_START, step_key="agent-x1"))

    session = _session(state)
    assert session["steps"]["s1/develop:r1"]["statuses"] == ["pass"]
    assert session["steps"]["s1/develop:r1"]["finished"] is True
    assert session["runs"][RUN]["status"] == "finished"


def test_step_keeps_latest_non_empty_summary_and_latest_non_none_result() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START, summary="began"))
    state.apply(_agent_event(EventKind.STEP_STOP, summary="done", result={"ok": True}))
    state.apply(_agent_event(EventKind.STEP_STOP, summary="", result=None))

    step = _session(state)["steps"]["s1/develop:r1"]
    assert step["summary"] == "done"
    assert step["result"] == {"ok": True}


def test_events_without_agent_id_are_keyed_by_step_key() -> None:
    state = RunState()
    state.apply(_event(step_key="develop"))
    state.apply(_event(step_key="develop", status=EventStatus.PASS, kind=EventKind.STEP_STOP))
    state.apply(_event(step_key="review"))

    steps = _session(state)["steps"]
    assert set(steps) == {"develop", "review"}
    assert steps["develop"]["statuses"] == ["running", "pass"]
    assert _session(state)["runs"] == {}


def test_replayed_probe_run_has_four_steps_and_finishes_after_the_last_stop(tmp_path: Path) -> None:
    fixtures = Path(__file__).parent / "fixtures"
    shutil.copytree(fixtures / "tree", tmp_path, dirs_exist_ok=True)
    events = []
    for line in (fixtures / "probe_payloads.jsonl").read_text().splitlines():
        payload = json.loads(line) | {"cwd": str(tmp_path)}
        event = normalise(payload, lambda: 1.0)
        if event is not None and event.run_id == RUN:
            events.append(event)
    state = RunState()

    statuses = []
    for event in events:
        state.apply(event)
        statuses.append(state.snapshot()["sessions"]["probe-session"]["runs"][RUN]["status"])

    session = state.snapshot()["sessions"]["probe-session"]
    assert set(session["steps"]) == {
        "s1/develop:r1",
        "s1/review:r1",
        "s1/code-review:r1",
        "s1/develop:r2",
    }
    assert sorted(session["runs"][RUN]["step_keys"]) == sorted(session["steps"])
    # events: develop start, develop stop, review start, code-review start, review stop, ...
    assert statuses[2:5] == ["running"] * 3  # review and code-review overlap
    assert statuses[-1] == "finished"


def test_run_is_running_while_any_step_is_unstopped() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START, agent_id="a", step_key="s1/review:r1"))
    state.apply(_agent_event(EventKind.STEP_START, agent_id="b", step_key="s1/code-review:r1"))
    state.apply(_agent_event(EventKind.STEP_STOP, agent_id="a", step_key="s1/review:r1"))
    assert _session(state)["runs"][RUN]["status"] == "running"
    state.apply(_agent_event(EventKind.STEP_STOP, agent_id="b", step_key="s1/code-review:r1"))
    assert _session(state)["runs"][RUN]["status"] == "finished"


def test_start_after_the_run_finished_returns_it_to_running() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_STOP))
    assert _session(state)["runs"][RUN]["status"] == "finished"

    state.apply(_agent_event(EventKind.STEP_START, agent_id="y2", step_key="s1/develop:r2"))
    assert _session(state)["runs"][RUN]["status"] == "running"


def test_retry_start_without_agent_id_reopens_the_step_and_the_run() -> None:
    state = RunState()
    start = {"agent_id": "", "step_key": "s1/develop:r1"}
    state.apply(_agent_event(EventKind.STEP_START, **start))
    state.apply(_agent_event(EventKind.STEP_STOP, **start))
    assert _session(state)["runs"][RUN]["status"] == "finished"

    state.apply(_agent_event(EventKind.STEP_START, **start))

    session = _session(state)
    assert session["steps"]["s1/develop:r1"]["finished"] is False
    assert session["steps"]["s1/develop:r1"]["statuses"] == ["running", "pass", "running"]
    assert session["runs"][RUN]["status"] == "running"


def test_start_with_agent_id_after_that_agents_stop_does_not_reopen_the_step() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START))
    state.apply(_agent_event(EventKind.STEP_STOP))
    state.apply(_agent_event(EventKind.STEP_START))

    session = _session(state)
    assert session["steps"]["s1/develop:r1"]["finished"] is True
    assert session["steps"]["s1/develop:r1"]["statuses"] == ["running", "pass"]
    assert session["runs"][RUN]["status"] == "finished"


def test_step_start_after_run_stop_leaves_the_run_finished() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START, agent_id="a", step_key="s1/develop:r1"))
    state.apply(_agent_event(EventKind.RUN_STOP, agent_id="", step_key="Workflow"))

    state.apply(_agent_event(EventKind.STEP_START, agent_id="b", step_key="s1/review:r1"))

    session = _session(state)
    assert session["steps"]["s1/review:r1"]["statuses"] == ["running"]
    assert session["runs"][RUN]["status"] == "finished"


def test_retry_start_after_run_stop_reopens_the_step_but_not_the_run() -> None:
    state = RunState()
    start = {"agent_id": "", "step_key": "s1/develop:r1"}
    state.apply(_agent_event(EventKind.STEP_START, **start))
    state.apply(_agent_event(EventKind.STEP_STOP, **start))
    state.apply(_agent_event(EventKind.RUN_STOP, agent_id="", step_key="Workflow"))

    state.apply(_agent_event(EventKind.STEP_START, **start))

    session = _session(state)
    assert session["steps"]["s1/develop:r1"]["finished"] is False
    assert session["runs"][RUN]["status"] == "finished"


def test_run_start_after_run_stop_does_not_clear_the_explicit_stop() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.RUN_STOP, agent_id="", step_key="Workflow"))
    state.apply(_agent_event(EventKind.RUN_START, agent_id="", step_key="Workflow"))
    state.apply(_agent_event(EventKind.STEP_START, agent_id="a", step_key="s1/develop:r1"))

    assert _session(state)["runs"][RUN]["status"] == "finished"


def test_snapshot_flags_an_explicitly_stopped_run_even_after_its_stop_event_ages_out() -> None:
    state = RunState(event_log_maximum=1)
    state.apply(_agent_event(EventKind.RUN_STOP, agent_id="", step_key="Workflow"))
    state.apply(_agent_event(EventKind.STEP_START, agent_id="a", step_key="s1/develop:r1"))

    session = _session(state)
    assert [event["kind"] for event in session["events"]] == ["step_start"]
    assert session["runs"][RUN]["stopped"] is True


def test_snapshot_does_not_flag_a_run_finished_only_by_its_steps() -> None:
    state = RunState()
    start = {"agent_id": "", "step_key": "s1/develop:r1"}
    state.apply(_agent_event(EventKind.STEP_START, **start))
    state.apply(_agent_event(EventKind.STEP_STOP, **start))

    run = _session(state)["runs"][RUN]
    assert run["status"] == "finished"
    assert run["stopped"] is False


def test_workflow_run_start_creates_a_running_run_and_never_finishes_it() -> None:
    state = RunState()
    state.apply(
        _agent_event(EventKind.RUN_START, agent_id="", step_key="Workflow", status=EventStatus.PASS)
    )

    run = _session(state)["runs"][RUN]
    assert run["status"] == "running"
    assert run["step_keys"] == []


def test_run_stop_marks_the_run_finished() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.RUN_START, agent_id="", step_key="Workflow"))
    state.apply(_agent_event(EventKind.RUN_STOP, agent_id="", step_key="Workflow"))

    assert _session(state)["runs"][RUN]["status"] == "finished"


def test_snapshot_with_runs_is_a_json_serialisable_copy() -> None:
    state = RunState()
    state.apply(_agent_event(EventKind.STEP_START, result=None))
    snapshot = state.snapshot()
    json.dumps(snapshot)
    snapshot["sessions"]["session-1"]["runs"][RUN]["step_keys"].append("x")
    snapshot["sessions"]["session-1"]["runs"][RUN]["status"] = "finished"

    run = _session(state)["runs"][RUN]
    assert run["step_keys"] == ["s1/develop:r1"]
    assert run["status"] == "running"


def test_default_limits_are_documented_values() -> None:
    assert run_state.DEFAULT_SESSION_MAXIMUM == 64
    assert run_state.DEFAULT_STEP_MAXIMUM == 5000
    assert run_state.DEFAULT_STATUS_HISTORY_MAXIMUM == 100


def test_new_session_evicts_the_least_recently_updated_not_the_oldest_created() -> None:
    state = RunState(session_maximum=2)
    state.apply(_event(session_id="a"))
    state.apply(_event(session_id="b"))
    state.apply(_event(session_id="a", step_key="again"))
    state.apply(_event(session_id="c"))

    assert set(state.snapshot()["sessions"]) == {"a", "c"}


def test_default_session_maximum_is_enforced() -> None:
    state = RunState()
    for index in range(run_state.DEFAULT_SESSION_MAXIMUM + 1):
        state.apply(_event(session_id=f"s{index}"))

    sessions = state.snapshot()["sessions"]
    assert len(sessions) == run_state.DEFAULT_SESSION_MAXIMUM
    assert "s0" not in sessions


def test_new_step_beyond_the_maximum_is_logged_and_delivered_but_not_stored() -> None:
    state = RunState(step_maximum=2)
    subscriber = state.subscribe()
    for key in ("one", "two", "three"):
        state.apply(_event(step_key=key))

    session = state.snapshot()["sessions"]["session-1"]
    assert set(session["steps"]) == {"one", "two"}
    assert [event["step_key"] for event in session["events"]] == ["one", "two", "three"]
    assert [subscriber.get_nowait().step_key for _ in range(3)] == ["one", "two", "three"]


def test_step_beyond_the_maximum_does_not_refresh_run_status() -> None:
    state = RunState(step_maximum=1)
    state.apply(_agent_event(EventKind.STEP_START, agent_id="a1", step_key="one"))
    state.apply(_agent_event(EventKind.STEP_STOP, agent_id="a1", step_key="one"))
    state.apply(_agent_event(EventKind.STEP_START, agent_id="a2", step_key="two"))

    run = _session(state)["runs"][RUN]
    assert run == {"status": "finished", "stopped": False, "step_keys": ["one"]}


def test_existing_steps_still_update_at_the_step_maximum() -> None:
    state = RunState(step_maximum=1)
    state.apply(_event(step_key="one", summary="first"))
    state.apply(_event(step_key="two"))
    state.apply(_event(step_key="one", status=EventStatus.PASS, summary="second"))

    step = _session(state)["steps"]["one"]
    assert step["statuses"] == ["running", "pass"]
    assert step["summary"] == "second"


def test_default_step_maximum_is_enforced() -> None:
    state = RunState(event_log_maximum=10)
    for index in range(run_state.DEFAULT_STEP_MAXIMUM + 1):
        state.apply(_event(step_key=f"step-{index}"))

    steps = _session(state)["steps"]
    assert len(steps) == run_state.DEFAULT_STEP_MAXIMUM
    assert f"step-{run_state.DEFAULT_STEP_MAXIMUM}" not in steps


def test_status_history_keeps_the_last_100_in_order_and_node_status_reads_the_latest() -> None:
    state = RunState()
    for index in range(101):
        state.apply(_event(status=EventStatus.RUNNING, summary=str(index)))
    state.apply(_event(kind=EventKind.STEP_STOP, status=EventStatus.FAIL))

    step = _session(state)["steps"]["develop"]
    assert isinstance(step["statuses"], list)
    assert step["statuses"] == ["running"] * 99 + ["fail"]
    assert step["node_status"] == "fail"


def test_status_history_trims_from_the_front() -> None:
    state = RunState(status_history_maximum=3)
    for status in (EventStatus.RUNNING, EventStatus.FAIL, EventStatus.RUNNING, EventStatus.PASS):
        state.apply(_event(status=status))

    assert _session(state)["steps"]["develop"]["statuses"] == ["fail", "running", "pass"]


def test_apply_does_not_construct_a_session_when_one_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = RunState()
    state.apply(_event())
    constructed = []
    original = run_state._Session

    def counting(*args: object) -> run_state._Session:
        constructed.append(args)
        return original(*args)

    monkeypatch.setattr(run_state, "_Session", counting)
    state.apply(_event(step_key="other"))

    assert constructed == []


def test_result_is_deep_copied_when_stored() -> None:
    state = RunState()
    result = {"verdict": "PASS", "details": {"items": [1]}}
    event = Event(
        session_id="session-1",
        ts=1.0,
        kind=EventKind.STEP_STOP,
        step_key="develop",
        status=EventStatus.PASS,
        summary="",
        result=result,
    )
    state.apply(event)
    result["details"]["items"].append(2)
    result["verdict"] = "FAIL"

    stored = _session(state)["steps"]["develop"]["result"]
    assert stored == {"verdict": "PASS", "details": {"items": [1]}}


def test_subscribe_with_snapshot_delivers_each_event_exactly_once() -> None:
    event_count = 200
    for _ in range(50):
        state = RunState()
        start = threading.Barrier(2)

        def writer(state: RunState = state, start: threading.Barrier = start) -> None:
            start.wait()
            for index in range(event_count):
                state.apply(_event(step_key=f"step-{index}", ts=float(index)))

        thread = threading.Thread(target=writer)
        thread.start()
        start.wait()
        subscriber, snapshot = state.subscribe_with_snapshot()
        thread.join()

        in_snapshot = [
            entry["ts"] for session in snapshot["sessions"].values() for entry in session["events"]
        ]
        in_queue = []
        while not subscriber.empty():
            in_queue.append(subscriber.get_nowait().ts)
        assert sorted(in_snapshot + in_queue) == [float(index) for index in range(event_count)]


def test_step_to_dict_serialises_the_step_and_its_display_status() -> None:
    from collections import deque

    step = run_state._Step(
        statuses=deque(["running", "pass"]),
        summary="done",
        finished=True,
        round=2,
        result={"verdict": "FAIL"},
    )
    assert step.to_dict() == {
        "statuses": ["running", "pass"],
        "summary": "done",
        "finished": True,
        "agent_id": "",
        "run_id": "",
        "slice": "",
        "stage": "",
        "round": 2,
        "phase": "",
        "result": {"verdict": "FAIL"},
        "node_status": "fail",
    }
