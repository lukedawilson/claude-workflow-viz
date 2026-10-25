# Code Generation Plan — Unit B (hook path / server lifecycle)

Per construction/code-generation.md. TDD red-green-refactor per step. All design inputs
in aidlc-docs/construction/unit-b-hook-path/ (functional-design/, nfr-requirements/,
nfr-design/). Mock policy: only external process/network boundaries may be stubbed;
file I/O and pure functions use real implementations.

## Steps

- [ ] Step 1 — `dashboard/connection_file.py`: `Connection.stop_server()` (POST /shutdown,
      Bearer token, 1s timeout, empty ProxyHandler; no-op when no connection file exists —
      R5/UB2); relocate `LOOPBACK_ADDRESS` from `dashboard/server.py` here (UEB1; server
      imports it from connection_file — no cycle). Update server.py import. Tests
      red-first: tests/test_connection_file_shutdown.py (real tmp state dir; a real local
      listener for the 204 path, a dead port for the timeout/no-op paths).
- [ ] Step 2 — `dashboard/server.py`: `POST /shutdown` handler (Bearer + Host allowlist,
      same checks as /ingest; 401 bad token — server keeps running; 204 success — stops and
      removes its connection file, the SIGINT sequence — R8/NRB3). Preferred-port bind:
      try 127.0.0.1:8322, EADDRINUSE → rebind port 0; `allow_reuse_address = sys.platform
      != "win32"` (NRB5). Actual bound port lands in server.json (R1). Tests:
      tests/test_server_shutdown.py.
- [ ] Step 3 — `dashboard/server.py` graph registry (NRB4=B): `{workflow_name: Graph}`
      loaded on demand from `<state>/graphs/<workflow>.viz.yaml` on the first
      `/graph?workflow=<name>` request, then held in memory; unknown name → linear graph
      for that request; no parameter → default graph (existing --graph flag or linear) —
      backward compatible (R15). Tests: tests/test_graph_registry.py (real tmp graphs dir).
- [ ] Step 4 — `invoke/bootstrap.py` Bootstrap: Connection.read → probe GET /graph
      (1s) → live = reuse (no spawn — R11/R18); else parse invoked workflow (Unit A
      WorkflowSource): Graph → write cache `<state>/graphs/<workflow>.viz.yaml` (R2/R17)
      + spawn detached `sys.executable -m claude_workflow_viz serve` (NFRB3) with
      stdout/stderr → append_debug_log (R3/NRB1); ParseFailure → append_debug_log failure
      summary + spawn without --graph (linear mode — R10); sweep before spawn (Step 5);
      wait ≤10s for server.json (R6/UB3); read token; open dashboard URL with
      `?workflow=<name>` via the platform selector (R7/R19/UEB6). Never raises past the
      dispatcher (R13). Tests: tests/test_bootstrap.py (tmp state dir; fake serve via
      subprocess to the real CLI where fast, or spawn seam for the slow paths).
- [ ] Step 5 — `invoke/_platform.py` (or similar): pure open-command selector —
      darwin → `open`, win32 → `os.startfile`, else → `xdg-open` (NFRB4); sweep helper —
      lsof -nP -ti tcp:8322 -sTCP:LISTEN, absent lsof → [] silent no-op (Windows), exclude
      own PID, match `claude-workflow-viz` on command line, cwd positive-only filter,
      SIGTERM + re-check 0.05s to 3s deadline then SIGKILL. Tests + Hypothesis property
      (selector total over platform ids; sweep idempotent/no-op without lsof).
- [ ] Step 6 — `workflow/hook_command.py` dispatcher (D10/R9): keyed on
      `hook_event_name` — Workflow PreToolUse → Bootstrap then forward; SessionEnd →
      stop_server() inline, no forward (UB1); everything else forward-only. run_hook
      silence wrapper unchanged, covers new branches (R4/R13). Tests with real payload
      fixtures (extend tests/fixtures/probe_payloads.jsonl with a Workflow PreToolUse and
      a SessionEnd payload — synthetic shapes per the existing fixture convention).
- [ ] Step 7 — `workflow/events.py` + `workflow/hook_adapter.py`: optional `workflow`
      field on Event, populated on run_start only from the PreToolUse payload (R16).
      Backward compatible: from_dict tolerates absence. Tests.
- [ ] Step 8 — `static/viz-core.js` reducer: map session→workflow from run_start;
      graph fetch passes `?workflow=`; workflow selector state (R16/R19). Extend
      tests/js/viz-core.test.mjs (Node suite).
- [ ] Step 9 — `static/app.js`: workflow selector UI + refetch on change; fetchGraph
      passes ?workflow=. No test file (covered via Node reducer tests + manual e2e).
- [ ] Step 10 — `pyproject.toml`: hatchling packages list +=
      `src/claude_workflow_viz.invoke` (wheel gotcha from planning-docs/000).
- [ ] Step 11 — `.github/workflows/ci.yml`: ubuntu job (full Python + Node suites) +
      windows-latest job exercising the win32 open-command branch + full suite
      (NFRB4=B user condition).
- [ ] Step 12 — README: invoke-time section (what happens when a workflow starts:
      parse, spawn/reuse, dashboard opens), /shutdown endpoint doc, port 8322 + fallback
      note, per-workflow graph registry note (FR8 content half).
- [ ] Step 13 — `run-demo.sh` end-to-end demo (user Q1 addition): statically parses
      a fictional workflow (the fixture `implement.js`), sweeps + spawns the server
      detached, waits for `server.json`, opens the dashboard in the browser, then
      simulates the update hooks by POSTing synthetic PreToolUse/step/SubagentStop/
      SessionEnd payloads to `/ingest` and `/shutdown` — one command proves the
      invoke-time flow without a real Claude Code session.
- [ ] Step 14 — N/A (API layer, Repository layer, Database, Frontend framework — no
      applicable new layers beyond Steps 8-9).
- [ ] Step 15 — Write `aidlc-docs/construction/unit-b-hook-path/code/summary.md`
      (implementation summary: files created/modified, rules honoured).

## Out of scope

- Unit C (installer, hook registrations, /viz command) — registrations unchanged here.
- Unit D (skipped-stage visualisation).
- Unit A behaviour changes (parser/to_yaml are consumed as-is).

## Execution vehicle

Q1 (plan approval): A — approved with one addition: the scope includes a `run-demo.sh`
end-to-end test script (Step 13). User input (verbatim): "Q1. A approved with one
addition: the scope includes a run-demo.sh that does an end-to end test (statically
parses a fictional claude workflow, spins up the server and opens the viz in browser,
and simulates the update hooks)"
Q2 (execution vehicle): B — agentic-dev-loop, user-triggered. User input (verbatim):
"Q2. B - I'll do it"

[Answer]: Q1=A (with run-demo.sh addition, Step 13); Q2=B (agentic-dev-loop, user-triggered)
