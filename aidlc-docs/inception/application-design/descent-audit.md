# Descent Audit

Domain Standards extension: every service placement must justify why the behaviour does
not live on an entity or value object first (DOMAIN-06). Descent order: (0) plain static
helper → (1) value object → (2) method on existing entity → (3) new entity →
(4) domain service → (5) application service.

## Audit per service-shaped component

### `invoke/bootstrap.py` — Bootstrap

Steps 0-4 ruled out in order:

- (0) not a pure helper: it coordinates process spawning, HTTP, and the connection file.
- (1) not a value object: no value concept; it performs side effects across boundaries.
- (2) not a method on an existing entity: no single entity owns "start the dashboard
  server" — it touches `Connection`, `Graph`, the OS process table, and the browser.
  `RunState` owns run state, not the server process.
- (3) no new entity: a `Server` process entity would wrap one `subprocess.Popen` call and
  add no behaviour beyond what `serve` already owns in-process.
- (4) not a domain service: the workflow-observation domain has no concept of process
  lifecycle; spawning a detached server is an infrastructure concern.

**Verdict: (5) application service.** Justification recorded: cross-aggregate orchestration
of infrastructure (detached process spawn, browser opening, HTTP) at the event-dispatch
boundary. It remains silent and never raises past the dispatcher (NFR2).

### `install/installer.py` — Installer

Same descent, faster: writes repo config files (`.claude/settings.local.json`,
`.claude/commands/viz.md`), prompts a human, and may raise (D8-B). No entity owns repo
configuration; this is entry-point orchestration for a human actor (D6).

**Verdict: (5) application service at the interactive boundary.** Per D8 it may fail
fast; `cli` catches and prints.

### `invoke/shutdown.py` — shutdown dispatcher

The behaviour to stop the server descends to (2): `Connection.stop_server()` — the
connection file value object knows its server's address and token; stopping is one
authenticated POST using them. No new entity, no service needed.

**Verdict: (2) method on existing value object.** `invoke/shutdown.py` remains only as
the dispatcher's SessionEnd branch glue: read connection, call `stop_server()`, stay
silent. If construction finds the glue trivial enough to fold into the dispatcher
itself, the module may collapse into `hook_command` — flagged, not pre-decided.

### `graph_source/parser.py` — WorkflowSource

**Verdict: (1) value object with computed behaviour.** The workflow's source text is a
value concept in the run-observation domain (the thing hooks observe). Parsing it into
the shared `Graph` contract is computed behaviour on that value, returning either the
`Graph` or named `ParseFailure` values (D5, D4). The module is named `parser.py`; the
class is `WorkflowSource` — module layout and class naming stay separate.

### `graph_source/agent_prompt.py` — prompt derivation

**Verdict: (1) derivation over value objects.** Building the fallback prompt is a pure
projection of `ParseFailure` values (D4). It could be a method on `ParseFailure`
(`summarise`) plus a short formatting function; construction may fold the module into
`parse_failures.py` if it stays this thin.

### `graph/graph.py` — `Graph.to_yaml()`

**Verdict: (2) method on existing entity.** `Graph` already owns its loading
(`Graph.load`); serialization is the same persistence concern in reverse, so the entity
owns it (DOMAIN-08: persistence lives on the owning aggregate).

## DOMAIN-05 blocking-shape checks (all avoided)

- No delegating entities: `WorkflowSource` computes; it does not proxy another object's
  behaviour.
- No service-named value objects: `ParseFailure` variants are named for the construct
  class they reject, not for a service.
- No coined "the X model" labels: concepts use the requirement vocabulary (graph source,
  parse failure, runtime context).
- No per-endpoint domain services: `/shutdown` is a method on the server (the existing
  HTTP handler shape), not a domain service per endpoint.
- No behaviourless aggregates: `Graph` keeps loading + serialization; `Connection` keeps
  read/write/remove + stop.

## DOMAIN-07 checks

- No 1:1 controller→aggregate application services: Bootstrap spans several aggregates
  and infrastructure; Installer has no aggregate behind it.
- No banned names: no Manager/Helper/Orchestrator/Facade anywhere in the model.
  `Installer` and `Bootstrap` name what the actor does at the boundary.

## DOMAIN-08 checks

- No Repository/DAO/store/unit-of-work: the only new persistence is `Graph.to_yaml()`
  (on the entity) and the installer's repo-config writes (entry-point I/O).
