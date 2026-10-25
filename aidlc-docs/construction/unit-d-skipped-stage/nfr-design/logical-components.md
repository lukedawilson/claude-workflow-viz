# Unit D (skipped-stage visualisation) — Logical Components

Four components, all client-side. No infrastructure elements, no external
integration points, no new dependencies.

- **SkipInference** (static/viz-core.js) — pure function `inferSkipped(graph,
  instances)`; deterministic fixpoint; seam output = skipped id set in reducer
  state.
- **applyClasses extension** (static/app.js) — two added steps in the existing
  SVG pass: status-skipped class application (exclusive of sibling statuses)
  and incoming/outgoing edge greying.
- **Styles** (static/styles.css) — `.status-skipped` (grey dashed stroke,
  muted fill) and the muted-edge class.
- **Node tests** (tests/js/viz-core.test.mjs) — direct skip, transitive chain,
  instance-wins, terminal exclusion, round scoping, interrupted run,
  determinism.
