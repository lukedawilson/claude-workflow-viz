#!/usr/bin/env bash
# End-to-end demo of the invoke-time flow without a real Claude Code session.
#
# It stages a fictional workflow (tests/fixtures/workflows/implement.js) into a throwaway repo,
# fires the Workflow PreToolUse hook so the bootstrap statically parses it, spawns the server
# detached, waits for server.json and opens the dashboard, then simulates the update hooks by
# POSTing synthetic step payloads to /ingest and stopping the server via /shutdown.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$(mktemp -d)"
REPO="$(mktemp -d)"
mkdir -p "$REPO/.claude/workflows"
cp "$HERE/tests/fixtures/workflows/implement.js" "$REPO/.claude/workflows/implement.js"

export CLAUDE_WORKFLOW_VIZ_STATE_DIR="$STATE_DIR"
PYTHON="${PYTHON:-python}"
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

# 3. Simulate the update hooks, then stop the server the same way SessionEnd does.
"$PYTHON" - "$STATE_DIR/server.json" <<'PYEOF'
import http.client
import json
import sys
import time

connection = json.load(open(sys.argv[1]))
port, token = connection["port"], connection["token"]


def post(path, body=None, token=token):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    conn.request("POST", path, body=body, headers=headers)
    response = conn.getresponse()
    response.read()
    conn.close()
    return response.status


events = [
    {"session_id": "demo", "ts": 1.0, "kind": "step_start", "step_key": "pre-flight/head-check", "status": "running", "summary": "checking"},
    {"session_id": "demo", "ts": 2.0, "kind": "step_stop", "step_key": "pre-flight/head-check", "status": "pass", "summary": ""},
    {"session_id": "demo", "ts": 3.0, "kind": "step_start", "step_key": "planner", "status": "running", "summary": "planning"},
    {"session_id": "demo", "ts": 4.0, "kind": "step_stop", "step_key": "planner", "status": "pass", "summary": ""},
]
for event in events:
    post("/ingest", body=json.dumps(event))
    time.sleep(0.3)

print(f"dashboard: http://127.0.0.1:{port}/?token={token}&workflow=implement")
print("shutdown:", post("/shutdown"))
PYEOF

echo "state dir: $STATE_DIR"
