# Unit D (skipped-stage visualisation) — Functional Design Plan

Unit D = FR9: stages that never ran render in a distinct skipped state, inferred
client-side (FR9.2) — a node with no instance whose predecessor passed and whose
successor arrived or the run stopped. Client-only unit: `static/viz-core.js`
(pure inference), `static/app.js` (class application), `static/styles.css`,
Node tests. Vertical-slice check: ships a visible change (skipped stages become
obvious in the dashboard).

## Steps

- [x] Step 1: Analyze unit context (unit-of-work.md, story map, FR9 in
      requirements.md, current viz-core.js reducer)
- [x] Step 2: Create this plan with checkboxes
- [x] Step 3: Domain Exposition Phase 1 questions (UED1-UED4) — one-by-one
- [x] Step 4: Store plan with [Answer]: tags
- [x] Step 5: Collect answers + write back + ambiguity analysis
- [x] Step 6: Design questions (UD1-UD6) — one-by-one
- [x] Step 7: Generate artifacts (domain-entities.md, business-logic-model.md,
      business-rules.md, frontend-components.md) under
      aidlc-docs/construction/unit-d-skipped-stage/functional-design/
- [x] Step 8: Domain Validation Phase 2 (DOMAIN-04..08)
- [ ] Step 9: Present completion message + wait for explicit approval
- [ ] Step 10: Log approval + update aidlc-state.md

## Domain Exposition questions (Phase 1, DOMAIN-01)

### UED1 — bounded-context placement of skip inference

Skip inference is pure logic in the client's reducer state (viz-core.js is the
pure, Node-testable core). Is skip status part of the existing run-observation
state or a new concept?

A) Part of the existing client state: skip is derived state of nodes and steps
   in the same reducer; no new context
B) A new bounded context in the client (inference engine separate from the
   reducer)

[Answer]: A — part of the existing client state: skip is derived state of nodes and steps in the same reducer; no new context (2026-10-25T18:36:00Z)

### UED2 — state ownership of skip status

Who owns the skipped flag once inferred?

A) The reducer state owns it as derived state: computed in the pure applyEvent
   layer, stored per node instance/step, consumed by app.js for styling
B) app.js computes it at render time; the reducer stays skip-unaware

[Answer]: A — the reducer state owns it as derived state: computed in the pure applyEvent layer, stored per node instance, consumed by app.js for styling (2026-10-25T18:40:00Z)

### UED3 — change-togetherness of inference, styling, and rendering

The skip rule, the CSS class, and the DOM application are three pieces.

A) They change together: one bounded context in the client (inference + class
   + apply-to-SVG co-evolve with the reducer)
B) Inference (pure) is separate from styling (presentation) as two contexts

[Answer]: B — inference (pure) is separate from styling (presentation) as two contexts; the seam is the `skipped` flag in state (2026-10-25T18:46:00Z)

### UED4 — actors and invariants of the inference

The inference must be deterministic and Node-testable (pure).

A) Confirm: pure function of the event sequence and graph — same input events
   and graph always produce the same skip set; no DOM, no clocks, no network
B) The inference may use wall-clock time (e.g. "no event for N seconds =
   skipped") which is harder to test

[Answer]: A — confirm: pure function of the event sequence and graph; same input always produces the same skip set; no DOM, clocks, or network (2026-10-25T18:50:00Z)

## Design questions (Phase 2)

### UD1 — the skip rule

FR9.2: a node with no instance whose predecessor passed and whose successor
arrived or the run stopped. Transitive case: a chain where the skipped node's
predecessor was itself skipped.

A) The rule applies transitively: if a node's predecessor is skipped, that
   node also renders skipped when its successor arrives
B) The rule is local: only nodes whose direct predecessor passed count;
   transitively-skipped successors get no special state

[Answer]: A — the rule applies transitively: predecessor passed-or-skipped, node has no instance, successor arrived or run stopped; never propagates into a node with an instance (2026-10-25T18:58:00Z)

### UD2 — terminals that never fired

Terminal nodes (done/blocked/needs-context) have no successor. When a run
stops without reaching a terminal, does the terminal render skipped?

A) Yes: on run end, any terminal with no instance and no arriving edge renders
   skipped
B) No: terminals only show running/pass/fail; absence of an instance is
   already meaningful, no skipped state

[Answer]: B — terminals only show running/pass/fail; the skip inference excludes terminal nodes entirely (2026-10-25T19:05:00Z)

### UD3 — the skipped visual

What does skipped look like?

A) Grey dashed node stroke with muted fill; text stays readable; a
   `status-skipped` CSS class like the existing status classes
B) Dimmed opacity on the node only, no stroke change
C) A distinct colour (e.g. amber) rather than grey

[Answer]: A — grey dashed node stroke with muted fill; text stays readable; a `status-skipped` class like the existing status classes (2026-10-25T19:09:00Z)

### UD4 — edges of skipped nodes

A) Both the node and its incoming/outgoing edges grey out (the traversal
   visibly "jumped over" the stage)
B) Only the node changes; edges keep their existing classes

[Answer]: A — both the node and its incoming/outgoing edges grey out (the traversal visibly jumped over the stage) (2026-10-25T19:13:00Z)

### UD5 — slice/round scoping

Skip inference is per instance key (slice, round). Does the selector interplay
change?

A) No change: inference runs per selected slice+round, exactly like the
   existing status classes; switching slice/round re-derives
B) Inference runs across all slices at once and the selector filters the
   result

[Answer]: A — no change: inference runs per selected slice+round like the existing status classes; switching re-derives (2026-10-25T19:17:00Z)

### UD6 — when skip appears

A) Live: as soon as a successor arrives (or the run stops), the skipped state
   renders immediately — matches FR9.2
B) Only after the run stops: skip is a verdict, not a live state

[Answer]: A — live: as soon as a successor arrives (or the run stops), the skipped state renders immediately (2026-10-25T19:21:00Z)
