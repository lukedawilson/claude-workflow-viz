"""Property-based invariants for `Graph.to_yaml` and the parser (NFR3, R12, R14, R17).

These properties run against Hypothesis-generated graphs and arbitrary source text. Hypothesis
supports shrinking and seed-based reproduction (PBT-08) and is a dev-only dependency (PBT-09).
The fixture corpus pins the same invariants for the parser's real outputs (PBT-10 complement).
"""

import tempfile
from pathlib import Path

import pytest

from claude_workflow_viz.graph.graph import Graph, Node
from claude_workflow_viz.graph_source.parser import WorkflowSource

hypothesis = pytest.importorskip("hypothesis")
given = hypothesis.given
settings = hypothesis.settings
st = hypothesis.strategies

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "workflows"


@st.composite
def graphs(draw):
    """A valid graph: a chain of stage nodes ending in `done`, with `blocked` reachable."""
    count = draw(st.integers(min_value=1, max_value=6))
    identifiers = [f"n{index}" for index in range(count)]
    nodes = []
    for index, node_id in enumerate(identifiers):
        on_pass = identifiers[index + 1] if index + 1 < count else "done"
        on_fail = "blocked" if index == 0 else draw(st.sampled_from(["blocked", None]))
        nodes.append(
            Node(node_id, node_id.title(), stage=f"s{index}", on_pass=on_pass, on_fail=on_fail)
        )
    nodes.append(Node("done", "Done", terminal=True))
    nodes.append(Node("blocked", "Blocked", terminal=True))
    if draw(st.booleans()):
        return Graph(
            name="g",
            entry=identifiers[0],
            nodes=tuple(nodes),
            max_rounds=draw(st.integers(min_value=1, max_value=5)),
            on_rounds_exhausted="blocked",
        )
    return Graph(name="g", entry=identifiers[0], nodes=tuple(nodes))


@given(graphs())
@settings(max_examples=200, deadline=None)
def test_to_yaml_round_trips_over_generated_graphs(graph):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "graph.viz.yaml"
        path.write_text(graph.to_yaml(), encoding="utf-8")
        assert Graph.load(path) == graph


def _assert_invariants(graph: Graph) -> None:
    identifiers = {node.id for node in graph.nodes}
    assert graph.entry in identifiers
    reachable = {graph.entry}
    frontier = [graph.entry]
    while frontier:
        current = frontier.pop()
        node = next(n for n in graph.nodes if n.id == current)
        for target in (node.on_pass, node.on_fail):
            if target is not None:
                assert target in identifiers, f"{current} -> {target} is missing"
                if target not in reachable:
                    reachable.add(target)
                    frontier.append(target)
    assert reachable == identifiers, f"unreachable: {identifiers - reachable}"
    if graph.max_rounds is not None:
        assert graph.on_rounds_exhausted in identifiers
    for node in graph.nodes:
        if node.terminal:
            assert node.on_pass is None and node.on_fail is None


@given(graphs())
@settings(max_examples=200, deadline=None)
def test_generated_graphs_satisfy_invariants(graph):
    _assert_invariants(graph)


def test_parsed_graphs_satisfy_invariants():
    for name in ("implement.js", "cross-repo-check.js"):
        path = FIXTURES / name
        result = WorkflowSource(path.read_text(encoding="utf-8"), path).parse()
        assert isinstance(result, Graph)
        _assert_invariants(result)


@given(st.text(max_size=500))
@settings(max_examples=100, deadline=None)
def test_parse_is_deterministic_for_arbitrary_source(text):
    source = WorkflowSource(text, "workflow.js")
    assert source.parse() == source.parse()


def test_parse_determinism_over_the_fixture_corpus():
    for name in ("implement.js", "cross-repo-check.js", "rca.js"):
        path = FIXTURES / name
        source = WorkflowSource(path.read_text(encoding="utf-8"), path)
        assert source.parse() == source.parse()
