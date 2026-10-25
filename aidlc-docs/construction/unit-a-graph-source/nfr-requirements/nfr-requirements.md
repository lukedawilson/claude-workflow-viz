# Unit A — NFR Requirements

Non-functional requirements for the graph-source unit. This is a pure, local parser
inside a hook; the desktop-tool context drives most answers.

## Performance

- Parse one workflow (hundreds of lines) in milliseconds — far inside the hook's
  1-second HTTP timeout envelope. No measurable benchmark required; the pathological
  fixture test (below) is the guard.
- One parse per workflow invocation (invoke-time), not per event. No scaling model:
  single machine, single user.

## Security (blocking extension, review checklist applied)

- Input source: a local, human-authored workflow file in the invoked repo. Not a
  network surface. SECURITY-06 (input validation bounds): source-size cap considered
  and marked N/A per NFR-A2 — the realistic risk is regex backtracking, mitigated by
  linear-time scan patterns (no nested quantifiers) and a pathological-fixture test
  that asserts bounded parse time.
- Fail-closed: hostile or malformed input yields typed `ParseFailure` values, never
  exceptions, never partial graphs (R2, R3).
- No secrets handled; failure context lines flow only into the /viz agent prompt, and
  the hook's silence contract keeps them out of server logs.
- No new dependencies (NFR-A1) — no new supply-chain surface.

## Reliability

- Deterministic: same source → same graph or same report (R17) — a Hypothesis property.
- Never raises: `WorkflowSource.parse()` returns a value; construction-time assertions
  guarantee the emitted graph passes `Graph.load` validation (R12).

## Maintainability

- The parser is frozen at the R1-R17 subset; extension is a deliberate unit, not
  drift (NFR-A1).
- Fixture corpus: implement.js (full), rca.js (expects UnsupportedLabel on the
  dynamic-depth construct), cross-repo-check.js — real workflows pin the subset.

## Availability / Scalability / Usability

- N/A beyond the bound: desktop tool, local parse (per the resiliency opt-in,
  cloud-only rules are marked N/A).
