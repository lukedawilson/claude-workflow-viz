# Implementation summary — Unit B (hook path / server lifecycle)

## Files created

- `src/claude_workflow_viz/invoke/__init__.py` — invoke package.
- `src/claude_workflow_viz/invoke/bootstrap.py` — `Bootstrap` application service:
  read connection, probe `/graph` for reuse (R11/R18), parse (Unit A), per-workflow cache
  write (R2/R17), sweep + detached spawn (NFRB3/R3), bounded 10 s wait (R6), open dashboard
  with `?workflow=<name>` (R7/R19/UEB6).
- `src/claude_workflow_viz/invoke/_platform.py` — pure `open_command` selector
  (darwin/win32/else, NFRB4) and the lsof-based `sweep_preferred_port` (NRB4).
- `tests/test_connection_file_shutdown.py`, `tests/test_server_shutdown.py`,
  `tests/test_graph_registry.py`, `tests/test_bootstrap.py`, `tests/test_platform.py`.
- `.github/workflows/ci.yml` — ubuntu + windows-latest matrix, full Python and Node suites.
- `run-demo.sh` — end-to-end demo (parse → spawn → open → synthetic hooks → `/shutdown`).

## Files modified

- `dashboard/connection_file.py` — `Connection.stop_server()` (POST `/shutdown`, 1 s timeout,
  no-op without a file, R5/UB2); `LOOPBACK_ADDRESS` relocated here; `state_directory()` and
  `ensure_state_directory()` (0700 dir) exposed.
- `dashboard/server.py` — `POST /shutdown` (Bearer + Host allowlist, 401/204, R8/NRB3);
  preferred-port bind 8322 with EADDRINUSE fallback; `allow_reuse_address = sys.platform !=
  "win32"` (NRB5); per-workflow graph registry on `/graph?workflow=<name>` (R15).
- `graph/graph.py` — `safe_workflow_name` guard so a workflow name cannot escape the
  `<state>/graphs/` directory (NFR1).
- `workflow/hook_command.py` — dispatcher keyed on `hook_event_name` (Workflow PreToolUse →
  Bootstrap then forward; SessionEnd → inline stop, no forward; else forward-only, R9).
- `workflow/events.py` + `workflow/hook_adapter.py` — optional `workflow` field on `Event`,
  populated on `run_start` from the PreToolUse payload (R16).
- `static/viz-core.js` + `static/app.js` + `static/index.html` — `sessionWorkflows`/
  `workflowNames`, workflow selector, `?workflow=` graph fetch and refetch on change (R19).
- `cli.py` — `serve --port` default now 8322 (fallback to an OS-picked port when busy).
- `pyproject.toml` — hatchling packages list gains `src/claude_workflow_viz.invoke`.
- `README.md` — invoke-time section, `/shutdown` endpoint, port 8322 + fallback note,
  per-workflow registry note (FR8 content half).
- `tests/js/viz-core.test.mjs`, `tests/test_events.py`, `tests/test_hook_adapter.py`,
  `tests/test_hook_command.py` — extended for the new behaviour.

## Rules honoured

R5/R8 (stop_server + `/shutdown`), R6 (10 s wait), R7/R19 (auto-open with workflow), R9
(dispatcher), R10 (parse-failure linear degradation + debug log), R11/R18 (reuse with cache
write), R13/R4 (silence), R15 (registry), R16 (workflow field), R17 (per-workflow cache),
NRB4/NRB5 (port selection), NFRB3 (detached spawn), NFRB4 (platform selector + Windows CI).

## Tests run locally

- `.venv-sandbox/bin/python -m pytest tests/ -q -m "not docker"` → 578 passed.
- `node --test tests/js/` → 91 passed.
- `ruff check` and `ruff format --check` → clean.

## Review fixes (attempt 2)

- `serve()` prints the token URL only when stdout is a terminal; a detached bootstrap spawn
  redirects stdout to the state-dir debug log, so the token no longer lands there
  (SECURITY-03, "the token is never logged").
- The bootstrap path creates the state dir with `ensure_state_directory()` (0700, always
  chmodded) and opens the debug-log handle 0600, mirroring `Connection.write()`. A fresh XDG
  state dir is never world-readable.
- `_spawn_detached` documents the accepted ~1 MiB cap bypass (server output is a two-line
  startup banner).
- New tests pin the invariants: `test_serve_does_not_print_the_token_to_a_non_terminal_stdout`
  (token absent from non-tty stdout), `test_detached_spawn_logs_no_token_and_keeps_the_state_dir_private`
  (end-to-end bootstrap spawn leaves no token in `debug.log` and a 0700 state dir),
  `test_ensure_state_directory_*` (0700 creation + tightening an existing permissive dir).
