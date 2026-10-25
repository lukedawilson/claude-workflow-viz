# Unit D (skipped-stage visualisation) — NFR Requirements

Client-only visual change. No real ambiguity found; all positions stated.

## Performance

The skip inference is a fixpoint over one graph (tens of nodes), computed after
each applyEvent and bounded by nodes × edges per pass; it terminates. No
measurable impact on the rendering path. No benchmark.

## Security

No new surface: CSS classes and SVG attributes are covered by the existing CSP
and Mermaid strict mode. No endpoints, no secrets, no dependencies.

## Reliability

Pure function (R10), deterministic and order-independent; Node-tested for
direct skip, transitive chains, instance-wins, terminal exclusion, round
scoping, interrupted run, and determinism.

## Maintainability

The pure/presentation seam holds: inference in viz-core.js, class pass in
app.js, styles in styles.css. Rules R1-R10 document the contract.

## Availability / Scalability

N/A — client-side rendering only; the input graph is hand-sized.

## Usability

FR9.1 is itself the requirement: skipped stages visibly obvious.

## PBT coverage

- PBT-02/03 (round-trip/invariants): exhaustive Node assertions on the pure
  inference function.
- PBT-07/08 (generators/shrinking/seeds): deterministic fixture cases in
  tests/js/viz-core.test.mjs; shrinking N/A for exhaustive small domains.
- PBT-09 (framework): Hypothesis is Python-only; Unit D has zero Python
  changes. No JS property framework added (yak-shaving).
