# Unit D (skipped-stage visualisation) — NFR Design Plan

Per user directive (2026-10-25T19:24:00Z, extended 19:32:00Z): stated decisions,
questions only on real ambiguity. None found.

## Steps

- [x] Step 1: Analyze NFR requirements (unit-d-skipped-stage/nfr-requirements/)
- [x] Step 2: Create this plan
- [x] Step 3: Category applicability (stated decisions below)
- [x] Step 4: Store plan
- [x] Step 5: Generate artifacts (nfr-design-patterns.md, logical-components.md)
- [x] Step 6: Present completion message + wait approval

## Category decisions (stated)

- **Resilience** — N/A: client-side rendering, no server/lifecycle surface.
  The six project-wide resiliency decisions (NRA2-A) apply and are not re-asked.
  Failure of inference cannot crash the hook path or server; a JS error in the
  pure function is caught by the existing rendering try/catch in app.js.
- **Scalability** — N/A: hand-sized graphs.
- **Performance** — Stated: fixpoint bounded by nodes × edges per event,
  terminating; no benchmark.
- **Security** — Stated: no new surface; classes and attributes under existing
  CSP/Mermaid strict mode.
- **Logical components** — Four: SkipInference (viz-core.js, pure),
  applyClasses extension (app.js), styles additions (styles.css), Node tests
  (tests/js/viz-core.test.mjs). Same shapes as frontend-components.md.
