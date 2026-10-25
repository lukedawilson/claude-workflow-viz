"""Workflow graph config: load and strictly validate `<workflow>.viz.yaml`.

Schema (YAML, parsed with a `yaml.SafeLoader` subclass only; unknown keys and duplicate keys at any
level are rejected so typos fail loudly):

    name: implement                  # required, string
    entry: develop                   # required, node id where a run starts
    max_rounds: 3                    # optional, positive integer
    on_rounds_exhausted: blocked     # node id; required when max_rounds is set
    step_pattern: '...'              # optional regex with named groups slice, stage, round;
                                     # the stage group is required. Default `DEFAULT_STEP_PATTERN`
                                     # (same shape as `_STEP_LABEL` in hook_adapter.py).
                                     # Rejected: longer than 200 characters; nested quantifiers
                                     # such as `(a+)+`; Python-only syntax the UI cannot convert
                                     # (`(?P=name)`, inline flags `(?i)`, `(?i:...)`); anything
                                     # Python cannot compile (e.g. variable-width lookbehind)
    nodes:                           # required, non-empty list
      - id: develop                  # required, unique
        label: Develop               # required, display text
        stage: develop               # optional, unique across nodes; the stage this node shows
        step_key: planner            # optional, unique; maps a step whose label carries no
                                     # `<slice>/<stage>:r<round>` stage (matched on the whole label)
        terminal: false              # optional boolean; terminal nodes (done, blocked,
                                     # needs-context) have no stage and no outgoing edges
        on_pass: gate                # node id; required on every non-terminal node
        on_fail: develop             # optional node id

A value may not be one node's stage and another node's step_key (the same node may carry it as
both). `Graph.linear` never reuses the reserved terminal ids (done, blocked, needs-context) for
stage nodes: such a stage gets the id `stage-<stage>` (numeric suffix if taken) and keeps its
stage and label.

A node maps to a stage. Slice and round are instance dimensions of a run, never separate nodes.
Every validation failure is returned as a `GraphError` with a typed `GraphErrorCode` naming the
node and field.
"""

import re
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

DEFAULT_STEP_PATTERN = r"(?P<slice>[^/]+)/(?P<stage>[^:]+):r(?P<round>\d+)"
DONE_NODE_ID = "done"
RESERVED_TERMINAL_IDS = frozenset({DONE_NODE_ID, "blocked", "needs-context"})

_TOP_LEVEL_KEYS = {"name", "entry", "max_rounds", "on_rounds_exhausted", "step_pattern", "nodes"}
_NODE_KEYS = {"id", "label", "stage", "step_key", "terminal", "on_pass", "on_fail"}


class GraphErrorCode(StrEnum):
    UNREADABLE = "unreadable"
    BAD_YAML = "bad_yaml"
    NOT_MAPPING = "not_mapping"
    DUPLICATE_KEY = "duplicate_key"
    UNKNOWN_KEY = "unknown_key"
    MISSING_FIELD = "missing_field"
    EMPTY_FIELD = "empty_field"
    BAD_STEP_PATTERN_LENGTH = "bad_step_pattern_length"
    NESTED_QUANTIFIERS = "nested_quantifiers"
    PYTHON_ONLY_PATTERN = "python_only_pattern"
    UNCOMPILABLE_PATTERN = "uncompilable_pattern"
    MISSING_STAGE_GROUP = "missing_stage_group"
    BAD_MAX_ROUNDS = "bad_max_rounds"
    ON_ROUNDS_EXHAUSTED_REQUIRED = "on_rounds_exhausted_required"
    NO_NODES = "no_nodes"
    NODE_NOT_MAPPING = "node_not_mapping"
    BAD_TERMINAL_FLAG = "bad_terminal_flag"
    BAD_TERMINAL = "bad_terminal"
    DUPLICATE_NODE_ID = "duplicate_node_id"
    DUPLICATE_STAGE = "duplicate_stage"
    DUPLICATE_STEP_KEY = "duplicate_step_key"
    AMBIGUOUS_VALUE = "ambiguous_value"
    UNKNOWN_NODE_REFERENCE = "unknown_node_reference"


@dataclass(frozen=True)
class GraphError:
    """A load or validation failure returned by `Graph.load` instead of an exception."""

    code: GraphErrorCode
    message: str


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that records a duplicate key in any mapping instead of keeping the last.

    `Graph.load` turns the first recorded duplicate into a `DUPLICATE_KEY` error, so the YAML
    parse itself never raises for a duplicate key.
    """

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self.duplicates: list[tuple[int, object]] = []

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue  # merged keys may be overridden; super() flattens them
            key = self.construct_object(key_node, deep=True)
            if isinstance(key, Hashable):
                if key in seen:
                    self.duplicates.append((key_node.start_mark.line + 1, key))
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


_MAX_STEP_PATTERN_LENGTH = 200
_INLINE_FLAGS = re.compile(r"\?[aiLmsux-]+[:)]")


def _reject_unsafe_step_pattern(pattern: str) -> GraphError | None:
    if len(pattern) > _MAX_STEP_PATTERN_LENGTH:
        return GraphError(
            GraphErrorCode.BAD_STEP_PATTERN_LENGTH,
            f"graph field step_pattern is longer than {_MAX_STEP_PATTERN_LENGTH} characters",
        )
    # Each open group carries whether its body holds a quantifier (directly or in a nested group).
    groups: list[bool] = []
    in_class = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if in_class:
            in_class = char != "]"
        elif char == "[":
            in_class = True
            if pattern.startswith("[]", index) or pattern.startswith("[^]", index):
                index += 1 if pattern[index + 1] == "]" else 2
        elif char == "(":
            if pattern.startswith("(?P=", index) or _INLINE_FLAGS.match(pattern, index + 1):
                return GraphError(
                    GraphErrorCode.PYTHON_ONLY_PATTERN,
                    "graph field step_pattern uses Python-only syntax the UI cannot convert: "
                    f"{pattern[index : index + 4]}",
                )
            groups.append(False)
        elif char == ")" and groups:
            body_has_quantifier = groups.pop()
            if body_has_quantifier and _quantifier_at(pattern, index + 1):
                return GraphError(
                    GraphErrorCode.NESTED_QUANTIFIERS,
                    "graph field step_pattern has nested quantifiers (a quantified group "
                    "containing a quantifier), which risks catastrophic backtracking",
                )
            if groups and (body_has_quantifier or _quantifier_at(pattern, index + 1)):
                groups[-1] = True
        elif groups and _unbounded_quantifier_at(pattern, index):
            groups[-1] = True
        index += 1
    return None


def _unbounded_quantifier_at(pattern: str, index: int) -> bool:
    return pattern[index] in "+*" or re.match(r"\{\d*,\}", pattern[index:]) is not None


def _quantifier_at(pattern: str, index: int) -> bool:
    return index < len(pattern) and (
        pattern[index] in "+*" or re.match(r"\{\d*,?\d*\}", pattern[index:]) is not None
    )


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    stage: str | None = None
    terminal: bool = False
    on_pass: str | None = None
    on_fail: str | None = None
    step_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "stage": self.stage,
            "step_key": self.step_key,
            "terminal": self.terminal,
            "on_pass": self.on_pass,
            "on_fail": self.on_fail,
        }


@dataclass(frozen=True)
class Graph:
    name: str
    entry: str
    nodes: tuple[Node, ...]
    max_rounds: int | None = None
    on_rounds_exhausted: str | None = None
    step_pattern: str = DEFAULT_STEP_PATTERN

    def __post_init__(self) -> None:
        if self.max_rounds is not None and self.on_rounds_exhausted is None:
            raise ValueError("Graph field on_rounds_exhausted is required when max_rounds is set")

    def node_for(self, stage_or_step_key: str) -> str | None:
        for node in self.nodes:
            if stage_or_step_key in (node.stage, node.step_key):
                return node.id
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entry": self.entry,
            "max_rounds": self.max_rounds,
            "on_rounds_exhausted": self.on_rounds_exhausted,
            "step_pattern": self.step_pattern,
            "nodes": [node.to_dict() for node in self.nodes],
        }

    def to_yaml(self) -> str:
        """Serialize this graph to the hand-authored viz.yaml schema, losslessly round-tripping.

        Only set fields are emitted, matching how a human writes the file: `max_rounds` carries
        `on_rounds_exhausted` with it, the default `step_pattern` is omitted, and a node omits
        `stage`, `step_key`, `terminal`, `on_fail` when unset. The output is a `yaml.safe_dump`
        that `Graph.load` reads back into an equal `Graph` (D5, DOMAIN-08).
        """
        document: dict[str, Any] = {"name": self.name, "entry": self.entry}
        if self.max_rounds is not None:
            document["max_rounds"] = self.max_rounds
            if self.on_rounds_exhausted is not None:
                document["on_rounds_exhausted"] = self.on_rounds_exhausted
        if self.step_pattern != DEFAULT_STEP_PATTERN:
            document["step_pattern"] = self.step_pattern
        document["nodes"] = [
            _omit_unset(
                {
                    "id": node.id,
                    "label": node.label,
                    "stage": node.stage,
                    "step_key": node.step_key,
                    "terminal": node.terminal,
                    "on_pass": node.on_pass,
                    "on_fail": node.on_fail,
                }
            )
            for node in self.nodes
        ]
        return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)

    @classmethod
    def load(cls, path: str | Path) -> "GraphResult":
        """Load and validate a `<workflow>.viz.yaml` file, or return a `GraphError`."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            return GraphError(
                GraphErrorCode.UNREADABLE, f"cannot read graph config {path}: {error}"
            )
        loader = _UniqueKeyLoader(text)
        try:
            document = loader.get_single_data()
        except yaml.YAMLError as error:
            return GraphError(GraphErrorCode.BAD_YAML, f"invalid YAML in {path}: {error}")
        if loader.duplicates:
            line, key = loader.duplicates[0]
            return GraphError(GraphErrorCode.DUPLICATE_KEY, f"duplicate key {key!r} at line {line}")
        if not isinstance(document, Mapping):
            return GraphError(
                GraphErrorCode.NOT_MAPPING,
                f"graph config {path} must be a mapping at the top level",
            )
        return _build(document)

    @classmethod
    def linear(cls, step_stages: Sequence[str]) -> "Graph":
        """Fallback graph: one node per distinct stage in first-seen order, ending in `done`."""
        stages = list(dict.fromkeys(step_stages))
        taken = set(stages) | RESERVED_TERMINAL_IDS
        identifiers: list[str] = []
        for stage in stages:
            if stage not in RESERVED_TERMINAL_IDS:
                identifiers.append(stage)
                continue
            candidate = f"stage-{stage}"
            suffix = 2
            while candidate in taken:
                candidate = f"stage-{stage}-{suffix}"
                suffix += 1
            taken.add(candidate)
            identifiers.append(candidate)
        following = [*identifiers[1:], DONE_NODE_ID][: len(stages)]
        nodes = [
            Node(id=identifier, label=stage, stage=stage, on_pass=target)
            for identifier, stage, target in zip(identifiers, stages, following, strict=True)
        ]
        nodes.append(Node(id=DONE_NODE_ID, label="Done", terminal=True))
        return cls(name="linear", entry=nodes[0].id, nodes=tuple(nodes))


GraphResult = Graph | GraphError
"""What `Graph.load` returns: a valid graph or a typed load/validation error."""


def _build(document: Mapping[str, Any]) -> Graph | GraphError:
    error = _reject_unknown(document, _TOP_LEVEL_KEYS, "graph")
    if error is not None:
        return error
    name = _string(document, "name", "graph", required=True)
    if isinstance(name, GraphError):
        return name
    entry = _string(document, "entry", "graph", required=True)
    if isinstance(entry, GraphError):
        return entry
    step_pattern = _string(document, "step_pattern", "graph") or DEFAULT_STEP_PATTERN
    error = _reject_unsafe_step_pattern(step_pattern)
    if error is not None:
        return error
    try:
        compiled = re.compile(step_pattern)
    except re.error as compile_error:
        return GraphError(
            GraphErrorCode.UNCOMPILABLE_PATTERN,
            f"graph field step_pattern does not compile: {compile_error}",
        )
    if "stage" not in compiled.groupindex:
        return GraphError(
            GraphErrorCode.MISSING_STAGE_GROUP,
            "graph field step_pattern must define a named group 'stage'",
        )

    max_rounds = document.get("max_rounds")
    if max_rounds is not None and (
        isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1
    ):
        return GraphError(
            GraphErrorCode.BAD_MAX_ROUNDS,
            f"graph field max_rounds must be a positive integer: {max_rounds!r}",
        )
    exhausted = _string(document, "on_rounds_exhausted", "graph")
    if isinstance(exhausted, GraphError):
        return exhausted
    if max_rounds is not None and exhausted is None:
        return GraphError(
            GraphErrorCode.ON_ROUNDS_EXHAUSTED_REQUIRED,
            "graph field on_rounds_exhausted is required when max_rounds is set",
        )

    raw_nodes = document.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return GraphError(GraphErrorCode.NO_NODES, "graph field nodes must be a non-empty list")
    nodes: list[Node] = []
    for index, raw in enumerate(raw_nodes):
        node = _node(raw, index)
        if isinstance(node, GraphError):
            return node
        nodes.append(node)

    identifiers: set[str] = set()
    stage_owner: dict[str, str] = {}
    step_key_owner: dict[str, str] = {}
    for node in nodes:
        if node.id in identifiers:
            return GraphError(
                GraphErrorCode.DUPLICATE_NODE_ID, f"node {node.id!r}: duplicate node id"
            )
        identifiers.add(node.id)
        if node.stage is not None:
            if node.stage in stage_owner:
                return GraphError(
                    GraphErrorCode.DUPLICATE_STAGE,
                    f"node {node.id!r} field stage {node.stage!r} already maps to node "
                    f"{stage_owner[node.stage]!r}",
                )
            stage_owner[node.stage] = node.id
        if node.step_key is not None:
            if node.step_key in step_key_owner:
                return GraphError(
                    GraphErrorCode.DUPLICATE_STEP_KEY,
                    f"node {node.id!r} field step_key {node.step_key!r} already maps to node "
                    f"{step_key_owner[node.step_key]!r}",
                )
            step_key_owner[node.step_key] = node.id
    for value, stage_node in stage_owner.items():
        key_node = step_key_owner.get(value)
        if key_node is not None and key_node != stage_node:
            return GraphError(
                GraphErrorCode.AMBIGUOUS_VALUE,
                f"value {value!r} is the stage of node {stage_node!r} and the step_key of "
                f"node {key_node!r}; a value may map to only one node",
            )
    for node in nodes:
        for field in ("on_pass", "on_fail"):
            target = getattr(node, field)
            if target is not None and target not in identifiers:
                return GraphError(
                    GraphErrorCode.UNKNOWN_NODE_REFERENCE,
                    f"node {node.id!r} field {field} names unknown node {target!r}",
                )
    if entry not in identifiers:
        return GraphError(
            GraphErrorCode.UNKNOWN_NODE_REFERENCE,
            f"graph field entry names unknown node {entry!r}",
        )
    if exhausted is not None and exhausted not in identifiers:
        return GraphError(
            GraphErrorCode.UNKNOWN_NODE_REFERENCE,
            f"graph field on_rounds_exhausted names unknown node {exhausted!r}",
        )

    return Graph(
        name=name,
        entry=entry,
        nodes=tuple(nodes),
        max_rounds=max_rounds,
        on_rounds_exhausted=exhausted,
        step_pattern=step_pattern,
    )


def _node(raw: Any, index: int) -> Node | GraphError:
    if not isinstance(raw, Mapping):
        return GraphError(
            GraphErrorCode.NODE_NOT_MAPPING, f"node at index {index} must be a mapping"
        )
    where = f"node {raw['id']!r}" if isinstance(raw.get("id"), str) else f"node at index {index}"
    error = _reject_unknown(raw, _NODE_KEYS, where)
    if error is not None:
        return error
    identifier = _string(raw, "id", where, required=True)
    if isinstance(identifier, GraphError):
        return identifier
    where = f"node {identifier!r}"
    label = _string(raw, "label", where, required=True)
    if isinstance(label, GraphError):
        return label
    stage = _string(raw, "stage", where)
    if isinstance(stage, GraphError):
        return stage
    step_key = _string(raw, "step_key", where)
    if isinstance(step_key, GraphError):
        return step_key
    on_pass = _string(raw, "on_pass", where)
    if isinstance(on_pass, GraphError):
        return on_pass
    on_fail = _string(raw, "on_fail", where)
    if isinstance(on_fail, GraphError):
        return on_fail
    terminal = raw.get("terminal", False)
    if not isinstance(terminal, bool):
        return GraphError(
            GraphErrorCode.BAD_TERMINAL_FLAG, f"{where} field terminal must be a boolean"
        )
    if terminal:
        if stage is not None or step_key is not None:
            return GraphError(
                GraphErrorCode.BAD_TERMINAL,
                f"{where} is terminal and must not have a stage or step_key",
            )
        if on_pass is not None or on_fail is not None:
            return GraphError(
                GraphErrorCode.BAD_TERMINAL,
                f"{where} is terminal and must not have on_pass or on_fail",
            )
    elif on_pass is None:
        return GraphError(
            GraphErrorCode.MISSING_FIELD,
            f"{where} field on_pass is required on a non-terminal node",
        )
    return Node(identifier, label, stage, terminal, on_pass, on_fail, step_key)


def _string(
    source: Mapping[str, Any], key: str, where: str, *, required: bool = False
) -> str | None | GraphError:
    if key not in source or source[key] is None:
        if required:
            return GraphError(GraphErrorCode.MISSING_FIELD, f"{where} field {key} is required")
        return None
    value = source[key]
    if not isinstance(value, str) or not value:
        return GraphError(
            GraphErrorCode.EMPTY_FIELD, f"{where} field {key} must be a non-empty string: {value!r}"
        )
    return value


def _reject_unknown(source: Mapping[str, Any], allowed: set[str], where: str) -> GraphError | None:
    unknown = sorted(str(key) for key in source if key not in allowed)
    if unknown:
        return GraphError(GraphErrorCode.UNKNOWN_KEY, f"{where} has unknown key {unknown[0]!r}")
    return None


def _omit_unset(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop keys a human would not write: `None` values and a false `terminal` flag."""
    return {
        key: value
        for key, value in mapping.items()
        if value is not None and not (key == "terminal" and value is False)
    }
