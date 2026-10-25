# Unit of Work

Three units, derived from the Domain Exposition (UE1-UE4, DOMAIN-03). Construction
order: A → B → C. The standalone module move (planning-docs/000) completed before unit
work began (the module-move commit); unit design assumes the DDD layout.

## Unit A — graph source

**Purpose**: turn a Claude Dynamic Workflow's JavaScript into the existing graph
contract, or fail with named, actionable failures.

**Components**:

- `graph_source/parser.py` — `WorkflowSource` value object. Strict static parse of the
  invoked workflow's JS into the `Graph` structure `Graph.load` accepts (D5), covering
  the FR4 subset: `export const meta`; `agent()` call sites with literal or
  literal-static-segment template labels; `const MAX_ROUNDS`; while/for + continue →
  loop-back edges; early literal `return` → terminal edges; if-guarded `agent()` →
  conditional nodes; `Promise.all` groups → parallel nodes. Anything outside the subset
  is a named failure — never a guess.
- `graph_source/parse_failures.py` — `ParseFailure` value objects with stable machine
  `code`, message, file:line location, context line; `summarise()`.
- `graph_source/agent_prompt.py` — `build_fallback_prompt(workflow_path, failures,
  viz_dir)`: pure derivation of the /viz agent prompt from failures.
- `/viz` command template content (UE3) — the instructions the fallback agent follows;
  co-evolves with the failure codes and prompt (FR5).
- `graph/graph.py` — `Graph.to_yaml()`: entity-owned serialization, byte-compatible with
  the hand-authored schema (D5, DOMAIN-08), lossless round-trip.

**Acceptance criteria**: parser round-trips the fixture corpus (implement.js
label/loop/terminal/conditional shape; rca.js remeasure case); every unsupported
construct class raises its named failure with file:line; `Graph.load` accepts
`Graph.to_yaml()` output for every graph in the corpus; PBT round-trip + invariant
properties green (NFR3).

**Requirements**: FR3 (dynamic generation), FR4 (strict subset), FR5 (fallback
information), D5 (one contract). NFR: NFR3 (PBT targets), NFR6 (documented subset).

## Unit B — hook path / server lifecycle

**Purpose**: at workflow invoke time, generate the graph, start (or reuse) the server,
and open the dashboard; at session end, stop the server. Bounded by one invariant: a
workflow run never observes a failure (NFR2).

**Components**:

- `workflow/hook_command.py` — dispatcher (D10): keyed on `hook_event_name`. Workflow
  `PreToolUse` → run invoke bootstrap then forward as today; `SessionEnd` → run session
  shutdown (no forward); everything else forward-only. Silence wrapper unchanged.
- `invoke/bootstrap.py` — `Bootstrap` application service (FR6/Q2): read connection
  file, probe `/graph` to reuse a live server; else parse the invoked workflow (Unit A),
  on `Graph` write the transient cache yaml to the state dir and spawn
  `serve --port 0 --graph <cache>` detached (stdout/stderr → state-dir log, never the
  hook's streams), on `ParseFailure` spawn `serve` without `--graph` (linear mode;
  existing unmapped-step warning surfaces degradation, NFR4); bounded wait for the
  connection file; open the dashboard in the default browser (`open`/`xdg-open`, Q2b).
  Never raises past the dispatcher.
- `invoke/shutdown.py` — SessionEnd branch (Q6): read connection, call
  `Connection.stop_server()`. May fold into the dispatcher if thin (open decision 1).
- `dashboard/connection_file.py` — `Connection.stop_server()`: authenticated POST
  /shutdown, 1s timeout, empty ProxyHandler; `LOOPBACK_ADDRESS` relocates here from
  `dashboard/server.py`.
- `dashboard/server.py` — `POST /shutdown` (Bearer token + Host allowlist, same checks
  as /ingest; 401/204). Stops the server and removes its connection file, the same
  sequence as SIGINT. Server owns its lifecycle; no PID handling.
- README: invoke-time section + /shutdown endpoint documentation (FR8 content half).

**Acceptance criteria**: end-to-end with the real hook payload fixtures — a workflow
invocation produces run_start + step events on a dashboard that is already open before
the first step lands; a second invocation reuses the running server; SessionEnd stops
it; all failure paths (no connection file, spawn failure, unparseable graph) leave the
hook silent and exit 0; full suite green.

**Requirements**: FR3 (invoke-time), FR6 (bootstrap), Q6-B (SessionEnd stop), D10
(dispatcher). NFR: NFR2 (never-fails invariant), NFR4 (linear-mode degradation,
bounded wait), NFR1 (/shutdown security), FR8 (README content half).

## Unit C — install

**Purpose**: one command wires a repo: verify the tool, write the five hooks, create the
/viz command, record the viz-dir choice.

**Components**:

- `install/installer.py` — application service at the interactive boundary (FR1/D6/D8):
  verify hook path (empty stdin, exit 0); idempotently merge the five registrations
  into `.claude/settings.local.json` (four byte-identical to the README contract +
  SessionEnd; preserve existing, only add missing, invalid JSON fails loudly); create
  `.claude/commands/viz.md` from the template (overwrite only with `--force`); record
  the viz-dir choice (`--viz-dir` flag or prompt; default `.claude-local/viz/`,
  alternative `.claude/viz/`, Q4); print the install summary.
- `cli.py` — `install` subcommand (D9).
- `install/templates/viz-command.md` — the packaged template (content from Unit A);
  deployment belongs here (UE3).
- README: installer section (FR8 content half).

**Acceptance criteria**: installing twice changes nothing; a repo with pre-existing
unrelated hooks keeps them; the created /viz command produces a yaml that `Graph.load`
accepts; installer failures print the error and exit non-zero (D8 boundary).

**Requirements**: FR1 (installer), FR2 (entry point), Q4 (viz-dir choice). NFR: NFR1
(settings merge), NFR5 (one-command bootstrap), FR8 (README content half).

## Unit D — skipped-stage visualisation (added during Unit A Functional Design)

**Purpose**: make conditionally-skipped stages visually obvious (FR9). The graph schema
has no conditional concept (FD2), so a gated node that never ran must be distinguishable
from a pending node the run simply hasn't reached.

**Components**:

- `static/viz-core.js` — pure skip inference in the reducer: a node with no instance
  whose on_pass/on_fail predecessor has a finished pass instance and whose successor
  arrived (or the run stopped) → skipped state. Never inferred mid-run before the
  successor arrives.
- `static/app.js` — apply the skipped class to the SVG node.
- `static/styles.css` — distinct skipped colour/state.
- `tests/js/viz-core.test.mjs` — inference cases (gated skip, terminal never fired,
  retry-round interplay).

**Acceptance criteria**: a verify-fsm-style gated node renders skipped when the guard
was false and the run completed; a node the run has not yet reached stays pending; an
instance that arrives later supersedes skipped; all under Node tests.

**Requirements**: FR9.1, FR9.2.

**Traced to**: FD2 hybrid (Unit A) — the skip state is the visual counterpart of the
gated node. UE4-style boundary: one acceptance gate, "a skipped stage is visibly
distinct and never misrendered". Construction order: A → B → C → D (D consumes the
event stream B delivers and the graphs A produces).

**Open sub-questions for Unit D's own Functional Design**: whether terminals that never
fired (e.g. the blocked terminal when the run ends done) also render skipped, and the
exact skipped colour.

## Not units

- FR7 (workflow-agnostic) — a constraint on Units A/B/C, not a unit.
- NFR5 (usability) — spans B (auto-open) and C (one command).
- The 000 module move — standalone work, already done (the module-move commit).
- The event pipeline (`events`, `run_state`, `hook_adapter`, `/ingest`, `/stream`,
  `/graph`, static UI) — untouched in unit-1.
