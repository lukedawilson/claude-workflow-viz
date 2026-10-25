# Unit D (skipped-stage visualisation) — Business Logic Model

## Inference flow

After every `applyEvent`, once node statuses are computed, the reducer derives
the skip set as a fixpoint over the graph:

1. Collect the nodes that have at least one instance in the selected
   slice+round view.
2. Repeatedly mark a node N skipped when all hold:
   - N is non-terminal (UD2-B);
   - N has no instance (UD1 note: an instance always wins);
   - N has an incoming edge from a node already marked pass or skipped
     (transitive closure, UD1-A);
   - the trigger fired: some node reachable forward from N has an instance, or
     the run has stopped (FR9.2, UD6-A).
3. Stop when a pass marks nothing new.

Determinism (UED4-A): the fixpoint is a pure function of graph + instances;
iteration order does not affect the result set.

## Rendering flow (app.js, presentation side)

The existing `applyClasses` pass gains two steps:

1. For every instance key with a skipped flag: add `status-skipped` to the
   node's SVG element (grey dashed stroke, muted fill, readable text — UD3-A).
2. Grey out the node's incoming and outgoing edges (UD4-A).

The pass touches the existing SVG the same way status classes do — no graph
re-render required. Selector changes re-derive the skip set (UD5-A) and re-run
the class pass.

## Interaction with existing states

- A node that later gains an instance leaves the skip set; its classes flip to
  the normal status classes (pass/fail/running). The live skip may be
  contradicted by a loop-back re-entry at a higher round; that re-entry is a
  new instance key, so the old round's skip stands (UD1 note, UD5-A).
- Retry/loop-back and active-edge logic are untouched; skip is an additional
  class, not a status replacement.
- Terminal rendering is unchanged (UD2-B).

## Failure / edge cases

| Case | Behaviour |
| --- | --- |
| Node with an instance | never skipped; normal status classes (UD1 note) |
| Terminal node | never skipped; excluded from inference (UD2-B) |
| Skip chain (A→B both bypassed) | both marked, via the transitive closure (UD1-A) |
| Run interrupted before conclusion | only nodes whose forward-reachable node arrived get skipped; terminals and unreached nodes show nothing new (UD2-B reasoning) |
| Empty graph / no instances | empty skip set |
| Live vs verdict | skip renders the moment the trigger fires (UD6-A); it is a state, not a verdict |
