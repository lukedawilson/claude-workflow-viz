# NFR Requirements — Unit B (hook path / server lifecycle)

## Security (NFR1 — blocking extension; /shutdown review, open decision 3 closed by NFRB1)

The `/shutdown` endpoint carries the /ingest-equivalent checks (NFRB1 = A): Bearer token
required (deny-by-default), Host allowlist, loopback-only bind, no request body, 401/204.

SECURITY-01..15 checklist applied to the new surface:

| Rule | Verdict |
| --- | --- |
| SECURITY-01 encryption at rest/transit | N/A — loopback-only HTTP; the only credential at rest is the existing `server.json` (0600 in a 0700 dir). Nothing new. |
| SECURITY-02 access logging | N/A — the server deliberately logs no requests (log_message silenced to protect the token); /shutdown inherits. |
| SECURITY-03 app logging — no secrets | APPLICABLE — the token never appears in the state-dir log or any command line: the spawn command is `serve --port 0 --graph <path>` (the server reads `server.json` itself); the dashboard URL with token is passed to the browser-open, never logged. |
| SECURITY-04 HTTP security headers | APPLICABLE — inherited: the server's existing hardened CSP/nosniff headers cover /shutdown responses. |
| SECURITY-05 input validation | APPLICABLE — no body accepted (a body is not read or deserialised); the token header is compared with `hmac.compare_digest`. |
| SECURITY-06 bounds | APPLICABLE — no body, no size surface beyond the header; nothing to bound. |
| SECURITY-07 least-privilege IAM | N/A — desktop tool, no cloud principal. |
| SECURITY-08 network deny-by-default | APPLICABLE — inherited: 127.0.0.1-only bind + Host allowlist. |
| SECURITY-09 authz deny-by-default | APPLICABLE — token required; 401 otherwise; no unauthenticated shutdown. |
| SECURITY-10 IDOR / CORS | N/A — no multi-tenant objects; no CORS enabled. |
| SECURITY-11 hardening (no default creds, no stack traces) | APPLICABLE — token generated via `secrets.token_urlsafe(32)` (existing); shutdown handler never emits stack traces (log_message silenced; 401/204 only). |
| SECURITY-12 supply chain | APPLICABLE — no new dependencies; `os.startfile`, `subprocess`, `sys` are stdlib. |
| SECURITY-13 rate-limiting / misuse cases | N/A with justification — the token is already the crown jewel: whoever holds it can read the whole event stream. Shutdown adds nothing beyond stop. No rate limit (the only client is the SessionEnd hook). |
| SECURITY-14 alerting / monitoring | N/A — desktop tool. |
| SECURITY-15 exception handling, deny on error | APPLICABLE — the handler denies on error: bad/missing token → 401 and the server keeps running; only a successful authenticated request stops the server (204). |

**Security findings: none.**

## Reliability (NFR2 / NFR4)

- Never-fails invariant: every dispatcher branch ends with exit 0 and no output (R4/R13).
- Timeouts: 1s for both `stop_server()` and the reuse probe (NFRB2 = A), mirroring /ingest.
- Bounded wait: 10s for `server.json` after spawn, silent timeout (R6, UB3).
- Degradation: parse failure → linear-mode server; dashboard shows the unmapped-step
  warning; the state-dir debug log carries the failure summary (R10).
- Retry semantics: a failed SessionEnd stop leaves the server up; the next SessionEnd
  retries (R14). No handshake for the async PreToolUse race (R12, UB4).

## Performance

No benchmark. Hooks are async (no workflow stall). The reuse path is one localhost GET;
the spawn path adds one process start. Worst case bounded by R6's 10s wait; steady state
is the probe-only path.

## Availability / Scalability

N/A — desktop tool; one server per machine by design (R1); no multi-server, no load.

## Maintainability

Single branch point (dispatcher, D10); silence contract in one place (run_hook wrapper);
SessionEnd branch folded inline (UB1 = A). README gains the invoke-time and /shutdown
sections (FR8 content half).

## Usability

Auto-open on all three platforms (NFRB4 = B); dashboard-only degradation (UEB5);
re-invoking the workflow recovers from a missed spawn (R6).

## Property-based testing (PBT partial — PBT-09 Hypothesis, decided at Unit A)

Targets for Unit B's pure functions:

1. Dispatch selection — every payload maps to a defined branch action (forward-only /
   bootstrap-then-forward / stop-no-forward).
2. Platform open-command selection — total over platform identifiers: darwin → `open`,
   win32 → `os.startfile`, anything else → `xdg-open`.

## Windows CI (new requirement from NFRB4 = B)

The Windows browser-open path must be exercised in CI on a Windows runner. The repo has
no `.github/workflows` today; Unit B code generation adds a GitHub Actions workflow with
a `windows-latest` job that runs the suite, including the win32 branch of the
open-command selection and the `os.startfile` call. (The dev loop itself tests on macOS;
the Windows job runs on push.)
