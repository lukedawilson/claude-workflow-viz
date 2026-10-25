"""Strict static parse of a Claude Code workflow's JavaScript into the `Graph` contract.

`WorkflowSource` owns the executable spec of the supported subset (UE-A1, R1): `export const meta`
name, `const MAX_ROUNDS`, `agent(...)` call sites with literal or `${slice}/<stage>:r${round}`
template labels, `while`/`for` + `continue` loop-backs, early literal `return` terminals, the
exhaustion return, guarded (else-less) agent calls, and `Promise.all` groups. Everything outside
the subset is a named `ParseFailure` collected exhaustively in one pass (R2, R3); the result is a
`Graph` (validated by `Graph.load`, R12) or a `ParseFailureReport`, never an exception (R17).

Patterns are linear-time: the only quantifier inside a quantified group is the dotted-name
tail in `_STATIC_NAME`, whose `.` separator is unique, so the match is unambiguous and
adversarial input cannot trigger catastrophic backtracking (NFR-A1/A2).
"""

import bisect
import re
from dataclasses import dataclass
from pathlib import Path

from claude_workflow_viz.graph.graph import Graph, Node
from claude_workflow_viz.graph_source.parse_failures import (
    MissingMaxRounds,
    MissingMeta,
    NoAgentCalls,
    ParseFailure,
    ParseFailureReport,
    SourceLocation,
    UnsupportedConditional,
    UnsupportedControlFlow,
    UnsupportedLabel,
    UnsupportedParallel,
    UnsupportedTerminal,
)

_TERMINAL_IDS = {"DONE": "done", "BLOCKED": "blocked", "NEEDS_CONTEXT": "needs-context"}
_TERMINAL_LABELS = {"done": "Done", "blocked": "Blocked", "needs-context": "Needs Context"}

_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_STATIC_NAME = rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})*"
_TEMPLATE_LABEL = re.compile(rf"^\$\{{{_STATIC_NAME}\}}/([^/:]+):r\$\{{{_STATIC_NAME}\}}$")
_META_NAME = re.compile(r"export\s+const\s+meta\s*=\s*\{[^}]*?\bname\s*:\s*['\"]([^'\"]*)['\"]")
_AGENT_CALL = re.compile(r"\bagent\s*\(")
_RETURN_LITERAL = re.compile(r"\breturn\s+(['\"])([^'\"]*)\1")
_RETURN_EXPRESSION = re.compile(r"\breturn\b(?!\s*['\"])")
_MAX_ROUNDS_INT = re.compile(r"^\s*const\s+MAX_ROUNDS\s*=\s*(\d+)\s*;?\s*$")
_MAX_ROUNDS_ANY = re.compile(r"^\s*const\s+MAX_ROUNDS\s*=")
_EXHAUSTION = re.compile(
    r"if\s*\(\s*round\s*>=\s*MAX_ROUNDS\s*\)\s*\{\s*return\s*['\"]([A-Z_]+)['\"]"
    r"|if\s*\(\s*round\s*>=\s*MAX_ROUNDS\s*\)\s*return\s*['\"]([A-Z_]+)['\"]"
)


@dataclass
class _AgentSite:
    index: int
    line: int
    node_id: str
    stage: str | None
    step_key: str | None


@dataclass
class _ReturnEvent:
    line: int
    literal: str
    agent: int | None


@dataclass
class _ContinueEvent:
    line: int
    reentry: int | None
    agent: int | None


@dataclass(frozen=True)
class WorkflowSource:
    """The workflow's JavaScript source plus its path; carries the parse behaviour."""

    source_text: str
    source_path: str | Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", Path(self.source_path))
        object.__setattr__(self, "_lines", self.source_text.splitlines())
        starts = [0]
        for match in re.finditer("\n", self.source_text):
            starts.append(match.end())
        object.__setattr__(self, "_line_starts", starts)

    def parse(self) -> Graph | ParseFailureReport:
        """Parse into a `Graph` or collect every failure into a `ParseFailureReport`."""
        failures: list[ParseFailure] = []

        name, meta_failure = self._extract_meta()
        if meta_failure is not None:
            failures.append(meta_failure)

        max_rounds, max_rounds_line, mr_failure = self._extract_max_rounds()
        if mr_failure is not None:
            failures.append(mr_failure)

        sites, label_failures, call_count = self._extract_agents()
        failures.extend(label_failures)
        if call_count == 0:
            failures.append(self._failure(NoAgentCalls, 1, self._line(1)))

        agent_by_line = {site.line: site.index for site in sites}
        scan = self._scan(agent_by_line)
        failures.extend(scan.failures)

        exhaustion = scan.exhaustion
        has_loop_back = any(event.reentry is not None for event in scan.continues)
        if max_rounds is None and (exhaustion is not None or has_loop_back):
            if exhaustion is not None:
                where = exhaustion[0]
            else:
                where = next(event.line for event in scan.continues if event.reentry is not None)
            failures.append(self._failure(MissingMaxRounds, where, self._line(where)))
        if max_rounds is not None and exhaustion is None:
            where = max_rounds_line or 1
            failures.append(self._failure(UnsupportedTerminal, where, self._line(where)))

        if failures:
            return ParseFailureReport.collect(failures)
        return self._build_graph(name, max_rounds, exhaustion, sites, scan)

    # -- extraction ---------------------------------------------------------

    def _extract_meta(self) -> tuple[str | None, ParseFailure | None]:
        match = _META_NAME.search(self.source_text)
        if match is None:
            return None, self._failure(MissingMeta, 1, self._line(1))
        name = match.group(1)
        if not name:
            return None, self._failure(MissingMeta, 1, self._line(1))
        return name, None

    def _extract_max_rounds(self) -> tuple[int | None, int | None, ParseFailure | None]:
        lines = self.source_text.splitlines()
        for index, line in enumerate(lines, start=1):
            match = _MAX_ROUNDS_INT.match(line)
            if match:
                return int(match.group(1)), index, None
            if _MAX_ROUNDS_ANY.match(line):
                return None, index, self._failure(MissingMaxRounds, index, line)
        return None, None, None

    def _extract_agents(self) -> tuple[list[_AgentSite], list[ParseFailure], int]:
        source = self.source_text
        failures: list[ParseFailure] = []
        raw: list[tuple[int, str | None, str | None, int]] = []
        call_count = 0
        for match in _AGENT_CALL.finditer(source):
            start = match.start()
            open_index = match.end() - 1
            close = _match_paren(source, open_index)
            if close == -1:
                continue
            call_count += 1
            call_text = source[start : close + 1]
            line = self._line_of(start)
            kind, value, label_offset = _extract_label(call_text)
            label_line = line + call_text[:label_offset].count("\n")
            context = self._line(label_line)
            if kind is None:
                failures.append(self._failure(UnsupportedLabel, label_line, context))
                continue
            raw.append((line, kind, value, label_line))
        sites = self._classify(raw, failures)
        return sites, failures, call_count

    def _classify(
        self, raw: list[tuple[int, str | None, str | None, int]], failures: list[ParseFailure]
    ) -> list[_AgentSite]:
        sites: list[_AgentSite] = []
        used: set[str] = set(_TERMINAL_IDS.values())
        counters: dict[str, int] = {}
        for index, (line, kind, value, label_line) in enumerate(raw):
            if kind == "literal":
                step_key = value or ""
                node_id = _unique(step_key.split("/", 1)[0], used, counters)
                sites.append(_AgentSite(index, line, node_id, None, step_key))
            else:  # template
                match = _TEMPLATE_LABEL.match(value or "")
                if match is None:
                    context = self._line(label_line)
                    failures.append(self._failure(UnsupportedLabel, label_line, context))
                    continue
                stage = match.group(1)
                node_id = _unique(stage, used, counters)
                sites.append(_AgentSite(index, line, node_id, stage, None))
        return sites

    # -- control-flow scan ---------------------------------------------------

    def _scan(self, agent_by_line: dict[int, int]) -> "_ScanResult":
        lines = self._lines
        frames: list[dict] = []
        returns: list[_ReturnEvent] = []
        continues: list[_ContinueEvent] = []
        failures: list[ParseFailure] = []
        exhaustion: tuple[int, str] | None = None
        current_agent: int | None = None
        depth = 0

        exhaustion_match = _EXHAUSTION.search(self.source_text)
        if exhaustion_match is not None:
            literal = exhaustion_match.group(1) or exhaustion_match.group(2)
            return_offset = exhaustion_match.start() + exhaustion_match.group(0).rfind("return")
            exhaustion_line = self._line_of(return_offset)
            if literal in _TERMINAL_IDS:
                exhaustion = (exhaustion_line, literal)
            else:
                context = self._line(exhaustion_line)
                failures.append(self._failure(UnsupportedTerminal, exhaustion_line, context))

        for index, line in enumerate(lines, start=1):
            if index in agent_by_line:
                current_agent = agent_by_line[index]
                for frame in reversed(frames):
                    if frame["kind"] == "loop" and frame["first_agent"] is None:
                        frame["first_agent"] = current_agent
                        break
                for frame in reversed(frames):
                    if frame["kind"] in ("if", "else"):
                        frame["has_agent"] = True
                        break

            kind = _line_kind(line)
            opens, closes = _count_braces(line)
            depth_before = depth

            if kind in ("loop-for", "loop-while"):
                frames.append({"kind": "loop", "depth": depth_before, "first_agent": None})
            elif kind == "loop-do":
                failures.append(self._failure(UnsupportedControlFlow, index, line))
                frames.append({"kind": "loop", "depth": depth_before, "first_agent": None})
            elif kind == "if":
                frames.append({"kind": "if", "depth": depth_before, "has_agent": False})
            elif kind == "function":
                frames.append({"kind": "function", "depth": depth_before})
            elif kind == "else-open" and frames and frames[-1]["kind"] == "if":
                had_agent = frames.pop()["has_agent"]
                # The leading `}` on `} else {` closes the if, so the else body opens one
                # level shallower than the line's starting depth.
                frames.append(
                    {
                        "kind": "else",
                        "depth": depth_before - closes,
                        "has_agent": False,
                        "pair_had_agent": had_agent,
                    }
                )

            if kind not in ("loop-for", "loop-while", "loop-do") and frames:
                # detect return / continue on this line
                return_match = _RETURN_LITERAL.search(line)
                if return_match is not None and not _is_exhaustion_line(index, exhaustion):
                    literal = return_match.group(2)
                    if literal not in _TERMINAL_IDS:
                        failures.append(self._failure(UnsupportedTerminal, index, line))
                    returns.append(_ReturnEvent(index, literal, current_agent))
                elif _RETURN_EXPRESSION.search(line) and not _is_exhaustion_line(index, exhaustion):
                    failures.append(self._failure(UnsupportedTerminal, index, line))
                if re.search(r"\bcontinue\b", line):
                    loop = _innermost_loop(frames)
                    reentry = loop["first_agent"] if loop is not None else None
                    if reentry is None:
                        failures.append(self._failure(UnsupportedControlFlow, index, line))
                    continues.append(_ContinueEvent(index, reentry, current_agent))

            depth += opens - closes
            while frames and depth <= frames[-1]["depth"]:
                frame = frames.pop()
                if frame["kind"] == "else" and frame.get("pair_had_agent") and frame["has_agent"]:
                    failures.append(self._failure(UnsupportedConditional, index, line))

        # UnsupportedParallel check (separate, targeted).
        failures.extend(self._parallel_failures())

        return _ScanResult(
            returns=returns,
            continues=continues,
            failures=failures,
            exhaustion=exhaustion,
        )

    def _parallel_failures(self) -> list[ParseFailure]:
        source = self.source_text
        failures: list[ParseFailure] = []
        for match in re.finditer(r"\bPromise\.all\s*\(", source):
            bracket = source.find("[", match.end())
            if bracket == -1:
                continue
            close = _match_bracket(source, bracket)
            if close == -1:
                continue
            body = source[bracket + 1 : close]
            for member in _split_top_level(body, ","):
                if member.strip() and not re.match(r"\s*agent\s*\(", member):
                    line = self._line_of(bracket)
                    failures.append(self._failure(UnsupportedParallel, line, self._line(line)))
                    break
        return failures

    # -- graph construction ---------------------------------------------------

    def _build_graph(
        self,
        name: str | None,
        max_rounds: int | None,
        exhaustion: tuple[int, str] | None,
        sites: list[_AgentSite],
        scan: "_ScanResult",
    ) -> Graph:
        ids = [site.node_id for site in sites]
        terminal_ids: set[str] = set()
        terminal_ids.add("done")

        diverts: list[tuple[int, int, str]] = []
        for event in scan.returns:
            if event.agent is None or event.literal == "DONE":
                continue
            terminal = _TERMINAL_IDS.get(event.literal)
            if terminal is None:
                continue
            terminal_ids.add(terminal)
            diverts.append((event.line, event.agent, terminal))
        for event in scan.continues:
            if event.agent is None or event.reentry is None:
                continue
            diverts.append((event.line, event.agent, ids[event.reentry]))
        if max_rounds is not None and exhaustion is not None:
            terminal_ids.add(_TERMINAL_IDS.get(exhaustion[1], "blocked"))
        on_fail: dict[int, str] = {}
        for _line, agent, target in sorted(diverts):
            on_fail.setdefault(agent, target)

        nodes: list[Node] = []
        for site in sites:
            nodes.append(
                Node(
                    id=site.node_id,
                    label=_display_label(site.node_id),
                    stage=site.stage,
                    step_key=site.step_key,
                    on_pass=None,
                    on_fail=None,
                )
            )
        # Assign on_pass: next site in source order; the last site routes to done.
        for index in range(len(sites)):
            target = ids[index + 1] if index + 1 < len(ids) else "done"
            nodes[index] = _replace_node(nodes[index], on_pass=target, on_fail=on_fail.get(index))

        for terminal_id in sorted(terminal_ids):
            nodes.append(
                Node(
                    id=terminal_id,
                    label=_TERMINAL_LABELS[terminal_id],
                    terminal=True,
                )
            )

        on_rounds_exhausted = _TERMINAL_IDS.get(exhaustion[1], "blocked") if exhaustion else None
        return Graph(
            name=name or "workflow",
            entry=ids[0],
            nodes=tuple(nodes),
            max_rounds=max_rounds,
            on_rounds_exhausted=on_rounds_exhausted,
        )

    # -- helpers ---------------------------------------------------------------

    def _failure(self, failure_type: type[ParseFailure], line: int, context: str) -> ParseFailure:
        return failure_type(SourceLocation(str(self.source_path), line), context)

    def _line(self, line: int) -> str:
        if 1 <= line <= len(self._lines):
            return self._lines[line - 1]
        return ""

    def _line_of(self, offset: int) -> int:
        return bisect.bisect_right(self._line_starts, offset)


@dataclass
class _ScanResult:
    returns: list[_ReturnEvent]
    continues: list[_ContinueEvent]
    failures: list[ParseFailure]
    exhaustion: tuple[int, str] | None


def _line_kind(line: str) -> str | None:
    stripped = line.lstrip()
    if stripped.startswith("} else {") or stripped == "} else":
        return "else-open"
    if stripped.startswith("}"):
        return "close"
    if re.match(r"for\s*\(", stripped):
        return "loop-for"
    if re.match(r"while\s*\(", stripped):
        return "loop-while"
    if re.match(r"do\s*\{", stripped):
        return "loop-do"
    if re.match(r"if\s*\(", stripped):
        return "if"
    if re.match(r"(?:export\s+)?(?:async\s+)?function\b", stripped):
        return "function"
    return None


def _count_braces(line: str) -> tuple[int, int]:
    opens = closes = 0
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            break
        elif char == "{":
            opens += 1
        elif char == "}":
            closes += 1
        index += 1
    return opens, closes


def _innermost_loop(frames: list[dict]) -> dict | None:
    for frame in reversed(frames):
        if frame["kind"] == "loop":
            return frame
    return None


def _match_paren(source: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    index = open_index
    while index < len(source):
        char = source[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _match_bracket(source: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    index = open_index
    while index < len(source):
        char = source[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _extract_label(call_text: str) -> tuple[str | None, str | None, int]:
    match = re.search(r"\blabel\s*:", call_text)
    if match is None:
        return None, None, 0
    position = match.end()
    while position < len(call_text) and call_text[position].isspace():
        position += 1
    if position >= len(call_text):
        return None, None, match.start()
    if call_text[position] in "'\"":
        quote = call_text[position]
        end = call_text.find(quote, position + 1)
        if end == -1:
            return None, None, match.start()
        return "literal", call_text[position + 1 : end], match.start()
    if call_text[position] == "`":
        end = call_text.find("`", position + 1)
        if end == -1:
            return None, None, match.start()
        return "template", call_text[position + 1 : end], match.start()
    return None, None, match.start()


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    current: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            current.append(char)
            if char == "\\":
                index += 1
                if index < len(text):
                    current.append(text[index])
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
            current.append(char)
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            depth -= 1
            current.append(char)
        elif char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _is_exhaustion_line(line: int, exhaustion: tuple[int, str] | None) -> bool:
    return exhaustion is not None and exhaustion[0] == line


def _unique(base: str, used: set[str], counters: dict[str, int]) -> str:
    candidate = base or "node"
    if candidate not in used:
        used.add(candidate)
        counters[base] = 2
        return candidate
    suffix = counters.get(base, 2)
    candidate = f"{base}-{suffix}"
    while candidate in used:
        suffix += 1
        candidate = f"{base}-{suffix}"
    counters[base] = suffix + 1
    used.add(candidate)
    return candidate


def _display_label(node_id: str) -> str:
    return node_id.replace("-", " ").title()


def _replace_node(node: Node, *, on_pass: str, on_fail: str | None) -> Node:
    return Node(
        id=node.id,
        label=node.label,
        stage=node.stage,
        terminal=node.terminal,
        on_pass=on_pass,
        on_fail=on_fail,
        step_key=node.step_key,
    )
