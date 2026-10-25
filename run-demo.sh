#!/usr/bin/env bash
# End-to-end demo of the invoke-time flow without a real Claude Code session.
#
# It stages a fictional workflow (tests/fixtures/workflows/implement.js) into a throwaway repo,
# fires the Workflow PreToolUse hook so the bootstrap statically parses it, spawns the server
# detached, waits for server.json and opens the dashboard, then simulates the update hooks by
# POSTing the full implement progression to /ingest (including a gate failure and its loop-back
# retry, plus verdicts for the review and code-review steps). The gated verify-fsm stage is
# deliberately left without events so it renders as skipped. The dashboard is held open for
# DEMO_HOLD_SECONDS (default 8, 0 skips the hold) before the server is stopped via /shutdown,
# the same way SessionEnd does.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$(mktemp -d)"
REPO="$(mktemp -d)"
mkdir -p "$REPO/.claude/workflows"
cp "$HERE/tests/fixtures/workflows/implement.js" "$REPO/.claude/workflows/implement.js"

export CLAUDE_WORKFLOW_VIZ_STATE_DIR="$STATE_DIR"
PYTHON="${PYTHON:-$HERE/.venv/bin/python}"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
  echo "run-demo.sh: interpreter '$PYTHON' is not Python 3.12+ (claude-workflow-viz requires >= 3.12)." >&2
  echo "Set PYTHON to a 3.12+ interpreter, e.g. PYTHON=$HERE/.venv/bin/python ./run-demo.sh" >&2
  exit 1
fi
export PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"

echo "staging workflow at $REPO/.claude/workflows/implement.js"

# 1. Invoke-time bootstrap: parse, cache, spawn (detached) and open the dashboard in a browser.
"$PYTHON" -m claude_workflow_viz hook < <(
  printf '%s\n' '{"session_id":"demo","hook_event_name":"PreToolUse","tool_name":"Workflow","tool_input":{"name":"implement"},"cwd":"'"$REPO"'"}'
)

# 2. Wait for the server's connection file (the spawn is detached and writes it shortly).
for _ in $(seq 1 200); do
  [ -f "$STATE_DIR/server.json" ] && break
  sleep 0.05
done
[ -f "$STATE_DIR/server.json" ] || { echo "server did not start" >&2; exit 1; }

# 3. Print the dashboard URL up front (the bootstrap already opened the tab).
"$PYTHON" - "$STATE_DIR/server.json" <<'PYEOF'
import json
import sys

connection = json.load(open(sys.argv[1]))
port, token = connection["port"], connection["token"]
print(f"dashboard: http://127.0.0.1:{port}/?token={token}&workflow=implement")
PYEOF

# 4. Simulate the update hooks: the full implement progression, then hold the dashboard
#    open, then stop the server the same way SessionEnd does.
DEMO_HOLD_SECONDS="${DEMO_HOLD_SECONDS:-8}"
"$PYTHON" - "$STATE_DIR/server.json" "$DEMO_HOLD_SECONDS" <<'PYEOF'
import http.client
import json
import sys
import time

connection = json.load(open(sys.argv[1]))
port, token = connection["port"], connection["token"]


def post(path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    conn.request("POST", path, body=body, headers=headers)
    response = conn.getresponse()
    response.read()
    conn.close()
    return response.status


def start(ts, key, summary):
    return {"session_id": "demo", "ts": ts, "kind": "step_start",
            "step_key": key, "status": "running", "summary": summary}


def stop(ts, key, status, result=None):
    event = {"session_id": "demo", "ts": ts, "kind": "step_stop",
             "step_key": key, "status": status, "summary": ""}
    if result is not None:
        event["result"] = result
    return event


events = [
    start(1.0, "pre-flight/head-check", "checking base sha"),
    stop(2.0, "pre-flight/head-check", "pass", {"sha": "demo"}),
    start(3.0, "planner", "planning the slices"),
    stop(4.0, "planner", "pass", {"status": "PLANNED", "slices": [{"id": "s1"}]}),
    start(5.0, "gate-baseline", "baseline checks"),
    stop(6.0, "gate-baseline", "pass"),
    start(7.0, "s1/develop:r1", "implementing slice s1"),
    stop(8.0, "s1/develop:r1", "pass", {"status": "DONE"}),
    start(9.0, "s1/gate:r1", "checking the gate"),
    stop(10.0, "s1/gate:r1", "fail", {"status": "red", "failureSummary": "one test red"}),
    start(11.0, "s1/develop:r2", "fixing the failing test"),
    stop(12.0, "s1/develop:r2", "pass", {"status": "DONE"}),
    start(13.0, "s1/gate:r2", "checking the gate"),
    stop(14.0, "s1/gate:r2", "pass", {"status": "green"}),
    start(15.0, "s1/review:r2", "reviewing the change"),
    stop(16.0, "s1/review:r2", "pass", {"verdict": "APPROVED"}),
    start(17.0, "s1/code-review:r2", "hunting for bugs"),
    stop(18.0, "s1/code-review:r2", "pass", {"ran": True, "blocking": False}),
    start(19.0, "s1/classify:r2", "classifying the change"),
    stop(20.0, "s1/classify:r2", "pass", {"touchesConcurrency": False}),
    # classify found no concurrency risk, so the guarded verify-fsm stage never ran.
    # Sending no events for it: once the run finishes, the dashboard renders
    # s1/verify-fsm:r2 as skipped (greyed out) via the Unit D inference.
]
for event in events:
    post("/ingest", body=json.dumps(event))
    time.sleep(0.3)

hold = float(sys.argv[2])
if hold > 0:
    print(f"holding {hold:.0f}s (DEMO_HOLD_SECONDS=0 to skip)...", flush=True)
    time.sleep(hold)
print("shutdown:", post("/shutdown"))
PYEOF

echo "state dir: $STATE_DIR"
