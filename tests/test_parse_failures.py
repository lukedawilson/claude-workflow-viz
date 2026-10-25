"""ParseFailure family, report collection, fallback prompt, and the debug-log helper."""

from pathlib import Path

from claude_workflow_viz.graph_source.parse_failures import (
    DEBUG_LOG_MAX_BYTES,
    DEBUG_LOG_NAME,
    VIZ_COMMAND_TEMPLATE,
    MissingMaxRounds,
    MissingMeta,
    NoAgentCalls,
    ParseFailureReport,
    SourceLocation,
    UnsupportedConditional,
    UnsupportedControlFlow,
    UnsupportedLabel,
    UnsupportedParallel,
    UnsupportedTerminal,
    append_debug_log,
)


def _at(line=3) -> SourceLocation:
    return SourceLocation("workflow.js", line)


def test_each_failure_class_carries_a_stable_code_and_context():
    cases = [
        (MissingMeta(_at(1), ""), "missing-meta"),
        (NoAgentCalls(_at(1), ""), "no-agent-calls"),
        (UnsupportedLabel(_at(), "label: r${round}/x"), "unsupported-label"),
        (MissingMaxRounds(_at(), "continue;"), "missing-max-rounds"),
        (UnsupportedControlFlow(_at(), "do {"), "unsupported-control-flow"),
        (UnsupportedTerminal(_at(), "return 'MAYBE';"), "unsupported-terminal"),
        (UnsupportedConditional(_at(), "} else {"), "unsupported-conditional"),
        (UnsupportedParallel(_at(), "Promise.all([a, b])"), "unsupported-parallel"),
    ]
    for failure, code in cases:
        assert failure.code == code
        assert failure.message
        assert str(failure.location) == f"workflow.js:{failure.location.line}"
        assert isinstance(failure.context, str)


def test_report_collapses_identical_triples_and_preserves_source_order():
    first = UnsupportedLabel(_at(3), "label: r${round}/x")
    duplicate = UnsupportedLabel(_at(3), "label: r${round}/x")
    second = MissingMaxRounds(_at(7), "continue;")
    report = ParseFailureReport.collect([first, duplicate, second])
    assert report.failures == (first, second)


def test_summarise_is_one_line_per_failure():
    report = ParseFailureReport.collect([UnsupportedLabel(_at(3), "label: r${round}/x")])
    summary = report.summarise()
    assert summary == "workflow.js:3: unsupported-label: " + (
        "agent label is not a string literal or a <slice>/<stage>:r<round> template literal"
    )


def test_build_fallback_prompt_carries_the_contract():
    report = ParseFailureReport.collect(
        [UnsupportedLabel(_at(3), "label: r${round}/x"), MissingMaxRounds(_at(7), "continue;")]
    )
    prompt = report.build_fallback_prompt(Path("repo/.claude/workflows/implement.js"), Path(".viz"))
    assert "implement.js" in prompt
    assert ".viz/implement.viz.yaml" in prompt
    assert "Graph.load" in prompt
    assert "unsupported-label" in prompt
    assert "missing-max-rounds" in prompt
    assert "label: r${round}/x" in prompt


def test_viz_command_template_names_the_schema_keys():
    for key in ("name", "entry", "step_pattern", "nodes", "on_pass", "Graph.load"):
        assert key in VIZ_COMMAND_TEMPLATE


def test_append_debug_log_writes_to_the_state_dir(tmp_path):
    append_debug_log("boom", tmp_path)
    log = (tmp_path / DEBUG_LOG_NAME).read_text(encoding="utf-8")
    assert "boom" in log


def test_append_debug_log_caps_at_one_mib_with_oldest_first(tmp_path):
    append_debug_log("first line\n", tmp_path)
    big = "x" * (DEBUG_LOG_MAX_BYTES + 100)
    append_debug_log(big, tmp_path)
    log = (tmp_path / DEBUG_LOG_NAME).read_text(encoding="utf-8")
    assert len(log.encode("utf-8")) <= DEBUG_LOG_MAX_BYTES
    assert "first line" not in log


def test_append_debug_log_never_raises_when_the_state_dir_cannot_be_created(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    append_debug_log("ok", blocker / "sub")
