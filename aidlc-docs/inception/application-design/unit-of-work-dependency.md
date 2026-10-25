# Unit of Work Dependencies

## Dependency matrix

| From / To | A graph source | B hook path / lifecycle | C install | Existing (moved) |
| --- | --- | --- | --- | --- |
| **A graph source** | — | — | — | imports `graph/graph.py`, `graph/parse_failures.py` (own) |
| **B hook path / lifecycle** | uses A: parser + `to_yaml()` at invoke time | — | — | imports `dashboard/connection_file.py`, `dashboard/server.py` (constants), `workflow/events.py`, `workflow/hook_adapter.py` |
| **C install** | template content (packaged, no import) | verify step runs B's dispatcher | — | writes into the target repo's `.claude/` |
| **Existing (moved)** | `graph/` extended with `to_yaml()` | `dashboard/` extended with `/shutdown` + `stop_server()` | unchanged | — |

Runtime import graph (solid = import; dashed = process spawn; no import cycles):

```
cli.py ──► install/installer.py, workflow/hook_command.py,
           dashboard/server.py, graph/graph.py

workflow/hook_command.py ──► invoke/bootstrap.py, invoke/shutdown.py,
                             workflow/hook_adapter.py, workflow/events.py

invoke/bootstrap.py ──► graph_source/parser.py, graph/graph.py,
                        dashboard/connection_file.py
invoke/bootstrap.py ─spawns─► claude_workflow_viz serve (detached process)

invoke/shutdown.py ──► dashboard/connection_file.py

graph_source/parser.py ──► graph/graph.py, graph_source/parse_failures.py
graph_source/agent_prompt.py ──► graph_source/parse_failures.py
```

## Construction sequence

1. **Unit A** (graph source) — no dependencies on B or C. The parser and `to_yaml()`
   exist before anything consumes them.
2. **Unit B** (hook path / lifecycle) — consumes A's parser and `to_yaml()`. Depends on
   A being complete and tested.
3. **Unit C** (install) — no runtime import of A or B, but its verify step runs B's
   dispatcher (empty stdin, exit 0), so it constructs after B.

## Boundary validation

- **Cycle check**: none. Imports flow cli → subpackages → graph/core; `graph_source/`
  and `dashboard/` never import each other; the spawn arrows are process boundaries.
- **Contract check**: the only cross-unit runtime contract is the parser output shape —
  the existing `Graph` structure — which is pinned by D5 and already tested in
  `tests/test_graph.py`. Cross-unit contract test: `Graph.load` accepts
  `Graph.to_yaml()` output (Unit A), and B's transient cache write is that same call.
- **Boundary invariant**: the hook path (B) imports no installer code (C) — install-time
  choices cannot disturb a session. A imports nothing outside `graph/` and its own
  modules.
