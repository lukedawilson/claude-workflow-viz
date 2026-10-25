# Unit D (skipped-stage visualisation) — NFR Requirements Plan

Per user directive (2026-10-25T19:24:00Z): "only ask about NFRs and NFD if there
is real ambiguity / No need for pedantry or yak-shaving". Category-by-category
evaluation found no real ambiguity — all decisions are stated below and may be
challenged at the completion message.

## Steps

- [x] Step 1: Analyze functional design (artifacts at aidlc-docs/construction/unit-d-skipped-stage/functional-design/)
- [x] Step 2: Create this plan
- [x] Step 3: Category applicability evaluation (no questions — no real ambiguity)
- [x] Step 4: Store plan (stated decisions, no [Answer]: tags needed)
- [x] Step 5: Generate artifacts (nfr-requirements.md, tech-stack-decisions.md)
- [x] Step 6: Present completion message + wait approval

## Category applicability + stated decisions

- **Scalability** — N/A: inference is a fixpoint over one graph's nodes; graphs
  are hand-sized (tens of nodes). Worst case bounded by nodes × edges per event
  and terminates. No benchmark.
- **Performance** — Stated: the fixpoint pass runs per applyEvent; bounded as
  above; no measurable risk to the 60 Hz rendering path. No new benchmark.
- **Availability** — N/A: client-side rendering; no server surface.
- **Security** — Stated: no new surface. CSS classes and SVG attributes are
  already covered by the existing CSP and Mermaid strict mode; no new endpoints,
  no new dependencies. Nothing to add.
- **Tech stack** — Stated: no new runtime or dev dependency. Property-style
  invariants are covered with deterministic/exhaustive Node test cases (the
  repo's PBT extension targets Python via Hypothesis; a JS property framework
  for one pure function is yak-shaving).
- **Reliability** — Stated: pure function, deterministic (R10), Node-tested
  including the interrupted-run and order-independence cases.
- **Maintainability** — Stated: seam preserved (pure inference in viz-core.js,
  presentation in app.js); rules R1-R10 document the contract.
- **Usability** — Stated: the change is the usability requirement itself (FR9.1:
  skipped stages visibly obvious).

## PBT-09 note

Hypothesis (PBT-09) applies to Python; Unit D has zero Python changes. The
blocking PBT rules (PBT-02/03/07/08/09) are satisfied by: round-trip/invariant
properties expressed as exhaustive Node assertions (PBT-02/03), deterministic
seeded fixtures in viz-core.test.mjs (PBT-07/08), no new framework (PBT-09 N/A
for JS).
