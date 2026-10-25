"""`Graph.to_yaml` serialization: byte-compatible schema, lossless round-trip (D5, R14)."""

from pathlib import Path

from claude_workflow_viz.graph.graph import DEFAULT_STEP_PATTERN, Graph, Node

ROOT = Path(__file__).resolve().parent.parent


def _round_trip(graph: Graph, tmp_path: Path) -> Graph:
    path = tmp_path / "graph.viz.yaml"
    path.write_text(graph.to_yaml(), encoding="utf-8")
    loaded = Graph.load(path)
    assert isinstance(loaded, Graph)
    return loaded


def test_example_config_round_trips_losslessly(tmp_path):
    graph = Graph.load(ROOT / "examples" / "implement.viz.yaml")
    assert isinstance(graph, Graph)
    assert _round_trip(graph, tmp_path) == graph


def test_minimal_graph_round_trips_with_defaults(tmp_path):
    graph = Graph(
        name="linear",
        entry="a",
        nodes=(Node("a", "A", stage="a", on_pass="done"), Node("done", "Done", terminal=True)),
    )
    text = graph.to_yaml()
    assert "step_pattern" not in text
    assert "max_rounds" not in text
    assert _round_trip(graph, tmp_path) == graph


def test_custom_step_pattern_and_rounds_round_trip(tmp_path):
    graph = Graph(
        name="g",
        entry="a",
        nodes=(Node("a", "A", stage="a", on_pass="done"), Node("done", "Done", terminal=True)),
        max_rounds=4,
        on_rounds_exhausted="done",
        step_pattern="(?P<slice>[^/]+)/(?P<stage>[^:]+)",
    )
    assert _round_trip(graph, tmp_path) == graph


def test_default_step_pattern_is_omitted_but_custom_is_kept():
    default = Graph(
        name="g",
        entry="a",
        nodes=(Node("a", "A", stage="a", on_pass="done"), Node("done", "Done", terminal=True)),
    )
    assert DEFAULT_STEP_PATTERN not in default.to_yaml()
    custom = Graph(
        name="g",
        entry="a",
        nodes=(Node("a", "A", stage="a", on_pass="done"), Node("done", "Done", terminal=True)),
        step_pattern="(?P<slice>[^/]+)/(?P<stage>[^:]+)",
    )
    assert "step_pattern: (?P<slice>[^/]+)/(?P<stage>[^:]+)" in custom.to_yaml()


def test_node_omits_unset_stage_step_key_and_on_fail():
    node = Node("done", "Done", terminal=True)
    text = Graph(name="g", entry="done", nodes=(node,)).to_yaml()
    assert "stage:" not in text
    assert "step_key:" not in text
    assert "on_fail:" not in text
    assert "terminal: true" in text


def test_max_rounds_only_graph_cannot_be_constructed(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        Graph(
            name="g",
            entry="a",
            nodes=(Node("a", "A", stage="a", on_pass="done"), Node("done", "Done", terminal=True)),
            max_rounds=3,
        )
