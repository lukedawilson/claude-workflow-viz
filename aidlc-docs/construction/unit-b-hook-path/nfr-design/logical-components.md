# Logical Components — Unit B (hook path / server lifecycle)

Logical view of the unit's components and their integration points. No new
infrastructure elements beyond the CI workflow file (a code-generation deliverable).

| Component | Module | Role |
| --- | --- | --- |
| Bootstrap | `invoke/bootstrap.py` (new) | Invoke-time orchestration: read connection → probe reuse → parse (Unit A) → per-workflow cache write → sweep preferred port → spawn or reuse → wait ≤10 s → open browser |
| Platform open-command selector | pure helper (in or under `invoke/`) | `darwin → open`, `win32 → os.startfile`, else `xdg-open`; total function over platform ids (PBT target) |
| Sweep helper | pure + lsof subprocess helper | Kill listeners matching `claude-workflow-viz` on the preferred port before spawn (cwd positive-only, self-PID excluded, silent no-op without lsof) |
| Dispatcher | `workflow/hook_command.py` (extended) | Branches on `hook_event_name`: Workflow PreToolUse → Bootstrap then forward; SessionEnd → inline `stop_server()`, no forward; else forward-only. Silence wrapper unchanged |
| Connection | `dashboard/connection_file.py` (extended) | Read `server.json`; `stop_server()` (POST /shutdown, 1 s timeout, no-op without file); owns `LOOPBACK_ADDRESS` (relocated from server.py) |
| Server — lifecycle | `dashboard/server.py` (extended) | `POST /shutdown` (deny-on-error); binds preferred port with EADDRINUSE fallback; stops + removes its connection file on authenticated shutdown |
| Server — graph registry | `dashboard/server.py` (new behaviour) | `{workflow_name: Graph}` loaded on demand from `<state>/graphs/<workflow>.viz.yaml` on `/graph?workflow=<name>`; unknown name → linear for that request; no parameter → default graph (backward compatible) |
| Event workflow field | `workflow/events.py` + `hook_adapter.py` (extended) | Optional `workflow` field populated on `run_start` only, from the PreToolUse payload (R16); backward compatible |
| Client workflow mapping | `static/viz-core.js` + `app.js` (extended) | Maps session → workflow from run_start events; workflow selector refetches `/graph?workflow=` on change; `?workflow=` in the dashboard URL (R19) |
| State-dir debug log | state dir (infrastructure) | ~1 MiB cap, oldest-truncation, exception-guarded; shared by Bootstrap summaries, server output, parser errors (NRB1) |
| CI workflow | `.github/workflows/*.yml` (new, code generation) | `windows-latest` job: win32 branch + full suite (NFRB4 = B) |

## Integration points

- Unit A: `WorkflowSource.parse()` and `Graph` (cache writes, registry loads).
- Existing HTTP surface: `/ingest`, `/stream`, `/graph` (now with optional `?workflow=`).
- New HTTP surface: `POST /shutdown` (deny-on-error).
- No external systems; no new runtime dependencies.
