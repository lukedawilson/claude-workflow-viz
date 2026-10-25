# Domain Entities — Unit B (hook path / server lifecycle)

Derived from the Domain Exposition answers (DOMAIN-03 trace: every concept below traces
to an exposition answer). Existing entities are named as they exist today; this unit
adds behaviour and one relocated constant.

## Trace list (concept → exposition answer)

| Concept | Trace |
| --- | --- |
| Connection owns liveness (no PID file, no lockfile) | UEB1 = A |
| Bootstrap owns the transient cache yaml | UEB2 = A |
| Detached spawn; server output to state-dir log only | UEB3 = A |
| POST /shutdown belongs to the server's HTTP surface | UEB4 = B |
| Every hook-path failure is silent (dashboard-or-nothing degradation) | UEB5 = A (revised from B) |
| Bootstrap performs the browser-open | UEB6 = A |
| SessionEnd branch folds into the dispatcher | UB1 = A |
| stop_server no-ops without a connection file | UB2 = A |
| 10-second bounded wait for the connection file | UB3 = C (revised from A) |
| No blocking handshake for the async race | UB4 = A |

## Entities

### Connection — `dashboard/connection_file.py` (existing, +behaviour)

The value object that owns the machine's single liveness record (UEB1): reads
`server.json` from the state dir, yields port + token, and — new this unit —
stops its server.

New behaviour:

- `stop_server()` — POST `/shutdown` with the Bearer token, 1s timeout, empty
  ProxyHandler (mirrors the hook path's /ingest POST). No-op when no connection file
  exists (UB2). Silently swallows failures — the SessionEnd branch must never fail
  (NFR2, UEB5).
- `LOOPBACK_ADDRESS` relocates here from `dashboard/server.py` (planning-docs/000's
  open decision): `stop_server()` needs the address, and importing `server` from
  `connection_file` would cycle.

State it owns: `server.json` (port, token) in the state dir. No PID file, no lockfile —
liveness is file presence plus an authenticated probe (UEB1).

### Bootstrap — `invoke/bootstrap.py` (new, application service)

The invoke-time orchestrator. Owns the transient cache yaml (UEB2): it is the file's
sole writer; the server reads it once at start; each invocation overwrites it; nothing
reads it after the spawn.

Responsibilities (in order):

1. `Connection.read()` → if present, probe `GET /graph` with the token → live server =
   reuse, skip straight to step 5.
2. Parse the invoked workflow with Unit A's `WorkflowSource` (FR3).
3. On `Graph`: write the cache yaml to the state dir; spawn
   `serve --port 0 --graph <cache>` detached — stdout/stderr to a state-dir log file,
   never the hook's streams (UEB3). On `ParseFailure`: spawn `serve` with no `--graph`
   (linear mode; the dashboard's unmapped-step warning shows the degradation — UEB5).
4. Wait up to 10 seconds for `server.json` (UB3). Timeout → return silently.
5. Read the token from `server.json`; open the dashboard URL in the default browser
   (`open` / `xdg-open`) — Bootstrap's last act before returning (UEB6). Only after the
   connection file appeared.

The browser-open is Bootstrap's because it owns the invoke moment; the server never
observes the invoke event, and on reuse there is no server start to hang the open on
(UEB6).

### Dispatcher — `workflow/hook_command.py` (existing, +branching)

The hook command becomes an event dispatcher keyed on `hook_event_name` (D10):

- Workflow `PreToolUse` → run Bootstrap, then forward the event as today
  (normalise → POST /ingest, which emits run_start).
- `SessionEnd` → `Connection.stop_server()` inline (UB1 — no separate module), no
  forward.
- everything else → forward only, exactly as today.

The `run_hook` silence wrapper (suppress `BaseException`, exit 0, no output) is
unchanged and covers every new branch (NFR2, UEB5).

### Server — `dashboard/server.py` (existing, +endpoint)

Adds `POST /shutdown`: Bearer token + Host allowlist, the same checks as `/ingest`;
401 on a missing/wrong token, 204 on success; stops the server and removes its
connection file if it still holds the server's token — the same shutdown sequence as
SIGINT today. The server owns its own lifecycle; there is no PID handling anywhere.

/shutdown is part of the server's HTTP surface (UEB4): it shares the server's
conventions and is reviewed with them (open decision 3 lands at NFR Requirements).
`Connection.stop_server()` remains the intent; the endpoint is transport.

### State-dir debug log — infrastructure (not domain)

The state-dir log file that receives the spawned server's stdout/stderr (UEB3). Marked
infrastructure: it is a diagnosis channel (the Unit A NRA1-B pattern), not a domain
concept.

## Relationships

```
Bootstrap ──reads──► Connection (server.json; probe)
Bootstrap ──writes──► cache yaml (state dir)          [UEB2: sole writer]
Bootstrap ──spawns──► Server (detached; log → state dir)   [UEB3]
Bootstrap ──opens──► browser (token from Connection)  [UEB6]
Dispatcher ──Workflow PreToolUse──► Bootstrap, then forward
Dispatcher ──SessionEnd──► Connection.stop_server() → Server POST /shutdown   [UB1, UEB4]
```

## Amendment 1 — multi-workflow graph registry (NRB4 = B, 2026-10-25T15:10:00Z)

The single-served-graph model is replaced: the server serves one graph per
workflow name, not one graph per machine.

New/changed concepts (trace: NRB4 = B + user port-selection directive):

- **Workflow name** (new domain concept) — the identity of the invoked
  workflow, carried by the Workflow PreToolUse payload. Bootstrap reads it to
  locate the JS file (it already needs it to parse) and keys everything
  downstream on it.
- **Event gains an optional `workflow` field** (schema extension, backward
  compatible) — populated on `run_start` (the Workflow PreToolUse event).
  Step events do not carry it; the client maps session → workflow from the
  run_start event. `events.py` Event + from_dict + `viz-core.js` reducer +
  tests all extend.
- **Graph registry** (server, new) — `{workflow_name: Graph}`; each graph is
  loaded on demand from `<state>/graphs/<workflow>.viz.yaml` on the first
  `/graph?workflow=<name>` request, then held in memory. No entry → that
  request gets the linear fallback (that workflow renders linearly); a
  request with no workflow parameter gets the default graph (the existing
  `--graph` flag, or linear when none was given) — backward compatible with
  today's `/graph`.
- **Bootstrap cache write keyed by workflow name** — R2 amended: the cache is
  `<state>/graphs/<workflow>.viz.yaml`, overwritten per invocation of that
  workflow. Other workflows' caches are untouched.
- **Dashboard URL carries the workflow name** — Bootstrap opens
  `/?token=…&workflow=<name>`; the client's fetchGraph passes it; a workflow
  selector (fed by run_start events) switches views and refetches.

Server spawn is unchanged in shape: still one server per machine (R1), still
detached with output to the state-dir log. Only the served graph is
per-workflow.
