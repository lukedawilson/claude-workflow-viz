"""`WorkflowSource.parse`: the strict subset, named failures, and graph invariants (R1-R17)."""

import time
from pathlib import Path

from claude_workflow_viz.graph.graph import Graph
from claude_workflow_viz.graph_source.parse_failures import ParseFailureReport
from claude_workflow_viz.graph_source.parser import WorkflowSource

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "workflows"


def _parse(name: str) -> WorkflowSource:
    path = FIXTURES / name
    return WorkflowSource(path.read_text(encoding="utf-8"), path)


def _parse_text(source: str, name: str = "workflow.js") -> WorkflowSource:
    return WorkflowSource(source, name)


def _nodes(graph: Graph) -> dict[str, tuple[str | None, str | None]]:
    return {node.id: (node.stage, node.step_key) for node in graph.nodes}


def test_implement_js_round_trips_the_full_subset():
    result = _parse("implement.js").parse()
    assert isinstance(result, Graph)
    assert result.name == "implement"
    assert result.entry == "pre-flight"
    assert result.max_rounds == 3
    assert result.on_rounds_exhausted == "blocked"
    assert _nodes(result) == {
        "pre-flight": (None, "pre-flight/head-check"),
        "planner": (None, "planner"),
        "gate-baseline": (None, "gate-baseline"),
        "develop": ("develop", None),
        "gate": ("gate", None),
        "review": ("review", None),
        "code-review": ("code-review", None),
        "classify": ("classify", None),
        "verify-fsm": ("verify-fsm", None),
        "done": (None, None),
        "blocked": (None, None),
        "needs-context": (None, None),
    }
    edges = {node.id: (node.on_pass, node.on_fail) for node in result.nodes}
    assert edges["pre-flight"] == ("planner", "blocked")
    assert edges["planner"] == ("gate-baseline", "needs-context")
    assert edges["gate-baseline"] == ("develop", "blocked")
    assert edges["develop"] == ("gate", "needs-context")
    assert edges["gate"] == ("review", "develop")
    assert edges["review"] == ("code-review", "develop")
    assert edges["code-review"] == ("classify", "develop")
    assert edges["classify"] == ("verify-fsm", None)
    assert edges["verify-fsm"] == ("done", "develop")


def test_cross_repo_check_js_parses_to_a_trivial_chain():
    result = _parse("cross-repo-check.js").parse()
    assert isinstance(result, Graph)
    assert result.name == "cross-repo-check"
    assert result.entry == "scan"
    assert result.max_rounds is None
    assert _nodes(result) == {
        "scan": (None, "scan/repos"),
        "summarise": (None, "summarise/findings"),
        "done": (None, None),
        "blocked": (None, None),
    }
    edges = {node.id: (node.on_pass, node.on_fail) for node in result.nodes}
    assert edges["scan"] == ("summarise", None)
    assert edges["summarise"] == ("done", "blocked")


def test_rca_js_reports_the_round_first_label_and_missing_exhaustion():
    result = _parse("rca.js").parse()
    assert isinstance(result, ParseFailureReport)
    codes = {failure.code for failure in result.failures}
    assert "unsupported-label" in codes
    assert "unsupported-terminal" in codes
    label = next(f for f in result.failures if f.code == "unsupported-label")
    assert label.location.line == 24
    assert "r${round}/investigate" in label.context


def test_every_parsed_graph_is_accepted_by_graph_load(tmp_path):
    for name in ("implement.js", "cross-repo-check.js"):
        result = _parse(name).parse()
        assert isinstance(result, Graph)
        path = tmp_path / f"{name}.viz.yaml"
        path.write_text(result.to_yaml(), encoding="utf-8")
        assert Graph.load(path) == result


def test_missing_meta_is_reported():
    source = """
export async function w(input) {
  const a = await agent('a', { label: 'a/one' });
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["missing-meta"]


def test_no_agent_calls_is_reported():
    source = """
export const meta = { name: 'empty' };
export async function empty(input) {
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["no-agent-calls"]


def test_loop_back_without_max_rounds_is_missing_max_rounds():
    source = """
export const meta = { name: 'loop' };
export async function loop(input) {
  let round = 1;
  while (round <= 3) {
    const a = await agent('a', { label: `${s}/develop:r${round}` });
    if (a.bad) { round += 1; continue; }
    break;
  }
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["missing-max-rounds"]


def test_do_while_is_unsupported_control_flow():
    source = """
export const meta = { name: 'dowhile' };
export async function dowhile(input) {
  let round = 1;
  do {
    const a = await agent('a', { label: 'a/one' });
    round += 1;
  } while (round <= 3);
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["unsupported-control-flow"]


def test_unrecognised_return_literal_is_unsupported_terminal():
    source = """
export const meta = { name: 'term' };
export async function term(input) {
  const a = await agent('a', { label: 'a/one' });
  if (a.bad) { return 'MAYBE'; }
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["unsupported-terminal"]


def test_if_else_with_agents_on_both_branches_is_unsupported_conditional():
    source = """
export const meta = { name: 'cond' };
export async function cond(input) {
  if (input.a) {
    const a = await agent('a', { label: 'a/one' });
  } else {
    const b = await agent('b', { label: 'b/two' });
  }
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["unsupported-conditional"]


def test_promise_all_with_a_non_agent_member_is_unsupported_parallel():
    source = """
export const meta = { name: 'par' };
export async function par(input) {
  const [a, b] = await Promise.all([
    agent('a', { label: 'a/one' }),
    helper(),
  ]);
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["unsupported-parallel"]


def test_promise_all_of_agents_becomes_a_chain_of_nodes(tmp_path):
    source = """
export const meta = { name: 'par' };
export async function par(input) {
  const [a, b] = await Promise.all([
    agent('a', { label: 'a/one' }),
    agent('b', { label: 'b/two' }),
  ]);
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, Graph)
    assert result.entry == "a"
    # Promise.all members linearise into a source-order chain: the graph schema has no
    # fork/join concept, and chaining keeps every member reachable from the entry.
    edges = {node.id: node.on_pass for node in result.nodes}
    assert edges["a"] == "b"
    assert edges["b"] == "done"
    assert "done" in {node.id for node in result.nodes if node.terminal}


def test_a_guarded_agent_call_is_a_normal_node():
    source = """
export const meta = { name: 'guard' };
export async function guard(input) {
  const a = await agent('a', { label: 'a/one' });
  if (a.flag) {
    const b = await agent('b', { label: 'b/two' });
  }
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, Graph)
    assert {node.id for node in result.nodes} >= {"a", "b", "done"}
    by_id = {node.id: node for node in result.nodes}
    assert by_id["a"].on_pass == "b"
    assert by_id["b"].on_pass == "done"


def test_computed_label_is_unsupported_label():
    source = """
export const meta = { name: 'bad' };
export async function bad(input) {
  const a = await agent('a', { label: someLabel });
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["unsupported-label"]


def test_no_partial_graph_when_any_failure_is_collected():
    source = """
export const meta = { name: 'mixed' };
export async function mixed(input) {
  const a = await agent('a', { label: 'a/one' });
  if (a.bad) { return 'MAYBE'; }
  const b = await agent('b', { label: `r${n}/x` });
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert {f.code for f in result.failures} == {"unsupported-terminal", "unsupported-label"}


def test_parse_is_deterministic():
    source = _parse("implement.js")
    assert source.parse() == source.parse()
    rca = _parse("rca.js")
    assert rca.parse() == rca.parse()


def test_pathological_input_parses_in_bounded_time():
    line = "  if (x) { agent('a', { label: 'a" + ("x" * 40) + "/one' }); }\n"
    source = "export const meta = { name: 'stress' };\n" + line * 25000
    started = time.monotonic()
    result = _parse_text(source, "stress.js").parse()
    assert time.monotonic() - started < 2.0
    assert isinstance(result, (Graph, ParseFailureReport))


def test_computed_return_is_unsupported_terminal():
    source = """
export const meta = { name: 'term' };
export async function term(input) {
  const a = await agent('a', { label: 'a/one' });
  if (a.bad) { return MAYBE; }
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, ParseFailureReport)
    assert [f.code for f in result.failures] == ["unsupported-terminal"]


def test_continue_without_semicolon_still_creates_a_loop_back():
    source = """
export const meta = { name: 'loop' };
const MAX_ROUNDS = 3;
export async function loop(input) {
  let round = 1;
  while (round <= MAX_ROUNDS) {
    const a = await agent('a', { label: `${s}/develop:r${round}` });
    if (a.bad) { round += 1; continue }
    break;
  }
  if (round >= MAX_ROUNDS) { return 'BLOCKED'; }
  return 'DONE';
}
"""
    result = _parse_text(source).parse()
    assert isinstance(result, Graph)
    edges = {node.id: (node.on_pass, node.on_fail) for node in result.nodes}
    assert edges["develop"] == ("done", "develop")
    assert result.on_rounds_exhausted == "blocked"


def test_parser_output_matches_checked_in_demo_graph_fixture():
    """The Node demo-progression test replays events against
    tests/fixtures/implement-graph.json; keep it in lockstep with the parser."""
    import json

    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "implement-graph.json"
    source_path = Path("tests/fixtures/workflows/implement.js")
    graph = WorkflowSource(source_path.read_text(), source_path).parse()
    assert isinstance(graph, Graph)
    assert graph.to_dict() == json.loads(fixture.read_text())
