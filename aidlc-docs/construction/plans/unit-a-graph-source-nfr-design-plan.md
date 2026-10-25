# Unit A (graph source) — NFR Design Plan

## Steps

- [x] Step 1: Analyze NFR requirements (nfr-requirements.md, tech-stack-decisions.md)
- [x] Step 2: Create NFR design plan (this file)
- [x] Step 3: Generate context-appropriate questions across all five categories
      (resilience / scalability / performance / security / logical components)
- [x] Step 4: Store plan (this file)
- [x] Step 5: Collect answers; write back; analyze for ambiguities
- [x] Step 6: Generate artifacts:
      - [x] nfr-design-patterns.md
      - [x] logical-components.md
- [ ] Step 7: Present completion message
- [ ] Step 8: Wait for explicit approval
- [ ] Step 9: Log approval; update aidlc-state.md

## Category applicability (evidence from NFR requirements)

- Resilience: APPLICABLE — deferred resiliency-baseline user-decision questions land
  here (RESILIENCY-02/03/04/08/14/15).
- Scalability: desktop tool, single machine — questions asked for the record, expected
  N/A.
- Performance: ms parse, no explicit budget beyond the 1s hook timeout.
- Security: threat model = local human-authored files; Unit A adds no network surface.
- Logical components: expected none (no queues/caches/circuit breakers for a pure
  in-process parser) — questions asked for the record.

## Questions

### NRA1: Parser internal-error handling (Resilience Pattern)

`WorkflowSource.parse()` never raises on bad input (typed failures). But an internal
bug — an exception from a buggy branch — must not crash the hook. The dispatcher's
silence wrapper swallows everything. The question is whether anything is recorded.

A) Silent swallow — the hook contract's purity is absolute; nothing is written anywhere
B) Debug log to the state dir — swallow for the hook, but append a stack trace to a
state-dir log file so a broken graph has a diagnosable cause
X) Other (please describe after [Answer]: tag below)

[Answer]: B — debug log to the state dir: swallow for the hook, but append a stack
trace to a state-dir log file so a broken graph has a diagnosable cause.
(User, 2026-10-25T03:30:00Z)

### NRA2: Resiliency-baseline user decisions (RESILIENCY-02/03/04/08/14/15)

The resiliency baseline requires the model to ask, not decide. For a single-machine
desktop tool these are the proposed answers — confirm each or override:

- RESILIENCY-02 (RTO/RPO + DR strategy): N/A — reinstall the wheel / regenerate the
  graph; no backup strategy beyond git history
- RESILIENCY-03 (change management): AI-DLC units — each parser-subset change is a
  planned unit with its own design artifacts
- RESILIENCY-04 (CI/CD, rollback, deployment style): dev loop runs tests; rollback =
  reinstall previous wheel; deployment = `pipx install --force` from a checkout
- RESILIENCY-08 (regional topology): N/A — single machine, no regions
- RESILIENCY-14 (resiliency testing): the pathological-fixture + determinism tests ARE
  the resiliency tests; no chaos/load testing
- RESILIENCY-15 (incident response): N/A — single user, no on-call; failures surface
  as parse failures or the linear-mode fallback

A) Confirm all six as proposed
X) Other (please describe after [Answer]: tag below)

[Answer]: A — confirm all six as proposed. (User, 2026-10-25T03:32:00Z)

### NRA3: Scalability, performance, security, logical components (for the record)

Confirm the desktop-tool profile for Unit A:

A) Confirm — no scaling mechanisms; performance governed by the 1s hook timeout and
the pathological-fixture test; no new security surface (local files only, no secrets);
no logical components (no queues, caches, or circuit breakers for an in-process
parser)
X) Other (please describe after [Answer]: tag below)

[Answer]: A — confirm. (User, 2026-10-25T03:34:00Z)