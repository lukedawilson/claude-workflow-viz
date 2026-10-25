# NFR Design Plan — Unit B (hook path / server lifecycle)

Per nfr-design.md (construction). Five categories: resilience, scalability, performance,
security, logical components — each evaluated for applicability with justification.

## Steps

- [x] Step 1: Analyze NFR requirements (unit-b-hook-path/nfr-requirements/ artifacts + Unit B FD R1-R14)
- [x] Step 2: Category applicability assessment
- [x] Step 3: Design questions NRB1-NRB3
- [x] Step 4: Collect answers, write back, ambiguity analysis
- [x] Step 5: Artifacts — nfr-design-patterns.md, logical-components.md
- [ ] Step 6: Completion message + explicit approval; log in audit.md; update aidlc-state.md

## Category applicability

| Category | Applicable | Justification |
| --- | --- | --- |
| Resilience | Yes | New failure surfaces: stop failure, spawn failure, wait timeout, double-spawn race. Unit A's six resiliency-baseline user decisions (NRA2 = A) are project-wide and are NOT re-asked here. |
| Scalability | N/A | One server per machine (R1); no horizontal concerns. |
| Performance | Confirm-only | Bounds already fixed: 1s probe/stop timeouts, 10s spawn wait (R6). No benchmark; the spawn cost is one-time per server lifetime. |
| Security | Yes | /shutdown deny-on-error pattern confirmation (SECURITY-15); debug-log secrets check (SECURITY-03). |
| Logical components | Yes | Derived table — no question needed. |

## Questions

### NRB1 — The state-dir debug log now has three writers

Source: Unit A NRA1-B (debug log, ~1 MiB cap, exception-guarded) + Unit B R3
(server stdout/stderr → state-dir log) + R10 (parser failure summary in the log).
Bootstrap's failure summary, the spawned server's stdout/stderr, and Unit A's parser
errors all need a diagnosis channel. Same file or separate?

A) One shared log file in the state dir: same ~1 MiB cap, same oldest-truncation,
   every write exception-guarded.
B) Two files: the server's process output in one, Bootstrap's failure summaries in
   another.

[Answer]: A — one shared log file in the state dir, same ~1 MiB cap and oldest-truncation, every write exception-guarded (2026-10-25T14:58:00Z)

### NRB2 — The double-spawn race

Source: R1 (liveness = server.json + probe) + R11 (reuse when live).
Two PreToolUse hooks from two different sessions can both find no connection file
within the same spawn window. Both spawn `serve --port 0`; the connection file write
is atomic, so one wins; the loser server runs orphaned on an unused port and
SessionEnd can never find it. What should happen?

A) Accept the orphan — the window is seconds, the case is rare, and the orphan dies
   with the machine/login session.
B) Atomic claim: the first spawner writes a claim file in the state dir; the second
   sees it, waits, and re-reads the connection file instead of spawning.
C) The server checks at startup whether a connection file from a concurrent start
   already exists and exits if it is not the owner.

[Answer]: A — accept the orphan: the window is seconds, the case is rare, the orphan dies with the machine/login session (2026-10-25T15:00:00Z)

### NRB3 — /shutdown deny-on-error confirmation

Source: SECURITY-15 (NFRB1 review). The /shutdown handler returns 401 and the server
keeps running on any validation failure; 204 only on authenticated success.

A) Confirm deny-on-error as the pattern — no request can stop the server without the
   token, and a bad request changes nothing.
B) Different semantics (describe below).

[Answer]: A — deny-on-error confirmed: no request can stop the server without the token; a bad request changes nothing (2026-10-25T15:16:00Z)

## Mandatory artifacts (after answers)

- `aidlc-docs/construction/unit-b-hook-path/nfr-design/nfr-design-patterns.md`
- `aidlc-docs/construction/unit-b-hook-path/nfr-design/logical-components.md`
