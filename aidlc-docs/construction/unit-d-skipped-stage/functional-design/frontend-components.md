# Unit D (skipped-stage visualisation) — Frontend Components

Client-only unit. The seam (UED3-B): viz-core.js computes the `skipped` flag as
pure state; app.js renders it; styles.css defines the visual. No Python changes.

## Component: SkipInference (static/viz-core.js)

Pure, Node-testable (no DOM, no clocks, no network — UED4-A).

```
inferSkipped(graph, instances) -> Set<nodeId>   # pure, deterministic, fixpoint
```

- Inputs: the graph (nodes, edges, terminals) and the instance map keyed by
  `[slice, nodeId, round, stepKey]`.
- Rule (R1/R2/R3): a node is skipped when it is non-terminal, has no instance,
  and every incoming edge comes from a node that passed or was itself skipped,
  and the trigger holds — some node reachable forwards from it has an instance
  or the run has stopped.
- Computed after each `applyEvent` (derived state, R8); recomputed per selected
  slice + round (R6). The flag lives in reducer state; the reducer's `viewClasses`
  path exposes it the same way `retry`/`loop-back` states are exposed.

## Component: applyClasses extension (static/app.js)

The existing SVG-touching pass gains two steps (no graph re-render):

1. For each node id in the skipped set: add `status-skipped` to its `<g>`
   element; remove the other status classes (`status-pending`, `status-running`,
   `status-pass`, `status-fail`, `status-retry`) so states never stack.
2. Grey the node's incoming and outgoing edges via the existing edge-class
   pass (UD4-A: traversal visibly jumped over).

Interaction flow: render → applyClasses → read skipped set from state → class
pass → edge pass. Slice/round selector change re-runs the same path (UD5-A).
Live behaviour (UD6-A): the grey-out appears the moment the trigger fires —
successor instance arrives or run stops — and disappears only if the node
later gains an instance (R2).

## Styles (static/styles.css)

- `.status-skipped`: grey dashed node stroke, muted fill, text stays readable
  (UD3-A). Sibling of the existing status classes.
- `.edge-skipped` (or reuse of the muted-edge pattern): greyed incoming and
  outgoing edges (UD4-A).

## Node-test coverage (tests/js/viz-core.test.mjs)

- Direct skip (predecessor passed, node has no instance).
- Transitive skip chain (both nodes marked).
- Instance wins (node with an instance is never skipped).
- Terminals excluded.
- Round scoping: higher-round re-entry creates a new instance key; the old
  round's skip inference is unaffected.
- Interrupted run: only forward-reachable nodes whose trigger fired are marked.
- Determinism: same (graph, events) sequence yields the same set, order-independent.
