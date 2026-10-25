"""Typed parse failures and the collected report for one graph-source parse attempt.

The parser never guesses (R2): every construct outside the supported subset becomes a named
`ParseFailure`, and one pass collects all of them into a `ParseFailureReport` (R3, FD1). Each
failure carries a machine `code`, a human `message`, a `location` (file:line) and the offending
`context` line (R15). Codes are internal until Unit C ships (UE-A2).

The report owns its projections (FD5 fold): `summarise()` for logs and the linear-mode warning,
and `build_fallback_prompt()` for the /viz agent. The /viz command template and the debug-log
append helper live here too, so the failure codes, the agent prompt, and the template content
co-evolve in one file (Decision 5).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEBUG_LOG_NAME = "debug.log"
DEBUG_LOG_MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class SourceLocation:
    """A source position, carried as `path:line` for failure reports."""

    path: str
    line: int

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class ParseFailure:
    """One named, actionable parse failure (R15)."""

    code: str
    message: str
    location: SourceLocation
    context: str


class MissingMeta(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "missing-meta",
            "no export const meta = { name: ... } with a name was found",
            location,
            context,
        )


class NoAgentCalls(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "no-agent-calls",
            "no agent(...) call site was found; a graph needs at least one node",
            location,
            context,
        )


class UnsupportedLabel(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "unsupported-label",
            "agent label is not a string literal or a <slice>/<stage>:r<round> template literal",
            location,
            context,
        )


class MissingMaxRounds(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "missing-max-rounds",
            "a retry loop or exhaustion return needs a const MAX_ROUNDS = <int> declaration",
            location,
            context,
        )


class UnsupportedControlFlow(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "unsupported-control-flow",
            "control flow the subset does not model (only while/for + continue loop-backs)",
            location,
            context,
        )


class UnsupportedTerminal(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "unsupported-terminal",
            "return outcome is not a recognised terminal or MAX_ROUNDS has no exhaustion return",
            location,
            context,
        )


class UnsupportedConditional(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "unsupported-conditional",
            "an if/else has agent calls on both branches; only a guarded (else-less) agent "
            "call is modelled",
            location,
            context,
        )


class UnsupportedParallel(ParseFailure):
    def __init__(self, location: SourceLocation, context: str) -> None:
        super().__init__(
            "unsupported-parallel",
            "a Promise.all group has a member that is not a statically known agent(...) call",
            location,
            context,
        )


VIZ_DIR_PLACEHOLDER = "{viz_dir}"


VIZ_COMMAND_TEMPLATE = """Generate a hand-authored `.viz.yaml` graph config for a workflow whose
static parse failed. Read the workflow source at the path given in the task, then write a
`<workflow>.viz.yaml` into the `{viz_dir}` directory that `Graph.load` accepts with zero errors.

The supported schema (same keys as a hand-authored file):

    name: <string>
    entry: <node id>
    max_rounds: <int>            # optional; on_rounds_exhausted required when set
    on_rounds_exhausted: <node id>
    step_pattern: <regex>        # optional; default <slice>/<stage>:r<round>
    nodes:
      - {id: ..., label: ..., stage: <stage> | step_key: <label>, terminal: false,
         on_pass: <node id>, on_fail: <node id>}

Map each agent call site to a node: a literal label to a `step_key` node (matched on the whole
label), a `${slice}/<stage>:r${round}` template label to a `stage` node. Chain nodes with
`on_pass`; early `return` outcomes become terminal nodes (`done`, `blocked`, `needs-context`).
The written file must load under `Graph.load` with zero errors.
"""


@dataclass(frozen=True)
class ParseFailureReport:
    """Every failure of one parse attempt, deduplicated and in source order (R3, FD1)."""

    failures: tuple[ParseFailure, ...]

    @classmethod
    def collect(cls, failures: Iterable[ParseFailure]) -> "ParseFailureReport":
        """Collapse identical (code, location, context) triples to one, keeping source order."""
        seen: set[tuple[str, str, int, str]] = set()
        ordered: list[ParseFailure] = []
        for failure in failures:
            key = (
                failure.code,
                failure.location.path,
                failure.location.line,
                failure.context,
            )
            if key not in seen:
                seen.add(key)
                ordered.append(failure)
        return cls(tuple(ordered))

    def summarise(self) -> str:
        """One line per failure, for logs and the linear-mode warning."""
        return "\n".join(
            f"{failure.location}: {failure.code}: {failure.message}" for failure in self.failures
        )

    def build_fallback_prompt(self, workflow_path: Path, viz_dir: Path) -> str:
        """Pure derivation of the /viz agent prompt from the collected failures (FR5)."""
        target = viz_dir / f"{workflow_path.stem}.viz.yaml"
        lines = [
            f"A static parse of {workflow_path} failed; the workflow uses constructs outside "
            "the supported subset. Write a hand-authored viz.yaml the visualiser can load.",
            "",
            "Failures:",
        ]
        for failure in self.failures:
            lines.append(f"- {failure.location}: {failure.code}: {failure.message}")
            if failure.context:
                lines.append(f"    context: {failure.context.rstrip()}")
        lines += [
            "",
            f"Target: {target}",
            "",
            "Schema (same keys as a hand-authored viz.yaml):",
            "  name, entry, max_rounds (optional), on_rounds_exhausted, step_pattern (optional),",
            "  nodes[] with id, label, one of stage or step_key, terminal, on_pass, on_fail.",
            "",
            "The written yaml must load under Graph.load with zero errors.",
        ]
        return "\n".join(lines)


def _truncate_oldest(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[-max_bytes:].decode("utf-8", errors="ignore")


def append_debug_log(text: str, state_dir: Path) -> None:
    """Append `text` to the state-dir debug log, best-effort and never raising (NRA1-B).

    The log is capped at ~1 MiB with oldest-first truncation; an internal-bug trace must never
    become a hook failure, so every write is exception-guarded.
    """
    try:
        entry = f"--- {datetime.now(UTC).isoformat()} ---\n{text.rstrip()}\n"
        path = state_dir / DEBUG_LOG_NAME
        if not state_dir.exists():
            state_dir.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        combined = existing + entry
        if len(combined.encode("utf-8")) > DEBUG_LOG_MAX_BYTES:
            combined = _truncate_oldest(combined, DEBUG_LOG_MAX_BYTES)
        path.write_text(combined, encoding="utf-8")
    except BaseException:
        return


__all__ = [
    "SourceLocation",
    "ParseFailure",
    "MissingMeta",
    "NoAgentCalls",
    "UnsupportedLabel",
    "MissingMaxRounds",
    "UnsupportedControlFlow",
    "UnsupportedTerminal",
    "UnsupportedConditional",
    "UnsupportedParallel",
    "ParseFailureReport",
    "VIZ_COMMAND_TEMPLATE",
    "VIZ_DIR_PLACEHOLDER",
    "append_debug_log",
    "DEBUG_LOG_NAME",
    "DEBUG_LOG_MAX_BYTES",
]
