# Business Rules — Unit B (hook path / server lifecycle)

Each rule cites its source (exposition/design answer or requirement). Rules are the
contract the construction code must satisfy.

| # | Rule | Source |
| --- | --- | --- |
| R1 | The machine's only liveness record is the connection file: `server.json`'s presence plus a token-authenticated probe. No PID file, no lockfile, no second registry. | UEB1 = A |
| R2 | Bootstrap is the sole writer of the transient cache yaml; the server reads it once at start; each invocation overwrites it; nothing reads it after the spawn. | UEB2 = A |
| R3 | The server is spawned detached; its stdout/stderr go to a state-dir log file only, never the hook's streams. | UEB3 = A |
| R4 | Every hook-path branch — no connection file, probe failure, spawn failure, parse failure, wait timeout, browser-open failure, stop failure — ends with the hook exiting 0 and writing nothing. | NFR2, UEB5 = A |
| R5 | `Connection.stop_server()` no-ops when no connection file exists. | UB2 = A |
| R6 | The wait for `server.json` after a spawn is bounded at 10 seconds; on timeout Bootstrap returns silently and the dashboard does not open. | UB3 = C |
| R7 | Bootstrap opens the dashboard as its last act, only after the connection file appeared; the server never opens a browser. | UEB6 = A |
| R8 | `POST /shutdown` shares the server's conventions: Bearer token + Host allowlist (same checks as /ingest); 401 on bad token, 204 on success; stopping removes the connection file, the same sequence as SIGINT. No PID handling. | UEB4 = B, D10 design |
| R9 | The dispatcher branches on `hook_event_name`: Workflow PreToolUse → Bootstrap then forward; SessionEnd → stop_server inline (no separate module), no forward; everything else forward-only. | D10, UB1 = A |
| R10 | A parse failure spawns the server without `--graph` (linear mode); the degradation is visible only in the dashboard's unmapped-step warning. The state-dir debug log carries the parser's failure summary for diagnosis. | UEB5 = A, NFR4 |
| R11 | A live server is reused: no re-parse, no cache write, no re-spawn. The probe is `GET /graph` with the stored token. | FR6, Q2 |
| R12 | No blocking handshake for the async PreToolUse race; the client's refetch/backoff covers it. | UB4 = A |
| R13 | Bootstrap never raises past the dispatcher; the silence wrapper (suppress `BaseException`, exit 0) covers all new branches. | NFR2, NFR4 |
| R14 | SessionEnd produces no viz event and stops the server; if the stop fails, the server stays up and the next SessionEnd retries. | Q6 = B, R5 |

## Domain Validation notes (recorded here per extension flow)

- DOMAIN-04 traceability: FR3 (invoke-time parse + cache write) → R2/R10; FR6
  (bootstrap: start-or-reuse, bounded wait, auto-open) → R5-R7/R11/R6; Q2/Q2b (reuse,
  auto-open) → R11/R7; Q6-B (SessionEnd stop) → R5/R14; D10 (dispatcher) → R9; NFR2
  (never-fails) → R4/R13; NFR4 (degradation) → R10; NFR1 (/shutdown security) → R8
  (reviewed at NFR Requirements, open decision 3); FR8 (README content half) →
  construction.
- DOMAIN-05: no delegating entities, no service-named value objects, no coined labels,
  no per-endpoint domain services (/shutdown is server infrastructure, UEB4 = B), no
  behaviourless aggregates.
- DOMAIN-06 descent audit: Bootstrap = application service (step 5 — cross-boundary
  orchestration: process spawn, HTTP probe, browser open; no entity owns these);
  `stop_server()` = method on Connection (step 2 — it knows address + token);
  dispatcher = existing entry point, not a service.
- DOMAIN-07: no 1:1 controller→aggregate services; no Manager/Helper/Orchestrator/
  Facade names.
- DOMAIN-08: no Repository/DAO/store; persistence is `server.json` on Connection
  (existing) and the transient cache yaml on its producer Bootstrap (UEB2).

## Amendment 1 rules (NRB4 = B, 2026-10-25T15:10:00Z)

| # | Rule | Source |
| --- | --- | --- |
| R15 | The server serves one graph per workflow name: `/graph?workflow=<name>` loads `<state>/graphs/<workflow>.viz.yaml` on demand and caches it; unknown name → linear fallback for that request; no parameter → the default graph (existing `--graph` flag, or linear when none). | NRB4 = B |
| R16 | `Event` gains an optional `workflow` field, populated on `run_start` from the Workflow PreToolUse payload's workflow name. Step events do not carry it; the client maps session → workflow from run_start. The field is optional and backward compatible. | NRB4 = B |
| R17 | The transient cache yaml is keyed by workflow name (`<state>/graphs/<workflow>.viz.yaml`) and only that workflow's file is overwritten per invocation. R2's sole-writer property holds per workflow. | NRB4 = B, R2 amended |
| R18 | Reuse means no re-spawn (R11 holds); the cache write still happens every invocation so a live server's registry picks up the fresh graph on the next `/graph` request for that workflow. | NRB4 = B |
| R19 | Bootstrap opens the dashboard URL with `?workflow=<name>`; the client refetches the graph when the workflow selector changes. | NRB4 = B |
