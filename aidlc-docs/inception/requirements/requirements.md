# Requirements

## Intent Analysis Summary

- **User request**: "Start AI-DLC on this repo, with reverse-engineering / This is currently
  a proof-of-concept for a visualisation extension for Claude Dynamic Workflows, modelled
  on https://pypi.org/project/agentic-dev-loop/ (I'm the author of that tool)" — refined
  during analysis to unit-1: replace hand-rolled graph configuration with automatic graph
  generation, and bootstrap the installation into any repo with Claude Dynamic Workflows.
  (Verbatim unit-1 direction: "unit-1 is how to generate the graph and generally bootstrap
  this installation nicely into a repo with claude dynamic workflows. The hooks approach is
  good, the general architecture is good")
- **Request type**: Enhancement + New Feature
- **Scope estimate**: Multiple Components
- **Complexity estimate**: Moderate
- **Depth**: Standard

## Unit 1 Scope

Unit-1 delivers the bootstrap story and dynamic graph generation for claude-workflow-viz.
All later units (visual polish, adapter hardening, etc.) are out of scope here.

## Functional Requirements

### FR1 — Installer (install-time bootstrap)
- FR1.1 Install/verify the tool (pipx install, verify the hook binary works).
- FR1.2 Write the four hook entries into the target repo's `.claude/settings.local.json`:
  PreToolUse (matcher Workflow), PostToolUse (matcher Workflow), SubagentStart,
  SubagentStop — each `{"type":"command","command":"claude-workflow-viz hook","async":true}`.
- FR1.3 Write the fifth hook: SessionEnd, command that stops the server.
- FR1.4 Idempotent: re-running the installer must not duplicate hook entries or corrupt
  settings.
- FR1.5 Fallback viz-yaml location is a choice made at install time (flag or prompt):
  `.claude-local/viz/` (default, local-only) or `.claude/viz/` (committed, shared).

### FR2 — Entry point
- FR2.1 A Claude Code command (e.g. `.claude/commands/viz.md`) in the target repo is the
  bootstrap entry point; it runs inside the repo so agent context is available for the
  fallback path.

### FR3 — Dynamic graph generation (invoke-time)
- FR3.1 No hand-authored graph yaml is required for any parseable workflow.
- FR3.2 When a workflow is invoked, the PreToolUse hook statically parses the invoked
  workflow's JS (payload carries workflow name + cwd) and generates the graph before the
  first step event (PreToolUse fires before subagents).
- FR3.3 Re-parses on every invocation — fully dynamic, nothing persisted for the parseable
  case.
- FR3.4 The graph captures all gates and loops: sequence edges, on_pass/on_fail routing,
  loop-backs (retry edges), parallel groups, conditional nodes, terminal outcomes.

### FR4 — Strict static analysis subset (never guesses)
- FR4.1 Parseable subset: `meta` export; `agent()` call sites with literal labels or
  template literals whose non-dynamic segments are literals; `const MAX_ROUNDS`-style
  round caps; while/for loops with continue/break → loop-backs; early returns with literal
  outcome/verdict → terminal edges; if-guarded `agent()` → conditional nodes; Promise.all
  groups → parallel.
- FR4.2 Anything outside the subset produces a NAMED parse failure (specific reason and
  location) — never a guessed graph.
- FR4.3 On named parse failure, fall back to the agent-generated path (FR5).

### FR5 — Agent-generated fallback
- FR5.1 When static parsing fails, a Claude Code agent reads the workflow JS and writes a
  `<workflow>.viz.yaml` in the existing yaml schema.
- FR5.2 The generated yaml is validated by the existing strict `Graph.load()` and served
  unchanged — no new schema, no deviation from the current yaml format.
- FR5.3 Agent fallback only runs where an agent exists (installer or Claude command
  context, not inside a bare hook). If a workflow is unparseable after install, the viz
  degrades to linear mode with a visible warning until the installer is re-run.

### FR6 — Invoke-time bootstrap (via hooks)
- FR6.1 On workflow invocation: start the server if not running (spawn detached, reuse via
  server.json), generate the graph (FR3/FR5), POST the run_start event, surface the
  dashboard URL.
- FR6.2 Auto-open the dashboard in the default browser when the workflow starts (`open` on
  macOS, `xdg-open` elsewhere).
- FR6.3 On SessionEnd, the fifth hook stops the server (user's Q6 answer B).

### FR7 — Generality
- FR7.1 The installer and parser are workflow-agnostic: any repo with
  `.claude/workflows/*.js` works, not just workflow-examples.

### FR8 — Build health
- FR8.1 Fix the failing README smoke test (`tests/test_smoke.py::
  test_readme_documents_the_serve_graph_flow_and_is_not_stale`) in unit-1: align the test
  and README, and extend the README with the new installer/bootstrap sections.
  (Drift half resolved by planning-docs/000 (the module-move commit); content half lands in
  Units B and C.)

### FR9 — Skipped-stage visibility (added during Unit A Functional Design)
- FR9.1 A stage that the workflow conditionally skips must be visually obvious in the
  dashboard (distinct colour/state), not silently dark.
- FR9.2 The skip state is inferred client-side: a node with no instance whose
  on_pass/on_fail predecessor finished successfully and whose successor arrived (or the
  run stopped) renders as skipped.
  (User input, 2026-10-25T02:42:00Z: "if a stage is skipped, that should be visually
  obvious (e.g. by colouring it)". Placement resolved 2026-10-25T02:46:00Z: new
  Unit D — skipped-stage visualisation — constructed after Unit C.)

## Non-Functional Requirements

- **NFR1 Security (blocking — Security extension opted in, all SECURITY-01..15)**:
  Preserve the existing security baseline (loopback-only bind, bearer token via 0600
  connection file, Host allowlist, bounded bodies, constant-time compare) and extend it to
  the new surface: hook-spawned server inherits the same protections; no secrets in logs;
  no `latest`-tagged or unpinned install steps; installer never writes executable content
  derived from untrusted input.
- **NFR2 Reliability**: parse failures fail loudly with a named reason (never a silent
  wrong graph); hooks remain fail-silent (always exit 0, never block the workflow); the
  invoke-time path must never crash a workflow run.
- **NFR3 Testability (PBT partial — blocking PBT-02/03/07/08/09)**: round-trip and
  invariant property tests for the new pure functions (label parsing, graph construction,
  settings.json merge), domain-appropriate generators, shrinking + seed reproducibility,
  Hypothesis as the Python PBT framework; PBT complements example-based tests.
- **NFR4 Resiliency (minimal — desktop tool, not a web server)**: directionally resilient
  design: explicit timeouts on external calls, fail-safe defaults, graceful degradation to
  linear mode; cloud-only rules (multi-zone, DR, auto-scaling) N/A. Resiliency clarifying
  questions (RTO/RPO, change management, CI/CD, rollback, deployment style, incident
  response) deferred to NFR Design — user explicitly asked to proceed.
- **NFR5 Usability**: bootstrap must be a single command in the target repo; the dashboard
  opens without manual serve steps.
- **NFR6 Maintainability**: the static-analysis subset is documented precisely (what is
  parsed, what fails); agent fallback produces yaml indistinguishable from a hand-written
  one.

## Architectural Considerations

- Hook-based invoke-time bootstrap is the confirmed mechanism (user: "The hooks approach
  is good, the general architecture is good").
- Existing `Graph.load()` validation and `/graph` serving are reused unchanged; the
  generator produces the same schema the validator already accepts.
- The event pipeline (normalise → ingest → SSE) is unchanged in unit-1.
- Open decision for NFR Design: fallback viz-yaml directory flag design (`--viz-dir`,
  default `.claude-local/viz/`).

## Success Criteria (confirmed by user)

After running bootstrap in workflow-examples and running /implement, the dashboard shows
the correct live graph — nodes, retries, loop-backs, verdict colours — with zero
hand-authored graph config, reachable without manual serve steps.
