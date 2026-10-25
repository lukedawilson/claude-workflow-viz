import json
from pathlib import Path

import pytest

from claude_workflow_viz.graph.graph import Graph, GraphError, GraphErrorCode, _build

VALID = """
name: implement
entry: develop
max_rounds: 3
on_rounds_exhausted: blocked
nodes:
  - {id: develop, label: Develop, stage: develop, on_pass: gate}
  - {id: gate, label: Gate, stage: gate, on_pass: done, on_fail: develop}
  - {id: done, label: Done, terminal: true}
  - {id: blocked, label: Blocked, terminal: true}
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "flow.viz.yaml"
    path.write_text(text)
    return path


def expect_error(tmp_path: Path, text: str, *fragments: str) -> None:
    graph = Graph.load(write(tmp_path, text))
    assert isinstance(graph, GraphError)
    for fragment in fragments:
        assert fragment in graph.message


def test_valid_config_loads_and_round_trips_through_json(tmp_path):
    graph = Graph.load(write(tmp_path, VALID))
    assert isinstance(graph, Graph)
    assert graph.name == "implement"
    assert graph.entry == "develop"
    assert graph.max_rounds == 3
    data = json.loads(json.dumps(graph.to_dict()))
    assert [node["id"] for node in data["nodes"]] == ["develop", "gate", "done", "blocked"]
    assert data["nodes"][1]["on_fail"] == "develop"
    assert data["entry"] == "develop"


def test_node_for_maps_stage_to_node_id(tmp_path):
    graph = Graph.load(write(tmp_path, VALID))
    assert isinstance(graph, Graph)
    assert graph.node_for("gate") == "gate"
    assert graph.node_for("nope") is None


def test_default_step_pattern_matches_step_labels(tmp_path):
    import re

    graph = Graph.load(write(tmp_path, VALID))
    assert isinstance(graph, Graph)
    match = re.fullmatch(graph.step_pattern, "s1/develop:r2")
    assert match and match["stage"] == "develop" and match["round"] == "2"


def test_python_object_tag_is_rejected_not_executed(tmp_path):
    expect_error(tmp_path, "name: !!python/object/apply:os.system ['true']\n")


def test_unknown_edge_target(tmp_path):
    expect_error(tmp_path, VALID.replace("on_pass: gate", "on_pass: ghost"), "develop", "on_pass")


def test_duplicate_node_id(tmp_path):
    text = VALID + "  - {id: gate, label: Again, stage: other, on_pass: done}\n"
    expect_error(tmp_path, text, "gate", "duplicate")


def test_duplicate_stage_mapping(tmp_path):
    expect_error(tmp_path, VALID.replace("stage: gate", "stage: develop"), "gate", "stage")


def test_missing_label_and_id(tmp_path):
    expect_error(tmp_path, VALID.replace("label: Gate, ", ""), "gate", "label")
    expect_error(tmp_path, VALID.replace("{id: gate, ", "{"), "id")


def test_missing_on_pass_on_non_terminal(tmp_path):
    expect_error(tmp_path, VALID.replace(", on_pass: gate", ""), "develop", "on_pass")


def test_terminal_with_edges(tmp_path):
    expect_error(
        tmp_path,
        VALID.replace(
            "terminal: true}\n  - {id: blocked", "terminal: true, on_pass: gate}\n  - {id: blocked"
        ),
        "done",
        "terminal",
    )


def test_unknown_keys(tmp_path):
    expect_error(tmp_path, VALID + "extra: 1\n", "extra")
    expect_error(tmp_path, VALID.replace("on_pass: gate", "on_pas: gate"), "develop", "on_pas")


def test_unknown_entry_and_exhausted_target(tmp_path):
    expect_error(tmp_path, VALID.replace("entry: develop", "entry: ghost"), "entry", "ghost")
    expect_error(
        tmp_path,
        VALID.replace("on_rounds_exhausted: blocked", "on_rounds_exhausted: ghost"),
        "on_rounds_exhausted",
        "ghost",
    )


def test_max_rounds_must_be_positive_integer(tmp_path):
    for bad in ("0", "-1", "'3'", "true", "1.5"):
        expect_error(tmp_path, VALID.replace("max_rounds: 3", f"max_rounds: {bad}"), "max_rounds")


def test_on_rounds_exhausted_required_with_max_rounds(tmp_path):
    expect_error(
        tmp_path, VALID.replace("on_rounds_exhausted: blocked\n", ""), "on_rounds_exhausted"
    )


def test_step_pattern_must_compile_and_have_stage_group(tmp_path):
    expect_error(tmp_path, VALID + "step_pattern: '(unclosed'\n", "step_pattern")
    expect_error(tmp_path, VALID + "step_pattern: '(?P<slice>.+)'\n", "step_pattern", "stage")


def test_wrong_types(tmp_path):
    expect_error(tmp_path, VALID.replace("label: Gate", "label: [x]"), "gate", "label")
    expect_error(
        tmp_path,
        VALID.replace(
            "terminal: true}\n  - {id: blocked", "terminal: yes please}\n  - {id: blocked"
        ),
        "done",
    )


def test_empty_non_mapping_and_missing_file(tmp_path):
    expect_error(tmp_path, "")
    expect_error(tmp_path, "- a\n- b\n")
    missing = tmp_path / "absent.yaml"
    error = Graph.load(missing)
    assert isinstance(error, GraphError)
    assert str(missing) in error.message


def test_linear_graph_first_seen_order_without_duplicates():
    graph = Graph.linear(["develop", "gate", "develop", "review"])
    assert [node.id for node in graph.nodes] == ["develop", "gate", "review", "done"]
    assert [node.on_pass for node in graph.nodes] == ["gate", "review", "done", None]
    assert graph.entry == "develop"
    assert graph.node_for("review") == "review"
    json.dumps(graph.to_dict())


def test_linear_graph_empty_has_only_done():
    graph = Graph.linear([])
    assert [node.id for node in graph.nodes] == ["done"]
    assert graph.nodes[0].terminal
    assert graph.entry == "done"


@pytest.mark.parametrize(
    "stages",
    [
        ["develop", "done"],
        ["done"],
        ["blocked", "stage-blocked"],
        ["needs-context", "stage-needs-context", "stage-needs-context-2"],
    ],
)
def test_linear_graph_node_ids_are_unique_and_validate(stages):
    graph = Graph.linear(stages)
    ids = [node.id for node in graph.nodes]
    assert len(ids) == len(set(ids))
    assert ids[-1] == "done"
    assert graph.nodes[-1].terminal
    for stage in stages:
        node = next(n for n in graph.nodes if n.stage == stage)
        assert node.label == stage
        assert graph.node_for(stage) == node.id
    assert graph.nodes[-2].on_pass == "done"
    assert graph.entry == graph.nodes[0].id
    assert isinstance(_build(graph.to_dict()), Graph)


def test_linear_graph_namespaces_a_reserved_stage_id():
    graph = Graph.linear(["done"])
    assert [node.id for node in graph.nodes] == ["stage-done", "done"]


def test_stage_equal_to_another_nodes_step_key_is_rejected(tmp_path):
    text = """
name: g
entry: a
nodes:
  - {id: a, label: A, stage: shared, on_pass: b}
  - {id: b, label: B, step_key: shared, on_pass: done}
  - {id: done, label: Done, terminal: true}
"""
    expect_error(tmp_path, text, "'a'", "'b'", "'shared'")


def test_same_node_may_carry_one_value_as_stage_and_step_key(tmp_path):
    text = """
name: g
entry: a
nodes:
  - {id: a, label: A, stage: same, step_key: same, on_pass: done}
  - {id: done, label: Done, terminal: true}
"""
    graph = Graph.load(write(tmp_path, text))
    assert isinstance(graph, Graph)
    assert graph.entry == "a"


def test_example_graph_still_loads():
    graph = Graph.load(Path(__file__).parent.parent / "examples" / "implement.viz.yaml")
    assert isinstance(graph, Graph)


def test_node_for_maps_a_step_key_for_labels_without_a_stage(tmp_path):
    text = VALID.replace(
        "nodes:\n",
        "nodes:\n  - {id: planner, label: Planner, step_key: planner, on_pass: develop}\n",
    )
    graph = Graph.load(write(tmp_path, text))
    assert isinstance(graph, Graph)
    assert graph.node_for("planner") == "planner"
    assert graph.to_dict()["nodes"][0]["step_key"] == "planner"


def test_step_key_must_be_unique_and_not_on_terminal_nodes(tmp_path):
    base = "nodes:\n  - {id: planner, label: Planner, step_key: planner, on_pass: develop}\n"
    duplicate = VALID.replace(
        "nodes:\n", base + "  - {id: x, label: X, step_key: planner, on_pass: done}\n"
    )
    expect_error(tmp_path, duplicate, "x", "step_key")
    terminal = VALID.replace(
        "{id: done, label: Done, terminal: true}",
        "{id: done, label: Done, terminal: true, step_key: k}",
    )
    expect_error(tmp_path, terminal, "done", "step_key")


def test_duplicate_top_level_key_is_rejected_with_key_and_line(tmp_path):
    text = VALID.replace("entry: develop\n", "entry: develop\nname: other\n")
    # leading newline in VALID: `name` is line 2, the duplicate sits on line 4
    expect_error(tmp_path, text, "duplicate", "name", "line 4")


def test_duplicate_key_inside_flow_style_node_is_rejected_with_key_and_line(tmp_path):
    text = VALID.replace(
        "{id: develop, label: Develop, stage: develop,",
        "{id: develop, label: Develop, stage: develop, stage: other,",
    )
    expect_error(tmp_path, text, "duplicate", "stage", "line 7")


MERGE_GRAPH = """
name: implement
entry: develop
nodes:
  - &base {id: develop, label: Develop, stage: develop, on_pass: gate}
  - {<<: *base, id: gate, stage: gate, on_pass: done}
  - {id: done, label: Done, terminal: true}
"""


def test_yaml_merge_key_still_loads(tmp_path):
    graph = Graph.load(write(tmp_path, MERGE_GRAPH))
    assert isinstance(graph, Graph)
    gate = next(node for node in graph.to_dict()["nodes"] if node["id"] == "gate")
    assert gate["label"] == "Develop"
    assert gate["stage"] == "gate"


def test_duplicate_key_next_to_merge_key_is_rejected(tmp_path):
    text = MERGE_GRAPH.replace("id: gate, stage: gate,", "id: gate, stage: gate, id: other,")
    expect_error(tmp_path, text, "duplicate", "id")


def test_step_pattern_longer_than_200_characters_is_rejected(tmp_path):
    long_pattern = "(?P<stage>" + "a" * 200 + ")"
    expect_error(tmp_path, VALID + f"step_pattern: '{long_pattern}'\n", "step_pattern", "200")


@pytest.mark.parametrize(
    "pattern",
    [
        "(?P<stage>a+)+",
        "(?P<stage>a*)*",
        "(?P<stage>(?:a+)*)",
        "(?P<stage>(a{1,})+)",
        "(?P<stage>((a+)))+",
    ],
)
def test_nested_quantifier_step_pattern_is_rejected(tmp_path, pattern):
    expect_error(tmp_path, VALID + f"step_pattern: '{pattern}'\n", "step_pattern", "nested")


@pytest.mark.parametrize(
    "pattern",
    ["(?P<stage>a)(?P=stage)", "(?i)(?P<stage>a)", "(?aiLmsux)(?P<stage>a)", "(?i:(?P<stage>a))"],
)
def test_python_only_step_pattern_syntax_is_rejected(tmp_path, pattern):
    expect_error(tmp_path, VALID + f"step_pattern: '{pattern}'\n", "step_pattern", "Python-only")


def test_variable_width_lookbehind_is_rejected_by_the_compile_path(tmp_path):
    expect_error(
        tmp_path, VALID + "step_pattern: '(?<=a+)(?P<stage>b)'\n", "step_pattern", "look-behind"
    )


@pytest.mark.parametrize(
    "pattern",
    [
        r"(?P<slice>[^/]+)/(?P<stage>[^:]+):r(?P<round>\d+)",
        r"(?P<stage>(?:ab)+)",
        r"(?P<stage>[a+*]+)\+",
        r"(?P<stage>a+)(?=b)(?<=a)",
    ],
)
def test_safe_step_patterns_are_accepted(tmp_path, pattern):
    graph = Graph.load(write(tmp_path, VALID + f"step_pattern: '{pattern}'\n"))
    assert isinstance(graph, Graph)
    assert graph.step_pattern == pattern


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (VALID.replace("on_pass: gate", "on_pass: ghost"), GraphErrorCode.UNKNOWN_NODE_REFERENCE),
        (
            VALID + "  - {id: gate, label: Again, stage: other, on_pass: done}\n",
            GraphErrorCode.DUPLICATE_NODE_ID,
        ),
        ("{not yaml\n", GraphErrorCode.BAD_YAML),
        ("- a\n- b\n", GraphErrorCode.NOT_MAPPING),
        (
            VALID.replace("entry: develop\n", "entry: develop\nname: other\n"),
            GraphErrorCode.DUPLICATE_KEY,
        ),
        (VALID.replace("max_rounds: 3", "max_rounds: 0"), GraphErrorCode.BAD_MAX_ROUNDS),
        (VALID.replace(", on_pass: gate", ""), GraphErrorCode.MISSING_FIELD),
        (VALID + "step_pattern: '(?P<stage>a+)+'\n", GraphErrorCode.NESTED_QUANTIFIERS),
        (VALID + "step_pattern: '(?i)(?P<stage>a)'\n", GraphErrorCode.PYTHON_ONLY_PATTERN),
        (VALID + "extra: 1\n", GraphErrorCode.UNKNOWN_KEY),
        ("name: x\nentry: y\nnodes: []\n", GraphErrorCode.NO_NODES),
        (VALID.replace("stage: gate", "stage: develop"), GraphErrorCode.DUPLICATE_STAGE),
    ],
)
def test_error_codes_are_typed(tmp_path, text, code):
    graph = Graph.load(write(tmp_path, text))

    assert isinstance(graph, GraphError)
    assert graph.code == code
    assert isinstance(graph.code, GraphErrorCode)


def test_missing_file_returns_a_typed_error(tmp_path):
    error = Graph.load(tmp_path / "absent.yaml")

    assert isinstance(error, GraphError)
    assert error.code == GraphErrorCode.UNREADABLE
