# NFR Design Patterns — Unit B (hook path / server lifecycle)

Patterns for the non-functional surface of Unit B. Unit A's six resiliency decisions
(NRA2 = A) apply project-wide and are not re-derived here.

## Resilience

### Shared debug log (NRB1 = A)

One state-dir debug log serves every diagnosis channel in the product: Bootstrap's
failure summaries (R10), the spawned server's stdout/stderr (R3), and Unit A's parser
errors. Same bounds as Unit A: ~1 MiB cap, oldest-truncation, every write
exception-guarded — a failed log write never fails the hook path (NFR2).

### Orphan acceptance (NRB2 = A)

Two concurrent invocations racing inside the spawn window can each miss the connection
file and each spawn a server; one wins the connection file, the other is an orphan
listening on an unused port. Accepted: the window is seconds, the case is rare, and the
orphan dies with the machine or login session. No claim file, no owner-check. Partial
reclamation: the port-selection sweep (below) recycles an orphan holding the preferred
port.

### SessionEnd retry semantics (R14)

A failed stop leaves the server up; the next SessionEnd retries. No backoff needed —
SessionEnd events are the natural retry cadence.

### Silent degradation (R4/R10)

Every hook-path failure exits 0 with no output; degradation is dashboard-visible
(linear mode, unmapped-step warning) or invisible. The debug log is the only diagnosis
channel.

## Port selection (NRB4 = B directive)

Mirrors the agentic-dev-loop mechanism, adapted to the hook path:

1. **Preferred port 8322** (NRB5 = A). Not fixed — a busy port degrades, never fails.
2. **Sweep before bind**, run by Bootstrap (the caller) before spawning, never inside
   the server:
   - find listeners on 127.0.0.1:8322 (lsof `-nP -ti tcp:8322 -sTCP:LISTEN`); lsof
     absent → empty list, silent no-op (Windows);
   - exclude own PID;
   - keep only processes whose command line matches `claude-workflow-viz`;
   - cwd positive-only filter (unknown cwd spared — multi-instance safety);
   - SIGTERM each, re-check every 0.05 s until a 3 s deadline, then SIGKILL survivors.
3. **Bind**: `127.0.0.1:8322` first; on `EADDRINUSE` rebind port 0 (OS picks a free
   port). `allow_reuse_address = sys.platform != "win32"` (Windows SO_REUSEADDR would
   defeat the busy-port fallback).
4. **The actual bound port** goes into `server.json` — the connection file remains the
   single liveness record (R1). Bootstrap and stop_server read it, so a fallback port
   changes nothing downstream.

## Security

### Deny-on-error for /shutdown (NRB3 = A)

No request can stop the server without the token: a bad or missing token returns 401
and the server keeps running; 204 only on authenticated success. A bad request changes
nothing. This is the SECURITY-15 pattern applied at the endpoint.

## Scalability

N/A — one server per machine (R1); the graph registry scales by workflow name count,
held in memory, bounded by the number of distinct workflows invoked between restarts.

## Performance

Fixed bounds, no benchmark (Unit A NFR decision): 1 s timeouts on the reuse probe and
`stop_server()` (NFRB2); 10 s bounded wait for the connection file (R6); steady state is
probe-only. Worst-case invocation latency is bounded by R6.

## Windows CI implications (NFRB4 = B)

The platform open-command selector has a win32 branch (`os.startfile`). The repo has no
CI today; Unit B's code generation adds a GitHub Actions workflow with a
`windows-latest` job exercising the win32 branch and the full suite. On Windows the
sweep silently no-ops (lsof absent) and `allow_reuse_address` is False.
