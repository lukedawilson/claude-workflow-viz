# NFR Requirements Plan — Unit B (hook path / server lifecycle)

Per nfr-requirements.md (construction) + opted-in extensions: Security baseline (blocking),
PBT partial (PBT-09 = Hypothesis, already decided at Unit A), Resiliency minimal (decisions
already made at Unit A, reused here). Unit B carries open decision 3: the /shutdown security
review (NFR1).

## Steps

- [x] Step 1: Analyze FD context (functional-design/ artifacts, R1-R14, NFR1/NFR2/NFR4/FR8 assignments)
- [x] Step 2: Category evaluation (8 categories; applicability justified)
- [x] Step 3: Context questions (NFRB1-NFRB4 all answered) NFRB1-NFRB4 (one-by-one in chat)
- [x] Step 4: Answer analysis (all concrete; NFRB4 clarification chain resolved; no follow-ups) + write-back
- [x] Step 5: Artifacts — nfr-requirements.md + tech-stack-decisions.md (+ /shutdown SECURITY review section)
- [ ] Step 6: Completion message + explicit approval + explicit approval; log in audit.md; update aidlc-state.md

## Category applicability (stated, challenge at review)

| Category | Applicability |
| --- | --- |
| Scalability | N/A — one server per machine by design (R1); no multi-server, no load |
| Performance | No benchmark. Hooks are async (no workflow stall); reuse probe is a single localhost GET; spawn path adds process start only. Worst case (spawn + wait) is bounded by R6's 10s. |
| Availability | N/A — desktop tool, localhost server, not a served product |
| Security | APPLICABLE — /shutdown endpoint (open decision 3) + spawn log path + SessionEnd stop (NFR1) |
| Tech stack | APPLICABLE — spawn mechanism, browser-open platform support |
| Reliability | APPLICABLE — timeout values, retry semantics (R14), silent-degradation paths (R4/R10) |
| Maintainability | Applicable (no question needed) — dispatcher is the single branch point; silence contract in one place; fold done (UB1) |
| Usability | Applicable (no question needed) — auto-open (Q2b/R7), dashboard-only degradation (UEB5), re-invoke recovery (R6) |

## Questions

### NFRB1 — Security: does /shutdown need more than the /ingest checks?

Source: open decision 3 + NFR1 + SECURITY extension (blocking). The endpoint gets:
Bearer token required, Host allowlist, loopback-only bind, no request body, 401/204.

A) The /ingest-equivalent checks suffice. The token is the authorisation (deny-by-default
   holds); the endpoint has no input beyond the header; the client is the SessionEnd
   hook, not the network. The SECURITY review finds no additional requirement.
B) Additional protection is needed (describe which rule and why).

[Answer]: A — the /ingest-equivalent checks suffice (2026-10-25T14:32:00Z)

### NFRB2 — Reliability: timeout values

Source: R8/R11 + reliability. `stop_server()` and the reuse probe POST/GET to localhost.

A) 1 second each — mirrors the existing /ingest POST timeout; a dead server answers
   nothing and 1s is generous for loopback.
B) Different values (probe and stop named separately).

[Answer]: A — 1 second each (2026-10-25T14:34:00Z)

### NFRB3 — Tech stack: how does Bootstrap spawn the server?

Source: FR6 (detached spawn) + tech stack.

A) `sys.executable -m claude_workflow_viz serve ...` — robust under pipx: uses the very
   interpreter the hook runs on; independent of PATH.
B) The console script `claude-workflow-viz serve ...`.

[Answer]: A — sys.executable -m (2026-10-25T14:36:00Z)

### NFRB4 — Tech stack: which platforms does the browser-open support?

Source: Q2b/R7 (`open`/`xdg-open`) + tech stack.

A) macOS + Linux only (`open` / `xdg-open`); anything else is documented as unsupported
   and the hook degrades silently (R4).
B) Add Windows support (`start`) now.

[Answer]: B — add Windows support via os.startfile, AND add a test that runs in GitHub CI on a Windows environment (2026-10-25T14:40:00Z, after "How much extra effort is it do to B?" → effort assessed ~30-60 min, shipped-unverified-on-Windows caveat; user chose B with the CI condition)

## Mandatory artifacts (after answers)

- `aidlc-docs/construction/unit-b-hook-path/nfr-requirements/nfr-requirements.md`
- `aidlc-docs/construction/unit-b-hook-path/nfr-requirements/tech-stack-decisions.md`
- SECURITY-01..15 checklist review of /shutdown + spawn log path (blocking finding format)
  inside nfr-requirements.md
