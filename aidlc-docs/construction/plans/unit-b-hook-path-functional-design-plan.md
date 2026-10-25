# Functional Design Plan — Unit B (hook path / server lifecycle)

Per functional-design.md (construction) + Domain Standards extension (Phase 1 exposition
at each unit's Functional Design; `coding-standards-ddd.yaml` is required reading for
every question drafted here).

## Steps

- [x] Step 1: Analyze unit context (unit-of-work.md Unit B, story-map assignments, Unit A artifacts)
- [x] Step 2: Phase 1 — Domain Exposition Q&A (UEB1-UEB6, DOMAIN-01: every question cites its source requirement)
- [x] Step 3: Design Q&A (UB1-UB4, after the exposition is answered — DOMAIN-02)
- [x] Step 4: Answer analysis (all concrete; UEB5 and UB3 corrected via clarification chains; no follow-ups needed) — vague/ambiguous/contradictory answers → follow-ups
- [x] Step 5: Artifacts — domain-entities.md, business-logic-model.md, business-rules.md (DOMAIN-03 trace list)
- [x] Step 6: Phase 2 — Domain Validation (DOMAIN-04..08; each rule stated or "N/A — reason")
- [ ] Step 7: Completion message + explicit approval + explicit approval; log in audit.md; update aidlc-state.md

## Unit B context (from unit-of-work.md)

Bounded by one invariant: a workflow run never observes a failure (NFR2). Components:
dispatcher in `workflow/hook_command.py` (D10), `invoke/bootstrap.py` (FR6/Q2),
`invoke/shutdown.py` (Q6-B, fold-if-thin), `dashboard/connection_file.py`
`Connection.stop_server()` + `LOOPBACK_ADDRESS` relocation, `dashboard/server.py`
`POST /shutdown`, README invoke-time + /shutdown sections (FR8 content half).
Open construction decisions entering this design: (1) shutdown.py fold; (3) /shutdown
security review (lands at NFR Requirements, not here); (4) async PreToolUse race.

## Phase 1 — Domain Exposition (DOMAIN-01)

Each question cites its source requirement, uses the requirement's own vocabulary, and
presents the concrete alternatives the wording leaves open. Six probe dimensions covered:
concepts named (UEB1), state ownership (UEB1/UEB2), runtime contexts (UEB3),
change-togetherness (UEB4), invariants and failure modes (UEB5), actors (UEB6).

### UEB1 — Who owns the knowledge "a server is running"?

Source: FR6's "start or reuse the server" + Q6's "stop at session end".
FR6 says bootstrap starts a server or reuses one; Q6 says SessionEnd stops it.
Both actions need one shared record of liveness. Which concept owns that record?

A) The connection file. `server.json`'s presence plus a token-authenticated probe is
   the machine's single liveness record — no PID file, no lockfile, no second registry.
B) A distinct liveness concept — a PID file or lockfile separate from `server.json`.

[Answer]: A (2026-10-25T13:48:00Z) — the connection file is the machine's single liveness record; no PID file or lockfile.

### UEB2 — Who owns the transient cache yaml?

Source: FR3's "generate the graph at invoke time" + FR6's bootstrap flow.
Bootstrap parses the invoked workflow and writes a generated yaml to the state dir,
then spawns `serve --graph <cache>`. Who owns that file?

A) The invocation (Bootstrap). Bootstrap writes it, the server only reads it at start,
   each invocation overwrites it, and nothing reads it after the spawn.
B) The server. The server records the graph source it is serving.
C) The connection file. The file is part of the server's connection state.

[Answer]: A (2026-10-25T13:52:00Z) — Bootstrap owns the transient cache yaml; the server only reads it at start, nothing reads it after spawn.

### UEB3 — Confirm the process split and output routing

Source: NFR2 "the hook must stay silent and exit 0" + FR6's detached server spawn.
FR6 spawns a detached server from inside the hook process. NFR2 requires the hook
to write nothing. Confirm the split:

A) The hook process spawns the server detached, waits (bounded) for the connection
   file, then exits. The server's stdout/stderr go to a state-dir log file only —
   never the hook's streams.
B) The hook process keeps the server as a child with shared streams until the server
   is ready.

[Answer]: A (2026-10-25T13:54:00Z) — detached spawn, server output to a state-dir log only, never the hook's streams.

### UEB4 — Does /shutdown change with the connection file, or with the server's endpoints?

Source: UE2 (units-generation exposition: start-or-reuse + session-end stop +
connection file form one bounded context) + Q6-B's session-end stop.
`Connection.stop_server()` calls the server's `POST /shutdown`. Which context does
the /shutdown surface belong to?

A) With the connection file. /shutdown exists solely for the session-end stop:
   `stop_server()`, the endpoint, and `server.json` change together.
B) With the server's HTTP surface. /shutdown is a server endpoint that changes with
   /ingest and /graph, independent of the connection file.

[Answer]: B (2026-10-25T13:58:00Z) — /shutdown is part of the server's HTTP surface (shared Bearer/Host/response conventions); Connection.stop_server() remains the intent in the connection-file context.

### UEB5 — Which failure modes exist, and where does each surface?

Source: NFR2 ("a workflow run never observes a failure") + Unit B acceptance criteria
("all failure paths leave the hook silent and exit 0").
The hook path can hit: no connection file, probe timeout, spawn failure, an
unparseable graph, browser-open failure. Name where each surfaces:

A) All of them surface nowhere on the hook path. Each branch ends with the hook
   exiting 0 and writing nothing; degradation is visible only in the dashboard
   (linear mode / unmapped-step warning) or not at all.
B) Some failures surface a message to the user at the terminal.

[Answer]: B initially, then REVISED to A (2026-10-25T14:02:00Z) after clarification: async hook output is never shown to the user (established at Q2b — that is why auto-open was chosen), so a terminal message is unbuildable for the invoke-time path. Final: silent everywhere on the hook path; degradation shows only in the dashboard or not at all. The state-dir debug log (NRA1-B pattern, Unit A) remains the diagnosis channel for a broken graph.

### UEB6 — Who opens the dashboard URL?

Source: Q2b ("auto-open the dashboard in the default browser when a workflow starts")
+ FR6's bootstrap flow.
Bootstrap obtains the dashboard URL + token from the connection file. Who performs
the browser-open?

A) Bootstrap itself, as its last act before returning to the dispatcher. The server
   never opens a browser.
B) The server process, once it is up.

[Answer]: A (2026-10-25T14:06:00Z) — Bootstrap owns the browser-open because it owns the invoke moment; the server never observes the invoke event (reuse path has no server start, so B would mean a tab per invocation via the run_start ingest). Ordering is safe: the token is read from server.json, which the server writes only after binding.

## Phase 2 — Design Questions (after exposition)

### UB1 — Open decision 1: does invoke/shutdown.py fold into the dispatcher?

A) Fold. The SessionEnd branch is: read connection → `stop_server()` → stay silent;
   a handful of lines inside `hook_command.py`'s dispatcher. No separate module.
B) Keep `invoke/shutdown.py` as its own module for symmetry with `invoke/bootstrap.py`.

[Answer]: A (2026-10-25T14:08:00Z) — the SessionEnd branch folds into the dispatcher; no invoke/shutdown.py module. Open decision 1 closed.

### UB2 — SessionEnd with no server running

Source: Q6-B + NFR2. SessionEnd fires but no `server.json` exists (bootstrap never
ran, or the server already stopped).

A) Silently do nothing — `stop_server()` no-ops when no connection file exists;
   the hook stays silent and exits 0.
B) Log the no-op to the state-dir log file.

[Answer]: A (2026-10-25T14:10:00Z) — stop_server() no-ops without a connection file; the hook stays silent and exits 0.

### UB3 — Bounded wait for the connection file

Source: FR6 ("bounded wait") + NFR4. Bootstrap waits for `server.json` to appear
after spawning the server.

A) 5 seconds, then give up silently — the hook exits 0; the dashboard opens only if
   the connection file appeared in time (re-invoking the workflow recovers).
B) 3 seconds.
C) 10 seconds.

[Answer]: C (REVISED from A, 2026-10-25T14:14:00Z) — 10-second bounded wait; on timeout give up silently, exit 0; re-invoking recovers.

### UB4 — Open decision 4: the async PreToolUse race

Source: decision record 4 (hook runs async; the first step event can race the graph
parse and spawn).

A) No design change — the parse is milliseconds and the client's existing
   refetch/backoff covers the race.
B) Add a blocking handshake — the hook waits for the graph to be served before
   forwarding (delays the workflow; conflicts with NFR2's exit-fast requirement).

[Answer]: A (2026-10-25T14:14:00Z) — no design change; client refetch/backoff covers the race. Open decision 4 closed.

## Mandatory artifacts (written after answers)

- `aidlc-docs/construction/unit-b-hook-path/functional-design/domain-entities.md`
- `aidlc-docs/construction/unit-b-hook-path/functional-design/business-logic-model.md`
- `aidlc-docs/construction/unit-b-hook-path/functional-design/business-rules.md`

## Domain Validation checklist (Phase 2)

- [x] DOMAIN-04 — requirements traceability (FR3/FR6/Q2/Q2b/Q6/D10/NFR2/NFR4/NFR1/FR8 all homed)
- [x] DOMAIN-05 — no delegating entities, no service-named value objects, no coined labels, no per-endpoint domain services, no behaviourless aggregates
- [x] DOMAIN-06 — descent audit for every service-shaped component (steps 0-4 tried first)
- [x] DOMAIN-07 — no 1:1 controller→aggregate services; no Manager/Helper/Orchestrator/Facade names
- [x] DOMAIN-08 — no Repository/DAO/store/unit-of-work; persistence on the owning entity
