# Unit D (skipped-stage visualisation) — Tech Stack Decisions

1. **No new runtime dependency** — the feature is CSS classes plus a pure
   function; the existing vendored Mermaid and hand-written viz-core.js/app.js
   suffice.
2. **No new dev dependency** — deterministic/exhaustive Node test cases via the
   existing node:test runner; no JS property-based framework.
3. **No Python changes** — Hypothesis (PBT-09) does not apply to this unit.
4. **Existing styling mechanism** — `status-skipped` joins the sibling status
   classes; edges reuse the existing edge-class pass in applyClasses.
