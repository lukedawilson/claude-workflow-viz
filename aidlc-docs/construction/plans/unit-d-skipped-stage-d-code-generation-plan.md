# Unit D (skipped-stage visualisation) — Code Generation Plan

Client-only unit. TDD red-first per step. Plan filename carries the `-d-`
middle segment for the dev-loop engine glob.

## Steps

- [ ] Step 1: RED — extend tests/js/viz-core.test.mjs with the seven inference
      cases (direct skip, transitive chain, instance-wins, terminal exclusion,
      round scoping, interrupted run, determinism). Run `node --test` → confirm
      failures.
- [ ] Step 2: GREEN — `inferSkipped(graph, instances)` in static/viz-core.js:
      pure fixpoint per R1-R3, seam output = skipped id set in reducer state.
- [ ] Step 3: GREEN — app.js applyClasses extension: status-skipped class
      (exclusive of sibling statuses) + incoming/outgoing edge greying.
- [ ] Step 4: GREEN — styles.css: `.status-skipped` (grey dashed stroke, muted
      fill) + muted-edge class.
- [ ] Step 5: REFACTOR + VERIFY — `node --test` green; full pytest run still
      green (no Python changes expected).
- [ ] Step 6: README — mention the skipped-stage styling in the Web UI section
      (FR9 visible feature, FR8 content half).
- [ ] Step 7: N/A — API / Repository / Database / Deployment layers.
- [ ] Step 8: aidlc-docs/construction/unit-d-skipped-stage/code/summary.md.

## Out of scope

- Python changes of any kind.
- Graph config, server, hooks, installer (Units A/B/C).
- Build and Test global gate (runs after all units).
