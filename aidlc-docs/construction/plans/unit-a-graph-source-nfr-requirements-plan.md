# Unit A (graph source) — NFR Requirements Plan

## Steps

- [x] Step 1: Analyze functional design (business-logic-model, business-rules,
      domain-entities)
- [x] Step 2: Create NFR assessment plan (this file)
- [x] Step 3: Generate context-appropriate questions with [Answer]: tags
- [x] Step 4: Store plan (this file)
- [x] Step 5: Collect answers one-by-one in chat; write back; analyze for ambiguities
- [x] Step 6: Generate artifacts:
      - [x] nfr-requirements.md
      - [x] tech-stack-decisions.md
- [ ] Step 7: Present completion message
- [ ] Step 8: Wait for explicit approval
- [ ] Step 9: Record approval in audit.md; update aidlc-state.md

## Questions

### NFR-A1: JS parsing tech stack
Unit A parses JavaScript workflow sources. The package's stated runtime-dependency
policy is PyYAML only (reverse engineering: "ONLY runtime dep: pyyaml>=6.0.3"). The
strict subset (labels, meta, MAX_ROUNDS, loops, returns, if-guards, Promise.all) is
small and syntax-local.

A) Hand-rolled stdlib parser (regex/scan-based over source text) — no new dependency;
the subset's strictness makes a lightweight parser feasible and bounded
B) Introduce a real JS parser dependency (e.g. tree-sitter) — more robust against
unusual-but-subset-conformant syntax, at the cost of breaking the one-runtime-dep
policy and adding a build surface
X) Other (please describe after [Answer]: tag below)

[Answer]: A — hand-rolled stdlib parser (regex/scan-based over source text); no new
dependency. Frozen at the R1-R17 subset: anything outside it is a named failure +
agent fallback, not a parser improvement. (User, 2026-10-25T03:15:00Z, after asking
for a recommendation; the never-guess rule converts parser-robustness risk into the
designed fallback path, so a JS parser dependency buys nothing.)

### NFR-A2: Source-size bound
The parser runs inside a hook at workflow invoke time and must never hang or exhaust
memory on hostile or pathological input.

A) Hard cap on workflow source size (1 MiB, mirroring the journal cap) — oversized
input is a named failure, not a parse attempt
B) No cap — workflow files are human-authored and small; the subset scan is
milliseconds anyway
X) Other (please describe after [Answer]: tag below)

[Answer]: B — no cap: workflow files are human-authored and small; the subset scan is
milliseconds anyway. (User, 2026-10-25T03:18:00Z.) Residual risk noted: catastrophic
regex backtracking on pathological input. Mitigation (stated decision): linear-time
scan patterns (no nested quantifiers), and a pathological-fixture test asserting
bounded parse time. SECURITY-06 bounds considered and marked N/A for source size per
this answer — the input is a local, human-authored file, not a network surface.

## Stated decisions (challenge at review)

- **Performance budget**: parsing one workflow (~hundreds of lines) must stay well
  under the hook's 1-second HTTP timeout envelope; no measurable benchmark required.
  The parse runs once per workflow invocation, not per event.
- **PBT-09 framework**: Hypothesis (Python) — mandated by the opted-in extension rule.
- **Security baseline (blocking extension) applies as a review checklist**: input
  validation with bounds — size bound N/A per NFR-A2=B (local human-authored file);
  linear-time scan patterns instead (backtracking mitigation); fail-closed typed
  failures instead of exceptions on hostile input (SECURITY-15); no secrets handled
  by Unit A; no logging of source content outside failure context lines (which flow
  only to the /viz agent prompt, never to server logs).
- **Availability/scalability**: not applicable beyond the bound — single-machine
  desktop tool, one parse per invocation (per the resiliency opt-in, cloud-only rules
  are marked N/A).
