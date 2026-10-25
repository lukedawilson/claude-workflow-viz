# Code Quality Assessment

## Test Coverage

- **Overall**: Good. The suite is contract-first and module-aligned; nearly everything has a
  dedicated test module.
- **Unit Tests**: 476 Python test functions across 15 modules (measured 2026-10-24:
  475 passed, 1 failed) plus 87 passing Node tests for the pure JS core
  (`tests/js/viz-core.test.mjs`). Coverage is behavioural rather than line-measured —
  every contract in the README (token policy, body caps, host allowlist, connection file
  lifecycle, SSE exactly-once delivery, graph validation, status rules) has a test.
- **Integration Tests**: Smoke tests spin up the real server on an ephemeral port
  (`test_smoke.py`, `test_serve_shutdown.py`, `test_static_ui.py`) and exercise
  `/ingest`, `/stream`, `/graph` and the static routes end to end. The JS core is exercised
  under Node with no browser.

## Code Quality Indicators

- **Linting**: Configured — ruff with `E, F, W, I, B, UP, SIM, N` rules, line length 100;
  also a `.markdownlint-cli2.yaml` for the AI-DLC rule tree.
- **Code Style**: Consistent. Typed union returns (`X | XError`), frozen dataclasses,
  StrEnums, docstrings on every module explaining the contract and the invariants.
- **Documentation**: Good. Every module carries a contract-level docstring; README documents
  subcommands, endpoints, run state limits, graph configuration, status rules and the
  development loop; `docs/plan.md` records the original phased design.

## Technical Debt

- **One failing test — README/smoke-test drift** (`tests/test_smoke.py:164`,
  `test_readme_documents_the_serve_graph_flow_and_is_not_stale`): the test expects the
  headings `## Server endpoints`, `## Graph configuration`, `### Node status rules`,
  `## Web UI`, `## Development`, but the README was restructured and now nests those
  sections at different levels (`### Server endpoints` under `## Usage`, `## Development
  environment` instead of `## Development`) and has no `### Node status rules` or `## Web
  UI` headings. Either the test's heading list or the README's structure is stale; the two
  disagree about what the README must document. Small, but it breaks the suite.
- **No transcript-tail adapter** — `events.py` and `docs/plan.md` both describe a second
  adapter (tail `agent-*.jsonl` transcripts) as the fallback if per-agent hooks had not
  carried step identity. The hook adapter won (the probe showed it works), so the
  transcript-tail adapter is documented but not built; `EventSink` is defined in
  anticipation of it. Not debt, but a documented gap between plan and code.
- **`result` deep-copy cost** — `RunState` deep-copies every step `result` on snapshot and
  on apply; bounded in size (16 KiB compact JSON) but quadratic in pathological
  snapshot-heavy usage. Currently acceptable; worth noting if snapshot frequency grows.

## Patterns and Anti-patterns

- **Good Patterns**:
  - Validation that never raises — typed error unions keep the HTTP layer and the hook path
    exception-free (a hard requirement of the hook contract).
  - Fail-silent hook: `contextlib.suppress(BaseException)`, exit 0, no stdout/stderr writes.
  - Bounded everything: 64 KiB body, 16 KiB results, 1 MiB journal, 64 sessions LRU,
    5000 steps, 100 statuses, 1000 events — hostile input cannot exhaust memory.
  - Exactly-once SSE delivery via subscribe-with-snapshot under one lock.
  - Security baseline respected: loopback-only bind, constant-time token compare, 0600
    atomic connection file, Host allowlist, CSP/nosniff on static assets, empty
    ProxyHandler so the token never leaves the machine.
  - Shared data, not shared code, for the verdict rules (`status_rules.json` read by both
    Python and JS).
  - Pure reducer in JS with no DOM, testable under Node.
- **Anti-patterns**: none material. The silent `log_message` override in `_Handler` hides
  request logs to protect the stream token — deliberate, documented, and correct for the
  threat model, though it costs debuggability.
