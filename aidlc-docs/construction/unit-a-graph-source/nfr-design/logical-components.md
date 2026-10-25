# Unit A — Logical Components

The logical-component inventory for the graph-source unit.

## Components

| Component | Kind | Purpose | Placement |
| --- | --- | --- | --- |
| `WorkflowSource` | value object (in-process) | parse behaviour over source text | `graph_source/parser.py` |
| `ParseFailure` family | value objects | typed failure values | `graph_source/parse_failures.py` |
| `ParseFailureReport` | value object | collect-all report + fallback prompt | `graph_source/parse_failures.py` |
| `Graph.to_yaml()` | entity method | serialization (DOMAIN-08) | `graph/graph.py` |
| Debug log | state-dir append-only file | internal-bug stack traces (NRA1=B) | state dir (existing convention) |

## Infrastructure elements

None. No queues, caches, circuit breakers, workers, or external services (NRA3 = A).
The debug log is the only file the unit writes; it is exception-guarded, capped at
~1 MiB with oldest-truncation, and never on the hook's streams.

## Integration points

- Input: workflow JS source text handed by the invoke-time caller (Unit B).
- Output: a `Graph` (validated by the existing `Graph.load` contract, R12) or a
  `ParseFailureReport` consumed by Unit B (linear-mode warning) and Unit C's /viz
  command (fallback prompt).
- No HTTP, no subprocess, no filesystem reads beyond the given source text (the
  source path is carried for failure locations only).
