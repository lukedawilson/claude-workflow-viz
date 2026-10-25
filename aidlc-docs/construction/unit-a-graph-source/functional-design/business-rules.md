# Unit A — Business Rules

The rules the parser enforces. Numbered for traceability; each cites the source
requirement or design answer.

## The subset (FR4, UE-A1)

R1. The executable spec of the parse subset is the parser code (UE-A1). README and /viz
template documentation derive from it; tests pin every rule below.

R2. The parser never guesses (FR4). Every construct outside the subset produces a named
failure; every construct inside it produces a defined graph element. There is no
best-effort mode.

R3. Failure collection is exhaustive (FD1): one pass collects all failures. The report
is the parse result whenever it is non-empty (failures win).

## Labels (FR4, FD4)

R4. A label is supported only if it is a string literal or a template literal whose
interpolations are static-known names, AND the literal part matches the standard
`<slice>/<stage>:r<round>` shape. Anything else — including the `r<round>/<stage>`
shape — is `UnsupportedLabel` (FD4-A: deferred as additive work).

R5. The graph's `step_pattern` remains the default regex; Unit A never emits a custom
pattern.

## Control flow (FR4, FD6, FD7)

R6. Entry: the first agent call site in source order (FD6). No agent call site at all is
a failure.

R7. MAX_ROUNDS: `const MAX_ROUNDS = <int>` maps to `max_rounds`. Absent → 
`MissingMaxRounds`. A non-integer or computed value → `MissingMaxRounds` (strict).

R8. Loop-backs: `continue` returning control to an earlier agent call inside a
`while`/`for` loop maps to the re-entry edge. Control flow that is not expressible
this way → `UnsupportedControlFlow`.

R9. Terminals: an early `return <literal>` maps to the lowercase terminal id (FD3).
Unrecognised literal → `UnsupportedTerminal`. A MAX_ROUNDS loop without an exhaustion
return → `UnsupportedTerminal`; an exhaustion return without MAX_ROUNDS →
`MissingMaxRounds` (FD7).

R10. Conditionals: an agent call guarded by an `if` with no agent call in the else maps
to a normal node (FD2). Agent calls on both branches → `UnsupportedConditional`.

R11. Parallel: `Promise.all` of statically known agent calls maps to parallel nodes.
A non-agent member → `UnsupportedParallel`.

## Graph construction (D5, FD3)

R12. The parser emits exactly the structure `Graph.load` validates — the same node/edge
schema as a hand-authored viz.yaml (D5). Emitting an invalid graph is a bug, not a
failure code: construction-time assertions guarantee it, and tests assert
`Graph.load` accepts every parsed output.

R13. Terminal ids are the lowercase literals `done`, `blocked`, `needs-context` (FD3).

## Serialization (D5, DOMAIN-08)

R14. `Graph.to_yaml()` output is byte-compatible with the hand-authored schema and
round-trips: `Graph.load(Graph.to_yaml(g)) == g`.

## Failure contract (D4, UE-A2)

R15. Each failure carries a machine `code`, human `message`, `location` (file:line), and
`context` (offending line).

R16. Codes are internal until Unit C ships (UE-A2). After that, additive-only.

## Determinism

R17. Parsing is deterministic: same source → same graph or same report (PBT property).

## Out of scope for Unit A

- The skip visual for gated nodes (FR9 → Unit D).
- Custom step_pattern shapes (deferred per R4).
- Everything the /viz agent does with the report (Unit C command, FR5).
