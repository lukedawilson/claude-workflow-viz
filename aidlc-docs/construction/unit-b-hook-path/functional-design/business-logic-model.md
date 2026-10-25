# Business Logic Model — Unit B (hook path / server lifecycle)

The unit is bounded by one invariant: a workflow run never observes a failure (NFR2).
Every branch below ends with the hook exiting 0 and writing nothing (UEB5).

## Flow 1 — Workflow invocation (Workflow PreToolUse)

```
hook payload arrives
  → dispatcher: hook_event_name == PreToolUse, tool name Workflow
    → Bootstrap.run(payload, cwd)
      1. Connection.read()
         ├─ no file ──────────────────────────────► go to 2
         └─ file present
              probe GET /graph with token
                ├─ live ──────────────────────────► go to 5   (reuse, no spawn)
                └─ not live ──────────────────────► go to 2
      2. parse invoked workflow (Unit A WorkflowSource)
         ├─ Graph ────────────────► write cache yaml to state dir (UEB2)
         │                          spawn serve --port 0 --graph <cache> detached
         │                          (output → state-dir log; UEB3)
         └─ ParseFailure ─────────► spawn serve (no --graph)   (linear mode; UEB5)
      3. wait ≤ 10 s for server.json (UB3)
         └─ timeout → return silently (exit 0; re-invoking recovers)
      4. read token from server.json
      5. open dashboard URL in default browser (open / xdg-open; UEB6)
    → return to dispatcher
  → forward event as today: normalise → POST /ingest  (emits run_start)
```

Reuse path: an existing live server is never re-spawned and its graph is not replaced —
the cache write and spawn happen only when a server must be started. A second
invocation therefore reuses the running server unchanged.

## Flow 2 — Session end (SessionEnd)

```
hook payload arrives
  → dispatcher: hook_event_name == SessionEnd
    → Connection.read()
        ├─ no file → nothing (stop_server no-ops; UB2)
        └─ file present → Connection.stop_server()
              POST /shutdown (Bearer, 1s timeout)
                ├─ 204 → server stopped, connection file removed (server's own
                │        sequence, same as SIGINT)
                └─ 401 / error / timeout → swallowed (NFR2, UEB5)
    → no forward (SessionEnd produces no viz event)
```

## Flow 3 — Everything else

```
hook payload arrives
  → dispatcher: any other hook_event_name
    → forward only: normalise → POST /ingest   (unchanged today)
```

## Failure inventory (each maps to silent exit 0 — UEB5)

| Failure | Where it surfaces |
| --- | --- |
| No connection file | not an error — first start, proceeds to parse + spawn |
| Probe timeout / server not live | treated as no server — spawn path |
| Spawn failure | swallowed; hook exits 0; nothing opens |
| ParseFailure (unparseable workflow) | linear-mode spawn; dashboard shows unmapped-step warning |
| Connection-file wait timeout | swallowed; dashboard opens only if the file appeared; re-invoking recovers |
| Browser-open failure | swallowed |
| SessionEnd stop failure | swallowed; the server stays up (next SessionEnd retries) |

Diagnosis channel for a broken graph: the state-dir debug log (Unit A NRA1-B pattern) —
the parser's failure summary and the server's spawn output are readable there. Nothing
on the hook path prints (UEB5, revised — async hook output is never shown to the user).

## Race note (UB4)

The PreToolUse hook runs async; the first step event can arrive before the graph is
served. No handshake: the parse is milliseconds and the client's existing
refetch/backoff covers the race. The hook never blocks the workflow.

## Amendment 1 — multi-workflow (NRB4 = B, 2026-10-25T15:10:00Z)

Flow 1 changes (invocation), the rest is unchanged:

```
2. parse invoked workflow (Unit A WorkflowSource); workflow name from payload
   ├─ Graph ────────────────► write <state>/graphs/<workflow>.viz.yaml
   │                          (per-workflow; other caches untouched)
   │                          if no live server: spawn detached (output → log)
   │                          if live server: no spawn, no restart
   └─ ParseFailure ─────────► no cache write; that workflow will render
                              linearly (registry miss → linear fallback)
                              if no live server: spawn (no --graph)
5. open dashboard URL: /?token=…&workflow=<name>
```

Server side: `/graph?workflow=<name>` loads and caches the registry entry on
first request; unknown name → linear response for that request; no parameter
→ the default graph (existing `--graph`, or linear). A live server is reused
across workflows and across repos (R1/R11 hold); the registry is the only
per-workflow state.

Concurrency: two sessions running different workflows now render correctly —
each page (or each selector position) fetches its workflow's graph, and the
run_start `workflow` field associates each session's steps with its workflow.
Same-workflow concurrency is unchanged.
