import json
from collections import deque
from pathlib import Path

import pytest

from claude_workflow_viz.graph.node_status import verdict_status
from claude_workflow_viz.workflow.events import Event
from claude_workflow_viz.workflow.run_state import RunState, _Step

_CASES = json.loads((Path(__file__).parent / "fixtures" / "status_cases.json").read_text())


def _step_from_fixture(entry: dict | None) -> _Step | None:
    if entry is None:
        return None
    return _Step(
        statuses=deque(entry["statuses"]),
        summary=entry.get("summary", ""),
        finished=entry.get("finished", False),
        agent_id=entry.get("agent_id", ""),
        run_id=entry.get("run_id", ""),
        slice=entry.get("slice", ""),
        stage=entry.get("stage", ""),
        round=entry.get("round"),
        phase=entry.get("phase", ""),
        result=entry.get("result"),
    )


@pytest.mark.parametrize("case", _CASES["node_status"], ids=lambda case: case["name"])
def test_step_display_status_matches_shared_fixture(case: dict) -> None:
    step = _step_from_fixture(case["step"])
    if step is None:
        # Rendered pending by the UI for stages with no step.
        assert case["expected"] == "pending"
    else:
        assert step.display_status() == case["expected"]


@pytest.mark.parametrize("case", _CASES["run_status"], ids=lambda case: case["name"])
def test_run_status_matches_shared_fixture(case: dict) -> None:
    state = RunState()
    for index, raw in enumerate(case["events"]):
        state.apply(Event.from_dict({"session_id": "s", "ts": float(index), "summary": "", **raw}))

    runs = state.snapshot()["sessions"]["s"]["runs"]
    assert {run_id: run["status"] for run_id, run in runs.items()} == case["expected"]


def test_snapshot_reports_node_status_for_every_step() -> None:
    state = RunState()
    base = {"session_id": "s", "ts": 1.0, "summary": "", "run_id": "r1"}
    state.apply(
        Event.from_dict({**base, "kind": "step_start", "step_key": "a", "status": "running"})
    )
    state.apply(
        Event.from_dict(
            {
                **base,
                "kind": "step_stop",
                "step_key": "b",
                "status": "pass",
                "result": {"verdict": "RED"},
            }
        )
    )

    steps = state.snapshot()["sessions"]["s"]["steps"]
    assert {key: step["node_status"] for key, step in steps.items()} == {
        "a": "running",
        "b": "fail",
    }


def test_rules_file_is_the_only_home_of_verdict_strings() -> None:
    source = (
        Path(__file__).parents[1] / "src/claude_workflow_viz/graph/node_status.py"
    ).read_text()
    rules = json.loads(
        (Path(__file__).parents[1] / "src/claude_workflow_viz/static/status_rules.json").read_text()
    )
    assert not [verdict for verdict in rules["verdicts"] if verdict in source]


def test_verdict_status_reads_fields_in_rule_order() -> None:
    assert verdict_status({"verdict": "PASS", "status": "FAIL"}) == "pass"
    assert verdict_status({"status": "FAIL"}) == "fail"
    assert verdict_status({"gate": "green"}) == "pass"
    assert verdict_status({"verdict": "MAYBE"}) is None
    assert verdict_status("APPROVED") is None
