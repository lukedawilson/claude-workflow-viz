# 000 - Move the existing flat modules into DDD folders

> **Status: COMPLETED**

> **For agentic workers:** Use bite-sized task execution to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Decision record

User (verbatim, 2026-10-25, during AI-DLC Application Design Q&A D7): "They should all
be in the same wheel, but can be organised into ddd-style subfolders. Propose a
structure." Then, on the proposal that deferred moving the existing modules:
"We should move these first. Write up a planning document, planning-docs/NNN.....md,
to move them."

Resolved: move the nine existing flat modules of `claude_workflow_viz` into DDD-style
subfolders named after domain concepts — `workflow/`, `graph/`, `dashboard/` — before the
unit-1 components (`install/`, `invoke/`, `graph_source/`) land. This is a
preserve-behaviour refactor: no symbol renames, no logic changes, no public contract
changes. Only module paths move.

Standalone scope (user, verbatim, 2026-10-25): "This is separate from ai-dlc units.
unit-1 can assume it's already been done." This plan is executed outside the AI-DLC
unit structure; the AI-DLC unit-1 design assumes the moved layout exists.

## Target layout

```
src/claude_workflow_viz/
    __init__.py            # __version__ only, no re-exports - unchanged
    __main__.py            # imports cli.main - unchanged
    cli.py                 # entry point stays top-level
    workflow/              # run-observation domain: hook boundary + run state
        __init__.py
        hook_command.py
        hook_adapter.py
        events.py
        run_state.py
    graph/                 # graph model and verdict rules
        __init__.py
        graph.py
        node_status.py
    dashboard/             # serving side: HTTP/SSE server + connection file
        __init__.py
        server.py
        connection_file.py
    static/                # unchanged - importlib.resources paths resolve the same
```

Folder names are ubiquitous-language concepts, matching the reverse-engineering business
overview vocabulary. No technical-role names (no `services/`, `repositories/`, `utils/`).

## Move mapping

| From | To |
| --- | --- |
| `events.py` | `workflow/events.py` |
| `run_state.py` | `workflow/run_state.py` |
| `hook_adapter.py` | `workflow/hook_adapter.py` |
| `hook_command.py` | `workflow/hook_command.py` |
| `graph.py` | `graph/graph.py` |
| `node_status.py` | `graph/node_status.py` |
| `server.py` | `dashboard/server.py` |
| `connection_file.py` | `dashboard/connection_file.py` |
| `cli.py` | stays |

Use `git mv` for every file so history is preserved.

## Import changes required

Internal imports (verified 2026-10-25 by reading every module):

| File | Current import | New import |
| --- | --- | --- |
| `cli.py` | `claude_workflow_viz.graph` | `claude_workflow_viz.graph.graph` |
| `cli.py` | `claude_workflow_viz.hook_command` | `claude_workflow_viz.workflow.hook_command` |
| `cli.py` | `claude_workflow_viz.server` | `claude_workflow_viz.dashboard.server` |
| `hook_command.py` | `claude_workflow_viz.connection_file` | `claude_workflow_viz.dashboard.connection_file` |
| `hook_command.py` | `claude_workflow_viz.events` | `claude_workflow_viz.workflow.events` |
| `hook_command.py` | `claude_workflow_viz.hook_adapter` | `claude_workflow_viz.workflow.hook_adapter` |
| `hook_command.py` | `claude_workflow_viz.server` | `claude_workflow_viz.dashboard.server` |
| `hook_adapter.py` | `claude_workflow_viz.events` | `claude_workflow_viz.workflow.events` |
| `run_state.py` | `claude_workflow_viz.events` | `claude_workflow_viz.workflow.events` |
| `run_state.py` | `claude_workflow_viz.node_status` | `claude_workflow_viz.graph.node_status` |
| `server.py` | `claude_workflow_viz.connection_file` | `claude_workflow_viz.dashboard.connection_file` |
| `server.py` | `claude_workflow_viz.events` | `claude_workflow_viz.workflow.events` |
| `server.py` | `claude_workflow_viz.graph` | `claude_workflow_viz.graph.graph` |
| `server.py` | `claude_workflow_viz.run_state` | `claude_workflow_viz.workflow.run_state` |

`events.py`, `graph.py`, `node_status.py`, `connection_file.py` have no internal imports
and need no changes. `__main__.py` and `__init__.py` are unaffected.

Import-cycle check: the move does not change the dependency graph, only the paths.
The existing `hook_command` → `server` dependency (for `LOOPBACK_ADDRESS`) becomes
`workflow.hook_command` → `dashboard.server` — same shape as today, no cycle introduced.

### Open decision — `LOOPBACK_ADDRESS`

`hook_command.py` imports `LOOPBACK_ADDRESS` from `server.py` to know where to POST.

- Recommended: keep the import as-is. Minimal churn; the coupling already exists.
- Alternative: relocate the constant to `dashboard/connection_file.py` — the connection
  file is the shared agreement between hook and server. Cleaner, touches more lines.
- Not recommended: a new top-level constants module — needless indirection.

Default: keep as-is unless review prefers the alternative.

## Packaging

`pyproject.toml` currently pins the wheel to one package:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/claude_workflow_viz"]
```

An explicit `packages` list does **not** include subpackages automatically — after the
move the wheel would silently drop `workflow/`, `graph/`, `dashboard/`. Required change:

```toml
[tool.hatch.build.targets.wheel]
packages = [
    "src/claude_workflow_viz",
    "src/claude_workflow_viz.workflow",
    "src/claude_workflow_viz.graph",
    "src/claude_workflow_viz.dashboard",
]
```

When unit-1 adds `install/`, `invoke/`, `graph_source/`, extend the list the same way.

## Tasks

- [ ] `git mv` the eight modules per the mapping table; create `__init__.py` in the three folders
- [ ] Update the 14 internal import lines per the table (leaf-first: `events.py`,
      then `node_status.py`/`connection_file.py`/`graph.py`, then `hook_adapter.py`/
      `run_state.py`, then `hook_command.py`, then `server.py`, then `cli.py`)
- [ ] Update `pyproject.toml` wheel packages list
- [ ] Update test imports in `tests/` (same table; only import lines change)
- [ ] Full suite green: 475 existing tests + README smoke-test fix, Node suite 87
- [ ] `ruff check` clean
- [ ] Wheel build contains the three subpackages; `pipx install --force` succeeds;
      `claude-workflow-viz serve --port 0` serves the dashboard
- [ ] End-to-end smoke: serve, POST probe payload to `/ingest` (204), `/graph` returns
      the graph, `/stream` delivers the event
- [ ] `git status` shows renames (R), not delete+add, for all moved files

Every intermediate commit keeps the tree importable — the ordering above makes each
step pass its import check.

## Unaffected contracts

- CLI: `claude-workflow-viz serve|hook` — entry point `claude_workflow_viz.cli:main` unchanged
- Hook contract: stdin JSON in, exit 0 always, no output
- HTTP API: `/ingest`, `/stream`, `/graph`, `/`, `/static/*` unchanged
- Event schema, Graph yaml schema, `status_rules.json` unchanged
- `static/` stays at the package root
- README, `docs/plan.md`: contain no module-path references (verified) — unchanged
- `aidlc-docs/` reverse-engineering artifacts describe the flat layout; they are
  historical snapshots and are not updated by this move

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Wheel silently missing subpackages | pyproject packages list updated; build-and-inspect step in verification |
| Stale install after move | `pipx reinstall` (or `pipx install --force`) before end-to-end check |
| Stale `__pycache__` shadowing moved modules | `find src tests -name __pycache__ -type d -exec rm -rf {} +` during the move |
| Rename drift (import updated, history lost) | `git mv` only; no file rewrites beyond import lines |

## Verification

1. `.venv/bin/python -m pytest` — 475 passed + fixed README smoke test, zero failures
2. `node --test tests/js/` — 87 passed
3. `.venv/bin/ruff check src tests` — clean
4. `python -m build` wheel contains `claude_workflow_viz/workflow/`, `.../graph/`,
   `.../dashboard/`
5. `pipx install --force .` then `claude-workflow-viz serve --port 0` — dashboard serves
6. Hook smoke: POST probe payload → 204, `/graph` returns graph, `/stream` delivers event
7. `git status` shows renames for all moved files

## Execution vehicle

Per repo default, implement through the agentic-dev-loop
(`./trigger-agentic-dev-loop.sh`), not inline.

## Out of scope

- Symbol renames, docstring changes, logic changes of any kind
- Moving `static/` or changing resource resolution
- The new unit-1 components (`install/`, `invoke/`, `graph_source/`) — they land after this move
- `planning-docs/README.md` conventions file (agent-engine has one; add here only if asked)

## Bookkeeping

- `aidlc-docs/inception/plans/application-design-plan.md`: D7 answer records the
  move-first directive
- `aidlc-docs/inception/plans/execution-plan.md`: amendment records the move as the
  first slice of unit-1
- `aidlc-docs/audit.md`: user directive logged
