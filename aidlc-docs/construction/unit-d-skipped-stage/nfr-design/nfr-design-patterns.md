# Unit D (skipped-stage visualisation) — NFR Design Patterns

## Resilience

Client-side rendering only — no server, lifecycle, or hook-path surface. The
six project-wide resiliency decisions apply unchanged. A JS error inside the
pure inference function is contained by the existing rendering try/catch in
app.js; the dashboard degrades to its current (pre-Unit-D) appearance rather
than failing.

## Scalability

N/A — inference runs over one hand-sized graph.

## Performance

Fixpoint inference bounded by nodes × edges per event and guaranteed to
terminate (each pass either marks a node or stops). No benchmark.

## Security

No new surface: CSS classes and SVG attributes flow through the existing
CSP/Mermaid strict mode; no endpoints, inputs, or dependencies.

## Logical components

| Component | Location | Role |
| --- | --- | --- |
| SkipInference | static/viz-core.js | pure fixpoint: skipped set per slice/round |
| applyClasses extension | static/app.js | adds status-skipped + greys edges |
| Styles | static/styles.css | status-skipped + muted-edge classes |
| Node tests | tests/js/viz-core.test.mjs | invariant and edge-case coverage |
