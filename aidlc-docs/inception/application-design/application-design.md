# Application Design

Consolidated design for unit-1 (bootstrap + dynamic graph generation). Detail lives in
the sibling artifacts: components.md, component-methods.md, descent-audit.md,
component-dependency.md. The complete domain entity model — existing entities plus the
unit A/B/C/D proposals — is diagrammed in `domain-entities.mmd` / `domain-entities.svg`.

## Summary

Unit-1 makes the visualiser self-bootstrapping and its graph dynamic. One installer
command (`claude-workflow-viz install`) wires a repo at install time; the hook command
becomes an event dispatcher that, at workflow invoke time, statically parses the invoked
workflow's JavaScript into the existing graph contract, starts (or reuses) the server,
and opens the dashboard; SessionEnd stops the server. Where static analysis cannot
parse, a named-failure report feeds a Claude Code command that generates a
`<workflow>.viz.yaml` in the existing schema.

## Components at a glance

| Component | Type | Key responsibility |
| --- | --- | --- |
| `install/installer.py` | application service (interactive boundary) | install-time bootstrap: hooks, command file, viz-dir choice (FR1, FR2, FR7) |
| `install/templates/viz-command.md` | packaged template | `/viz` command: agent fallback generation (FR2, FR5) |
| `graph_source/parser.py` (`WorkflowSource`) | value object | strict static parse → `Graph` or named failure (FR3, FR4) |
| `graph_source/parse_failures.py` | value objects | named failure per construct class (D4) |
| `graph_source/agent_prompt.py` | derivation | fallback prompt from failures (FR5) |
| `invoke/bootstrap.py` | application service | invoke-time: parse, spawn/reuse server, open dashboard (FR3, FR6) |
| `invoke/shutdown.py` | glue | SessionEnd stop via `Connection.stop_server()` (Q6-B) |
| `graph/graph.py` | + `to_yaml()` | entity owns serialization (D5, DOMAIN-08) |
| `dashboard/connection_file.py` | + `stop_server()`, `LOOPBACK_ADDRESS` | connection knows how to stop its server |
| `dashboard/server.py` | + `POST /shutdown` | server owns its lifecycle |
| `workflow/hook_command.py` | dispatcher | behaviour keyed on `hook_event_name` (D10) |
| `cli.py` | + `install` subcommand | third entry point (D9) |

## Fixed decisions (from Q&A)

- Q1/Q1b: dynamic graph; no user-authored yaml. Static analysis first (strict subset,
  named failures, never guess); agent fallback writes a `<workflow>.viz.yaml` in the
  existing schema. The transient cache file the invoke path writes is machine-generated,
  regenerated every invocation, and invisible to the user.
- Q2: installer at install time; generate-graph/start-server/open-dashboard at invoke
  time via hooks.
- Q2b: auto-open the dashboard on workflow start.
- Q3: generic — any repo with `.claude/workflows/*.js`.
- Q4: fallback yaml dir is an install-time choice (`--viz-dir`; default
  `.claude-local/viz/`, shared-repo alternative `.claude/viz/`). Discovery tries
  local then shared.
- Q5: entry point is a Claude Code command (`.claude/commands/viz.md`).
- Q6: server starts at invoke, stops at SessionEnd.
- D8: typed results everywhere except the interactive installer boundary.
- D9: `claude-workflow-viz install`.
- D10: one dispatcher command; five byte-identical registrations (four existing +
  SessionEnd).

## Open design decisions carried into construction

1. **`invoke/shutdown.py` may collapse into the dispatcher.** The descent audit
   concludes the behaviour is `Connection.stop_server()`; the module may end up thin
   enough to fold into `hook_command`. Decided at construction by the thinnest-shape
   test, not before.
2. **`agent_prompt.py` may fold into `parse_failures.py`** for the same reason.
3. **`/shutdown` must pass the Security extension review** (NFR Requirements): token,
   Host allowlist, body-less; no new attack surface beyond what `/ingest` already
   proves.
4. **Server-spawn race**: PreToolUse hooks are async; the first step event can race the
   graph parse. Covered by the client's existing refetch/backoff and the parse being
   milliseconds; not a design change.

## NFR coverage

NFR1 security (blocking extension) applies to `/shutdown`, the spawn log path (state
dir only, never the hook's streams), and the installer's settings merge. NFR2: the
dispatcher's existing silence wrapper covers all new branches. NFR3 PBT targets:
`Graph.to_yaml()` round-trip and parser invariants. NFR4: bounded connection-file wait,
linear-mode degradation. NFR5: one install command; no manual serve steps. NFR6: the
supported parse subset is documented in components.md and mirrored in the command
template.

## Construction implications

- The README smoke test's heading list is fixed alongside the README's new installer and
  invoke-time sections (FR8).
- `planning-docs/000` (module move) executes first, standalone; unit-1 assumes the moved
  layout.
- `LOOPBACK_ADDRESS` relocation (000's open decision) lands in unit-1 with
  `Connection.stop_server()`.
