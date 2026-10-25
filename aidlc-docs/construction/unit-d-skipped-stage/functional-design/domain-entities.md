# Unit D (skipped-stage visualisation) — Domain Entities

Client-side unit. The pure/presentation split mirrors the existing architecture
(UED3-B): inference and derived state live in `static/viz-core.js`; the visual
lives in `static/app.js` + `static/styles.css`. The seam is the `skipped` flag
in reducer state (UED2-A).

## Concepts

### Skipped flag (derived state, value concept)

A boolean per node instance key `[slice, nodeId, round, stepKey]`, computed in
the pure applyEvent layer (UED1-A, UED2-A), consumed by app.js. It is derived
state, not an event: no event carries it; the reducer derives it from the event
sequence and the graph. Terminal nodes never carry it (UD2-B).

### SkipInference (pure function)

The rule as a pure function (UED4-A): `inferSkipped(graph, instances)` →
set of instance keys. Deterministic — same graph and instances always produce
the same set. No DOM, no clocks, no network. Descent step 0: a plain pure
helper over existing state; no new entity is introduced (the flag is a field on
existing node-instance state).

The rule (UD1-A, FR9.2):

- a non-terminal node with no instance renders skipped when a node reachable
  forward from it has arrived (has an instance) or the run has stopped, AND
  its predecessor along the taken edge is pass or skipped;
- transitive: a predecessor that is itself skipped satisfies the condition, so
  a bypassed tail marks as a whole;
- a node WITH an instance is never skipped — pass/fail/running wins (UD1 note);
- terminals are excluded entirely (UD2-B).

### Status classes (presentation)

- `status-skipped` node class: grey dashed stroke, muted fill, readable text
  (UD3-A).
- Skipped-edge class: the skipped node's incoming and outgoing edges grey out —
  the traversal visibly jumped over the stage (UD4-A).
- Applied by app.js's existing `applyClasses` pass (UED3-B), exactly like the
  existing status-pending/running/retry/pass/fail classes.

## Relationships

```
EventSequence ──applyEvent──► reducer state (instances, statuses)
Graph ──► SkipInference ──► skipped flags (per instance key, non-terminal only)
skipped flags ──app.js applyClasses──► status-skipped node + greyed edges
```

Scoping (UD5-A): inference runs per selected slice+round, re-derived on
selector change, identical to the existing status-class mechanism.
Timing (UD6-A): the flag appears live the moment the trigger fires.
