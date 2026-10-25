# Unit A — Tech Stack Decisions

## Decision 1: Hand-rolled stdlib parser (NFR-A1 = A)

- **Chosen**: regex/scan-based parsing over workflow source text, Python stdlib only.
- **Rejected**: tree-sitter (or any JS parser dependency).
- **Rationale**: the subset (R1-R17) is syntax-local; the never-guess rule means an
  imperfect matcher degrades to a named failure + agent fallback instead of a wrong
  graph, so parser robustness beyond the subset has no payoff. Preserves the
  PyYAML-only runtime-dependency policy; no native builds, no second language runtime,
  no new supply-chain surface.
- **Consequence**: patterns must be linear-time (no nested quantifiers) to bound
  backtracking; pathological fixtures test this.

## Decision 2: No source-size cap (NFR-A2 = B)

- **Chosen**: no hard cap on workflow source size.
- **Rationale**: workflow files are human-authored and small; the scan is
  milliseconds. The residual risk (pathological regex backtracking) is handled by
  Decision 1's pattern discipline and fixture tests rather than a size gate.
- **Consequence**: the only input bound is the OS-level reality of reading a local
  file; SECURITY-06 bounds marked N/A for size.

## Decision 3: Hypothesis for property-based tests (PBT-09)

- **Chosen**: Hypothesis (Python) — mandated by the opted-in property-based-testing
  extension rule for Python projects.
- **Scope (PBT Partial opt-in)**: round-trip property for `Graph.to_yaml()`
  (`Graph.load(Graph.to_yaml(g)) == g`), parser invariants (every node reachable from
  entry; every on_pass/on_fail target exists), parse determinism, and
  shrink-then-embed: shrunk failures become permanent example tests.

## Decision 4: Existing stack everywhere else

- `Graph`, `Graph.load`, `GraphError` (21 typed codes) — reused unchanged; `to_yaml()`
  is the only addition.
- PyYAML stays the only runtime dependency; pytest + ruff + node --test unchanged.
- No frontend work in Unit A (FR9/Unit D owns skip visuals).

## Decision 5: Failure-code namespacing (UE-A2 = B)

- Codes are internal strings until Unit C ships; free to rename during construction.
  The /viz template content is generated alongside the codes in the same module
  (FD5 fold), so rename risk is contained to one file.
