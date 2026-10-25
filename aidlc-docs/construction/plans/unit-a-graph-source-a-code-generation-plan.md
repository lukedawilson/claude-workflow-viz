# Unit A (graph source) — Code Generation Plan

Single source of truth for Unit A code generation. Brownfield: existing files are
modified in place; new files land in the existing structure.

## Unit Context

- **Unit**: A — graph source (parser + failure report + fallback prompt + to_yaml)
- **Stories**: FR3 (dynamic graph at invoke), FR4 (strict subset, named failures),
  FR5 (agent fallback), FR7 (workflow-agnostic); NFR-A1/A2 decisions; UE-A1/A2; FD1-FD7
- **Dependencies on other units**: none (A is the root of A→B→C→D). Only existing
  modules (graph/, PyYAML).
- **Owned concepts**: WorkflowSource, ParseFailure family, ParseFailureReport,
  Graph.to_yaml, /viz template content, parse debug log.
- **Contracts out**: `parse() -> Graph | ParseFailureReport` (D5 shape), R14 round-trip,
  build_fallback_prompt → Unit C consumption.

## TDD note

Repo AGENTS.md mandates TDD. Each generation step below therefore writes failing tests
first (red), then implementation (green), then refactors. The "Unit Testing" steps add
the depth beyond the red-green driver: fixture corpus, pathological bound, Hypothesis
properties.

## Steps

### Business Logic Generation

- [ ] Step 1: `graph_source/parse_failures.py` (new) — ParseFailure family (6 classes,
      R15: code/message/location/context), ParseFailureReport (R3 collect-all, dedupe by
      (code,location,context), source order, summarise(), build_fallback_prompt() per
      FD5 fold), viz_command template content constant (UE3-B) + debug-log append helper
      (NRA1-B: ~1 MiB cap, exception-guarded, state-dir). Red: tests/test_parse_failures.py.
- [ ] Step 2: `graph_source/parser.py` (new) — WorkflowSource (UE-A1: executable subset
      spec), parse() implementing R1-R17 (R2 never-guess, R4 label shape, R5 default
      step_pattern, R6 entry, R7 MAX_ROUNDS, R8 loop-backs, R9 terminals, R10
      conditionals FD2-hybrid, R11 parallel, R12 Graph.load-valid, R13 lowercase ids,
      R17 deterministic; linear-time patterns per NFR-A1/A2). Red: tests/test_parser.py.
- [ ] Step 3: `graph/graph.py` — add `to_yaml()` in place (R14 round-trip, DOMAIN-08
      entity-owned serialization). Red: tests/test_graph_to_yaml.py.
- [ ] Step 4: `pyproject.toml` — add `src/claude_workflow_viz/graph_source` to hatchling
      packages list. Red: wheel-build check in the test step.

### Business Logic Unit Testing

- [ ] Step 5: Fixture corpus — copy implement.js, rca.js, cross-repo-check.js into
      `tests/fixtures/workflows/` with a provenance README; implement.js → expected
      graph assertions (nodes, entry, max_rounds, on_rounds_exhausted, terminals);
      rca.js → UnsupportedLabel on the dynamic-depth construct; cross-repo-check.js →
      trivial graph.
- [ ] Step 6: Each failure class triggered once (6 focused fixtures); no-partial-graph
      assertion; determinism test (parse twice, equal values).
- [ ] Step 7: Pathological-fixture bounded-time test (NFR-A2 residual risk; generous
      bound, e.g. < 2s wall clock for a megabyte of adversarial braces/backticks).
- [ ] Step 8: Hypothesis properties (PBT): to_yaml round-trip over generated graphs;
      parser invariants (every node reachable from entry, every edge target exists,
      max_rounds pairing); determinism.

### Business Logic Summary

- [ ] Step 9: `aidlc-docs/construction/unit-a-graph-source/code/` — generation summary
      (files created/modified, rules coverage, contract check results).

### API Layer / Repository Layer / Frontend / Database

- [ ] Step 10: Marked N/A — Unit A has no HTTP surface (DOMAIN-08: no repository
      abstractions), no frontend (FR9 → Unit D), no data models.

### Documentation Generation

- [ ] Step 11: README — add the parse-subset table (UE-A1: derives from parser code;
      keeps FR8 smoke test green).
- [ ] Step 12: Fixture provenance note (example workflow fixtures
      authored for this repo — see tests/fixtures/workflows/README.md).

### Deployment Artifacts Generation

- [ ] Step 13: N/A — packaging verified via Step 4's wheel check; no deployment
      artifacts for this unit.

## Out of scope (other units)

- Dispatcher branches, bootstrap spawn, /shutdown, stop_server (Unit B)
- Installer, cli install, template deployment (Unit C)
- Skip visual (Unit D, FR9)
- README invoke/endpoint + installer sections (Units B and C)
