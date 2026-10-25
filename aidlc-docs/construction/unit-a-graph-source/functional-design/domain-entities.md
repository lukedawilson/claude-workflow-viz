# Unit A — Domain Entities

Domain model for the graph-source unit. All concepts come from the requirement
vocabulary (FR3, FR4, FR5, D4, D5); none are coined.

## WorkflowSource (value object)

The workflow's JavaScript source text, plus where it came from (`source_path`).

- Immutable once constructed.
- Carries the parsing behaviour: `parse() -> Graph | ParseFailureReport`.
- Pure: same source always produces the same `Graph` or the same report (parse
  determinism — a PBT-01 property).
- Owns the executable spec of the parse subset (UE-A1: parser code is the authoritative
  subset definition; README table and /viz template derive from it).

## ParseFailure (value object family)

One per unsupported-construct class:

- `UnsupportedLabel` — a label that is neither literal nor a literal-static-segment
  template, or that does not match the standard `<slice>/<stage>:r<round>` shape (FD4).
- `MissingMaxRounds` — no `const MAX_ROUNDS = <int>` found (FD7).
- `UnsupportedControlFlow` — control flow the subset does not model.
- `UnsupportedTerminal` — an early return whose literal is not a recognised outcome,
  or a missing exhaustion return on a MAX_ROUNDS loop (FD3, FD7).
- `UnsupportedConditional` — an if/else with agent calls on both branches (FD2 hybrid).
- `UnsupportedParallel` — a `Promise.all`-shaped group whose members are not all
  statically known agent calls.

Each value carries: `code` (machine string, e.g. `unsupported-label`), `message`
(human-readable), `location` (file:line), `context` (the offending source line).

Codes are internal until Unit C ships (UE-A2); free to rename during construction.

## ParseFailureReport (value object)

The collected failures of one parse attempt (FD1: collect ALL failures in one pass).

- Ordered by source location.
- `summarise()` — one line per failure, for logs and the linear-mode warning.
- `build_fallback_prompt(workflow_path, viz_dir)` — the /viz agent prompt derived from
  the failures (FD5: folded in; the report owns its projection). Pure derivation:
  failure summary + viz.yaml schema reference + target path + the instruction that the
  written yaml must load under `Graph.load` with zero errors.

## Graph (existing entity, extended)

`Graph.to_yaml()` — the entity's own serialization (DOMAIN-08: persistence lives on the
owning entity). Output is byte-compatible with the hand-authored schema and round-trips
losslessly (D5: `Graph.load(Graph.to_yaml(g)) == g` — a PBT-01 property).

## Relationships

```
WorkflowSource ──parse()──► Graph                 (success: strict subset satisfied)
WorkflowSource ──parse()──► ParseFailureReport    (failure: report collects all)
ParseFailureReport ──build_fallback_prompt()──► str   (feeds the /viz agent)
Graph ──to_yaml()──► str ──Graph.load()──► Graph      (round-trip, same contract)
```

No entities delegate behaviour to each other; `WorkflowSource` computes, it does not
proxy. No service-named value objects (DOMAIN-05): failures are named for the construct
class they reject.
