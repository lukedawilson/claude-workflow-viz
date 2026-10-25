# End-to-End Test Instructions

## Purpose

The complete user workflow, from zero to a live dashboard, with no manual
serve steps (Q8 success criterion).

## Scenario: bootstrap → invoke → visualise → stop

- **Setup**: a repository with a `.claude/workflows/*.js` workflow present,
  the package installed (`pip install -e .`), and the hooks registered.

### 1. Install

```bash
cd <target repo>
claude-workflow-viz install
```

**Expected**: summary lists five hook registrations written to
`.claude/settings.local.json`, `/viz` command created, binary verified
(exit 0 on empty stdin).

### 2. Invoke a workflow

Run a Claude Code workflow (or simulate one): the PreToolUse hook parses
the workflow, starts or reuses the server, and opens the dashboard at
`http://127.0.0.1:<port>/?token=…&workflow=<name>`.

**Expected**: a browser tab opens; the graph renders before the first step
event; nodes colour as steps run; retries re-enter with a loop-back;
verdict results map to colours; a guarded stage that never runs renders
skipped at run end; the terminal node turns green when reached.

### 3. Session end

End the Claude Code session.

**Expected**: the SessionEnd hook stops the server (no request, no
forwarded event), and `server.json` is removed from the state dir.

## Automated Coverage

`./run-demo.sh` is the scripted version of this scenario for a staged
repository (steps 2-3 with the fixture event stream; step 1 is covered by
`tests/test_installer.py`). The Windows leg of CI runs the full Python and
Node suites on windows-latest, covering the `os.startfile` branch of the
browser opener through `tests/test_platform.py`.
