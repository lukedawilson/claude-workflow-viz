# Components

Application Design for unit-1 (bootstrap + dynamic graph generation). Component
identification per `application-design-plan.md` answers D1-D10 and `requirements.md`
FR1-FR8 / NFR1-NFR6.

## Domain Exposition trace (DOMAIN-01 / DOMAIN-03)

Each concept below was established through the exposition Q&A (D1-D6) before any model
proposal; the table traces concept → exposition answer → source requirement.

| Concept | Exposition answer | Source requirement |
| --- | --- | --- |
| Runtime context | D1: exactly three — install, invoke, session-end | FR1, FR3, FR6 |
| Graph source | D2: one concept, two interchangeable producers (static parser, agent fallback) | FR4, FR5, Q1b |
| Server lifecycle | D3 + Q6B: hook-owned start at invoke, SessionEnd stops; one server per machine | FR6 |
| Parse failure | D4: distinct named failure per unsupported construct class; feeds the agent generator | FR4, FR5 |
| Graph contract | D5: parser emits the same Graph structure as `Graph.load` — one schema | FR3, FR4 |
| Actor | D6: interactive human only; installer assumes a terminal | FR1, FR2 |
| Module layout | D7: same wheel, DDD-style subfolders (existing modules moved per planning-docs/000) | NFR6 |
| Error convention | D8: typed results in domain + hook path; installer boundary may fail fast | NFR2, NFR6 |
| Entry point | D9: `claude-workflow-viz install` | FR1 |
| Hook registrations | D10: one dispatcher command, behaviour keyed on `hook_event_name` | FR6, NFR2 |

Coverage of the six exposition dimensions: concepts named (graph source, parse failure),
state ownership (server owns its lifecycle; RunState already owns run state), runtime
contexts (D1), change-togetherness (D2 interchangeable producers, D5 one contract),
invariants/failure modes (D4 never-guess parsing, D8 typed errors, NFR2 hook silence),
actors (D6).

## New components

### `install/installer.py` — Installer

- **Type**: application service at the interactive entry-point boundary (descent audit
  step 5, see descent-audit.md).
- **Responsibility**: install-time bootstrap (FR1, FR7): verify the tool, write the five
  hook registrations idempotently into `.claude/settings.local.json`, create the entry
  point command, record the fallback-yaml directory choice.
- **Error convention**: may raise at the boundary (D8-B); `cli` catches and prints.
- **Keyed on**: FR1 (installer), FR2 (command file), FR7 (workflow-agnostic), Q4
  (`--viz-dir` choice), D6 (interactive, assumes terminal).

### `install/templates/viz-command.md` — command template

- **Type**: static package resource; the installer copies it to
  `.claude/commands/viz.md` (FR2, Q5).
- **Responsibility**: the Claude Code command that invokes the agent fallback: read the
  named parse failures, read the workflow source, write `<workflow>.viz.yaml` in the
  chosen viz dir (FR5). Also documents manual `serve`.
- **Keyed on**: FR2, FR5, Q5.

### `graph_source/parser.py` — WorkflowSource

- **Type**: value object with computed behaviour (descent audit step 2). Module name is
  `parser.py`; the class is `WorkflowSource`.
- **Responsibility**: strict static analysis of one workflow's JavaScript
  (`agent()` call sites, loop-backs, terminals, conditionals, `MAX_ROUNDS`) producing
  the same `Graph` structure as `Graph.load` (D5) — or a named `ParseFailure` (D4).
  Anything outside the supported subset is a named failure, never a guess (FR4).
- **Keyed on**: FR3, FR4, Q1b, D4, D5.

### `graph_source/parse_failures.py` — ParseFailure values

- **Type**: value objects (typed error codes in the existing `GraphError` style).
- **Responsibility**: one distinct class per unsupported-construct class, each carrying
  enough context (file, line, construct) for the agent generator (D4, FR5).
- **Keyed on**: FR4, FR5, D4, D8.

### `graph_source/agent_prompt.py` — agent prompt derivation

- **Type**: thin derivation module (descent audit step 1).
- **Responsibility**: builds the fallback-generation prompt from the collected
  `ParseFailure` values plus the workflow path (FR5).
- **Keyed on**: FR5, D4.

### `invoke/bootstrap.py` — Bootstrap

- **Type**: application service (descent audit step 5).
- **Responsibility**: invoke-time bootstrap (FR3, FR6, Q2): detect a live server (reuse
  via connection file), otherwise statically parse the invoked workflow, cache the graph,
  spawn `serve` detached with its output to a state-dir log, wait for the connection
  file, open the dashboard (Q2b auto-open), and ensure the `run_start` event is
  forwarded. Never raises past the hook dispatcher; never writes to the hook's
  stdout/stderr (NFR2).
- **Keyed on**: FR3, FR6, Q2, Q2b, Q6.

### `invoke/shutdown.py` — shutdown dispatcher

- **Type**: entry-point glue (descent audit step 5 justification in descent-audit.md).
- **Responsibility**: SessionEnd stop (Q6-B): read the connection file and stop the
  server; a no-op when no server is running. Silence contract applies.
- **Keyed on**: FR6, Q6-B, D10.

## Existing components (post planning-docs/000 move) and their unit-1 changes

| Component | Unit-1 change |
| --- | --- |
| `cli.py` | gains the `install` subcommand (D9); `_serve` stays the fail-fast boundary. |
| `workflow/hook_command.py` | becomes the event dispatcher: Workflow PreToolUse → `invoke.bootstrap`, SessionEnd → `invoke.shutdown`, everything else → forward only (D10). Silence contract unchanged. |
| `graph/graph.py` | gains serialization (`to_yaml` / round-trip through the existing viz.yaml schema) so a parsed graph can cross the process boundary to a detached `serve` (D5, DOMAIN-08: the entity owns its persistence). |
| `dashboard/connection_file.py` | gains `Connection.stop_server()` (descent step 2); `LOOPBACK_ADDRESS` relocates here from `dashboard/server.py` (resolves the planning-docs/000 open decision; `stop_server` needs the address and importing `server` would cycle). |
| `dashboard/server.py` | gains one authenticated endpoint `POST /shutdown` (Bearer token, Host allowlist — same checks as `/ingest`) so the server owns its own shutdown; it removes its connection file on shutdown exactly as SIGINT does today. |
| `workflow/hook_adapter.py`, `workflow/events.py`, `workflow/run_state.py`, `graph/node_status.py`, `static/*` | unchanged in unit-1. |

## Explicitly absent

- No graph-cache manager, no `GraphWriter`, no `Repository`/`DAO` (DOMAIN-08): the cache
  file write is `Graph` serialization plus a stdlib write inside Bootstrap.
- No new HTTP surface beyond `/shutdown`: graph hand-off to the detached server goes
  through the existing `serve --graph` contract (transient cache file in the state dir),
  so the graph is re-validated by the same `Graph.load` the user-facing path uses (D5).
- No `Manager`/`Helper`/`Orchestrator`/`Facade` names (DOMAIN-07).

## DOMAIN-04 traceability (requirement → model coverage)

| Requirement | Covered by |
| --- | --- |
| FR1 installer | `install/installer.py` |
| FR2 entry point command | `install/templates/viz-command.md` |
| FR3 dynamic graph at invoke | `invoke/bootstrap.py` + `graph_source/parser.py` |
| FR4 strict subset | `graph_source/parser.py` + `graph_source/parse_failures.py` |
| FR5 agent fallback | `graph_source/agent_prompt.py` + command template + fallback path resolution |
| FR6 invoke-time bootstrap + SessionEnd stop | `invoke/bootstrap.py` + `invoke/shutdown.py` + `/shutdown` |
| FR7 workflow-agnostic | `install/installer.py` (no per-workflow assumptions) |
| FR8 README smoke-test fix | construction (test + README), not a component |
| NFR1 security | `/shutdown` uses existing auth pattern; spawn log path in state dir, never the hook's streams |
| NFR2 reliability | dispatcher and invoke modules hold the silence contract |
| NFR3 PBT partial | targets: `Graph` serialize round-trip, `WorkflowSource` parse/`ParseFailure` invariants |
| NFR4 resiliency minimal | bounded waits for connection file; linear-mode degradation on parse failure |
| NFR5 usability | one command installs; invoke needs no manual steps |
| NFR6 maintainability | parse subset documented; agent yaml indistinguishable from hand-written |
