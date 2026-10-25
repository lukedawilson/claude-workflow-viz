# Unit D (skipped-stage visualisation) — Business Rules

- **R1** (FR9.2, UD1-A): a non-terminal node with no instance renders skipped
  when its predecessor is pass or skipped AND a forward-reachable node has
  arrived or the run stopped. Transitive: a skipped predecessor satisfies the
  condition.
- **R2** (UD1 note): a node with an instance is never skipped; pass/fail/running
  wins over the skip derivation.
- **R3** (UD2-B): terminal nodes are excluded from skip inference entirely;
  they only ever show running/pass/fail.
- **R4** (UD3-A): the skipped visual is `status-skipped` — grey dashed node
  stroke, muted fill, readable text — a sibling of the existing status classes.
- **R5** (UD4-A): a skipped node's incoming and outgoing edges grey out.
- **R6** (UD5-A): inference is scoped to the selected slice+round instance
  view; selector changes re-derive the skip set.
- **R7** (UD6-A): the skipped state renders live the moment its trigger fires;
  it is a state, not a verdict.
- **R8** (UED1-A, UED2-A): skip is derived state owned by the reducer; no event
  carries it.
- **R9** (UED3-B): inference and derived state live in the pure core
  (viz-core.js); the class and DOM application live in app.js/styles.css; the
  seam is the `skipped` flag.
- **R10** (UED4-A): the inference is a pure deterministic function of graph and
  instances — no DOM, clocks, or network — and is Node-testable.

## Out of scope

- Python-side changes: none. The server's graph/events are untouched.
- Changing how retry/loop-back/active-edge rendering works (existing
  behaviour preserved).
- Any skip semantics for unmapped steps (unmapped list unchanged).
