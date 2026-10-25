# Integration Test Instructions

## Purpose

Verify the units work together: graph source (A) feeding the hook path (B),
the installer (C) driving the dispatcher, and the client skip inference (D)
against a live server. The primary integration vehicle is `./run-demo.sh`,
which exercises A+B+D end-to-end against a staged repository.

## Test Scenarios

### Scenario 1: Graph source → hook path (A → B)

- **Description**: a Workflow PreToolUse hook payload for a staged
  `implement.js` workflow is parsed, a detached server is spawned, and the
  run is observable on `/graph` and `/stream`.
- **Setup**: `./run-demo.sh` stages the fixture workflow into a temp repo.
- **Test Steps**: run `DEMO_HOLD_SECONDS=0 ./run-demo.sh`.
- **Expected Results**: a dashboard URL containing `?token=…&workflow=implement`
  is printed; the simulation posts 23 events; `/shutdown` answers 204; the
  script exits 0.
- **Cleanup**: the script removes its temp state dir on exit.

### Scenario 2: Hook path → installer (B ← C)

- **Description**: the installer's verify step runs the real
  `claude-workflow-viz hook` (empty stdin) through the dispatcher's silence
  wrapper and expects exit 0.
- **Setup**: the console script must be on PATH (`pip install -e .`).
- **Test Steps**: run `claude-workflow-viz install` in a scratch repo.
- **Expected Results**: five hook registrations written into
  `.claude/settings.local.json`, `/viz` command deployed, summary printed.
- **Cleanup**: delete the scratch repo.

### Scenario 3: Live stream → client skip inference (D, live)

- **Description**: `run-demo.sh` sends no events for the guarded
  `verify-fsm` stage; once the run finishes, the client marks it skipped.
- **Setup**: as Scenario 1.
- **Test Steps**: run the demo with the browser open for the hold window.
- **Expected Results**: the final step `done` renders green and
  `s1/verify-fsm:r2` renders skipped (grey dashed) at run end.
- **Cleanup**: the script's `/shutdown` closes the server.

## Setup Integration Test Environment

### 1. Start Required Services

No services to start; `run-demo.sh` spawns the server itself.

### 2. Configure Service Endpoints

```bash
# Optional: point the demo at a scratch state dir
export CLAUDE_WORKFLOW_VIZ_STATE_DIR="$(mktemp -d)"
```

## Run Integration Tests

### 1. Execute Integration Test Suite

```bash
DEMO_HOLD_SECONDS=0 ./run-demo.sh
python -m pytest tests/test_demo_fixture.py tests/test_parser.py -q
node --test tests/js/demo-progression.test.mjs
```

The fixture-contract test locks every demo event to the `/ingest`
validation, and the Node replay test locks the client behaviour for the
exact event stream.

### 2. Verify Service Interactions

- **Test Scenarios**: the three above.
- **Expected Results**: as listed per scenario.
- **Logs Location**: server stdout/stderr go to the state dir's `debug.log`.

### 3. Cleanup

```bash
# The demo shuts its own server down. For stray servers:
curl -X POST -H "Authorization: Bearer <token>" http://127.0.0.1:<port>/shutdown
```
