# Unit A — Business Logic Model

The parse algorithm and its outcomes. Technology-agnostic: no HTTP, no filesystem, no
subprocesses; `source_path` is carried for locations only.

## Parse flow

```
read source text
│
├─ 1. Extract meta             export const meta = { name, ... }
│       ├─ missing → MissingMeta (not in subset) → failure
│       └─ name → graph name
├─ 2. Find agent call sites    agent(...) in source order
│       ├─ none → failure (no graph without nodes)
│       └─ first call site → entry node (FD6)
├─ 3. Classify each call site  → node + stage/step_key + edges, or a failure
├─ 4. Classify control flow    MAX_ROUNDS const, loop-backs, exhaustion return,
│                               terminals, conditionals, parallel groups
├─ 5. Build the Graph          node list, entry, max_rounds + on_rounds_exhausted,
│                               step_pattern (default)
└─ 6. If ANY failure collected → return the ParseFailureReport (failures win)
```

Step 6 is the never-guess rule in operation: a partial understanding is not a graph. If
one construct failed while others parsed, the report is the result (FD1 collects all so
the /viz agent fixes everything in one round).

## Node derivation

- A call site with a literal label (`"pre-flight/head-check"`) becomes a step_key node
  matched by that exact label.
- A call site with a literal-static-segment template label
  (`` `${slice.id}/develop:r${round}` ``) becomes a stage node; the stage is the literal
  segment (`develop`); the step_pattern stays the default
  `(?P<slice>[^/]+)/(?P<stage>[^:]+):r(?P<round>\d+)` (FD4: only this shape).
- A guarded call site (agent call inside an `if` with no agent in the else) becomes a
  normal node; the guard is not encoded (FD2). The skip visual is Unit D's concern.
- An `if`/`else` with agent calls on both branches is `UnsupportedConditional` (FD2).

## Edge derivation

- Sequential call sites chain via `on_pass` in source order.
- A `continue` in a `while`/`for` loop that returns control to an earlier call site
  creates the loop-back: the loop body's last node gets `on_fail` (or its natural
  re-entry) pointing back to the re-entered node. The re-entered node's round is the
  loop's iteration (via the label's `r<round>`).
- An early `return <literal>` becomes a terminal edge: `on_pass` or `on_fail` to the
  terminal whose id is the lowercase literal (FD3: `DONE`→`done`, `BLOCKED`→`blocked`,
  `NEEDS_CONTEXT`→`needs-context`). An unrecognised literal is
  `UnsupportedTerminal`.
- `const MAX_ROUNDS = n` → `max_rounds: n`; the exhaustion return inside the loop
  (e.g. `if (round >= MAX_ROUNDS) return BLOCKED`) → `on_rounds_exhausted: blocked`
  (FD7). MAX_ROUNDS without an exhaustion return, or a loop exhaustion without
  MAX_ROUNDS, is a failure (MissingMaxRounds / UnsupportedTerminal).
- `Promise.all([...])` of statically known agent calls → the members become parallel
  nodes (each chaining to the same successor). A member that is not a statically known
  agent call is `UnsupportedParallel`.

## Terminal set

The three recognised outcomes (`done`, `blocked`, `needs-context`) are always present as
terminal nodes when referenced; the graph keeps them reachable from at least one edge.
`Graph` validation (existing) enforces terminal well-formedness.

## Failure precedence

Report wins over graph (step 6). Within the report, every failure is kept — no
deduplication beyond identical (code, location, context) triples, which collapse to one.
Order is source order, so the report reads like the file.
