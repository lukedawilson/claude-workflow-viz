# Unit A (graph source) — Functional Design Plan

## Steps

- [x] Step 1: Analyze unit context (unit-of-work.md, story map)
- [x] Step 2: Domain Exposition (Domain Standards Phase 1) — focused probes for the
      graph-source domain, citing source requirements
- [x] Step 3: Generate context-appropriate questions (business logic, domain model,
      business rules, error handling) with [Answer]: tags
- [x] Step 4: Store plan (this file)
- [x] Step 5: Collect answers one-by-one in chat; write back to [Answer]: tags;
      analyze for ambiguities; follow up if needed
- [x] Step 6: Generate functional design artifacts:
      - [x] business-logic-model.md
      - [x] business-rules.md
      - [x] domain-entities.md
- [x] Step 7: Domain Validation (Domain Standards Phase 2) on the Unit A model
- [ ] Step 8: Present completion message
- [ ] Step 9: Wait for explicit approval; log in audit.md; update aidlc-state.md

## Domain Exposition (focused, Unit A — graph source)

### UE-A1: Ownership of the parse-subset spec (FR4, FR6)
FR4 defines a strict subset: meta export, literal/literal-static-segment labels,
MAX_ROUNDS, loop-backs, early literal returns, if-guards, Promise.all — everything else
a named failure. FR6 requires the invocation path to be reliable. The subset definition
must have a single source of truth, or the parser and the /viz agent instructions drift.

A) Parser code is the executable spec; the README table and /viz template derive from it
B) README table is the normative spec; the parser implements it and tests pin it
X) Other (please describe after [Answer]: tag below)

[Answer]: A — parser code is the executable spec; the README table and /viz template
derive from it. (User, 2026-10-25T02:32:00Z)

### UE-A2: Failure-code stability contract (FR5, D4)
FR5 makes the /viz agent consume the failure report. D4 names per-construct failure
codes. The codes are the parser↔agent contract; changing them breaks fallback prompts.

A) Codes freeze at first release; changes are additive-only (new codes may appear,
existing ones never change meaning)
B) Codes are internal until unit C ships; free to rename during construction
X) Other (please describe after [Answer]: tag below)

[Answer]: B — codes are internal until unit C ships; free to rename during construction.
(User, 2026-10-25T02:34:00Z)

## Functional Design Questions

### FD1: Failure collection (D4, FR5)
When the parser meets more than one unsupported construct:

A) Collect ALL failures in one pass — the report lists every problem, so the /viz agent
fixes the whole file in one generation round
B) Stop at the first unsupported construct — fail fast, the report names one problem at
a time
X) Other (please describe after [Answer]: tag below)

[Answer]: A — collect ALL failures in one pass, so the /viz agent fixes the whole file
in one generation round. (User, 2026-10-25T02:36:00Z)

### FD2: Conditional agent calls in the graph (FR4)
The viz.yaml schema has no conditional concept — nodes have static on_pass/on_fail. A
conditional call like implement.js's verify-fsm guard means the node runs only when the
runtime guard is true. The graph models structure; the viz already renders a node only
when an instance (step) actually arrives.

A) Represent the guarded node as a normal node with its static edges; the runtime guard
decides whether an instance appears. The graph never encodes the guard condition itself
B) Treat guard-condition parsing as part of the strict subset and reject workflows where
the guard's shape is not understood (UnsupportedConditional); never emit a node whose
conditions we could not parse
X) Other (please describe after [Answer]: tag below)

[Answer]: HYBRID (user, 2026-10-25T02:40:00Z): gating guards (single agent call in the
if; no competing agent in the else) → emit the node as a normal node with static edges;
the runtime guard decides whether an instance appears. Alternative guards (agents on
both branches) → UnsupportedConditional → /viz agent fallback.
USER ADDENDUM (2026-10-25T02:42:00Z): "if a stage is skipped, that should be visually
obvious (e.g. by colouring it)" — new requirement FR9: skipped nodes render with a
distinct visual state, inferred client-side (a gated node with no instance whose
predecessor passed and whose successor arrived/run stopped). PLACEMENT RESOLVED
(2026-10-25T02:46:00Z): new Unit D (skipped-stage visualisation), constructed after C.

### FD3: Terminal mapping (FR4) — STATED DECISION (challenge at review if wrong)
The workflow returns literal outcome names (DONE, BLOCKED, NEEDS_CONTEXT). The graph
schema's terminal ids in the reference example are lowercase (done, blocked,
needs-context). Decision: the parser lowercases literal return values to terminal node
ids; a return value outside the recognised set is UnsupportedTerminal. Rationale:
strictness (never guess) + the existing example convention.

### FD4: Non-standard label shapes (FR4, FR7)
rca.js uses `r${round}/<stage>` (round first). implement.js uses the standard
`<slice>/<stage>:r<round>`.

A) Unit A supports only the standard `<slice>/<stage>:r<round>` shape; anything else is
UnsupportedLabel (strict, keeps unit A small; rca falls back to the /viz agent)
B) Unit A also derives custom step_patterns for known alternative shapes like
`r${round}/<stage>` (broader coverage, larger test matrix)
X) Other (please describe after [Answer]: tag below)

[Answer]: A — standard `<slice>/<stage>:r<round>` shape only; everything else is
UnsupportedLabel. Deferral rationale recorded: shape support is additive; rca.js falls
back regardless (dynamic-depth labels). (User, 2026-10-25T02:50:00Z, after risk
assessment: B is low-risk but currently zero-value.)

### FD5: Fold decisions (open decisions 1-2 from application design)
agent_prompt.py may fold into parse_failures.py (the derivation is a pure projection of
failures).

A) Fold now: failures carry the prompt derivation; one module for the whole report
B) Keep separate: prompt building is its own concern (template content co-evolves with
it — UE3)
X) Other (please describe after [Answer]: tag below)

[Answer]: A — fold now: ParseFailure values carry the prompt derivation; one module
(parse_failures.py) holds the whole report including build_fallback_prompt. (User,
2026-10-25T02:52:00Z)

### FD6: Entry node (FR4) — STATED DECISION
The first `agent()` call site in source order is the graph entry. A workflow with no
parseable agent call is a named failure. Rationale: source order matches the example
yaml's entry semantics.

### FD7: max_rounds / on_rounds_exhausted derivation (FR4) — STATED DECISION
`const MAX_ROUNDS = <int>` maps to `max_rounds`; the loop's exhaustion return (e.g.
`if (round >= MAX_ROUNDS) return BLOCKED`) maps to `on_rounds_exhausted`. Missing
MAX_ROUNDS → MissingMaxRounds; missing exhaustion return → UnsupportedTerminal.

## PBT-01 property candidates (recorded for NFR Requirements)
- to_yaml round-trip: `Graph.load(Graph.to_yaml(g))` equals `g` for every generated graph
- parser invariants: every node reachable from entry; on_pass/on_fail targets exist
- parse determinism: same source → same graph (or same failure list)
