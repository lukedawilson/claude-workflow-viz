from pathlib import Path

import pytest

from claude_workflow_viz.graph.graph import Graph

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "implement.viz.yaml"
STAGES = ["develop", "gate", "review", "code-review", "classify", "verify-fsm"]


@pytest.fixture(scope="module")
def graph():
    return Graph.load(EXAMPLE)


def node(graph, node_id):
    return next(candidate for candidate in graph.nodes if candidate.id == node_id)


def test_node_set(graph):
    assert {candidate.id for candidate in graph.nodes} == {
        "pre-flight",
        "planner",
        "gate-baseline",
        "develop",
        "gate",
        "review",
        "code-review",
        "classify",
        "verify-fsm",
        "done",
        "blocked",
        "needs-context",
    }


def test_pass_chain_runs_from_develop_to_done(graph):
    chain = [*STAGES, "done"]
    for current, following in zip(chain, chain[1:], strict=False):
        assert node(graph, current).on_pass == following
    assert node(graph, "pre-flight").on_pass == "planner"
    assert node(graph, "planner").on_pass == "gate-baseline"
    assert node(graph, "gate-baseline").on_pass == "develop"


@pytest.mark.parametrize("failing", ["gate", "review", "code-review", "verify-fsm"])
def test_failing_checks_route_back_to_develop(graph, failing):
    assert node(graph, failing).on_fail == "develop"


def test_unrecoverable_failures_end_in_terminal_nodes(graph):
    assert node(graph, "planner").on_fail == "needs-context"
    assert node(graph, "pre-flight").on_fail == "blocked"
    assert node(graph, "gate-baseline").on_fail == "blocked"
    assert node(graph, "develop").on_fail == "blocked"
    assert node(graph, "classify").on_fail == "blocked"


def test_rounds_are_bounded_at_three_then_blocked(graph):
    assert graph.max_rounds == 3
    assert graph.on_rounds_exhausted == "blocked"


@pytest.mark.parametrize("stage", STAGES)
def test_node_for_maps_each_slice_stage(graph, stage):
    assert graph.node_for(stage) == stage


def test_node_for_maps_the_planner_label(graph):
    assert graph.node_for("planner") == "planner"


@pytest.mark.parametrize(
    ("label", "node_id"),
    [
        ("pre-flight/head-check", "pre-flight"),
        ("planner", "planner"),
        ("gate-baseline", "gate-baseline"),
    ],
)
def test_node_for_maps_every_slice_less_label_implement_emits(graph, label, node_id):
    assert graph.node_for(label) == node_id
