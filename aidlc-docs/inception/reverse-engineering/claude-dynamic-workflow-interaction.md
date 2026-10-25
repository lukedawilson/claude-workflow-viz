# How Claude Dynamic Workflows Interact with claude-workflow-viz

**Audience**: the tool's author, and anyone wiring a Dynamic Workflow (e.g. `/implement` in
workflow-examples) to the visualiser.

**Scope**: the contract between a running Claude Dynamic Workflow and claude-workflow-viz —
which hooks to register, what data flows, how workflow identity and step identity survive the
trip, and where the mapping is approximate today.

---

## 1. The two systems' relationship

```
+--------------------------------------------------------------+
|  Claude Code (driver)                                        |
|                                                              |
|  .claude/workflows/implement.js      (JavaScript VM workflow)|
|      |                                                        |
|      | agent() x N  ->  spawns workflow-subagents             |
|      |   "s1/develop:r1", "s1/gate:r1", "s1/review:r1", ...   |
|      v                                                        |
|  Claude Code session dir                                      |
|    session/subagents/workflows/wf_<run id>/                   |
|      agent-<id>.jsonl   (per-agent transcript)                |
|      agent-<id>.meta.json  (label + phase)                    |
|      journal.jsonl        (started / result records)          |
|      |                                                        |
|      |  hooks fire (PreToolUse, PostToolUse,                  |
|      |               SubagentStart, SubagentStop)             |
|      v                                                        |
+--------------------------------------------------------------+
       |
       |  stdin JSON -> "claude-workflow-viz hook"  (async, always exits 0)
       v
+--------------------------------------------------------------+
|  claude-workflow-viz (observer)                               |
|                                                              |
|  hook_adapter: normalise payload -> Event                     |
|  server:      POST /ingest  ->  RunState (in-memory)          |
|  server:      GET /stream   ->  SSE to browser                |
|  server:      GET /graph    ->  Mermaid flowchart             |
|                                                              |
|  Browser: app.js + viz-core.js + mermaid.min.js               |
+--------------------------------------------------------------+
```

The visualiser is a **passive observer**. It never drives the workflow: no hook output,
no files written, every hook process exits 0 regardless of what it read. If the visualiser
is down, the workflow runs unchanged. The hooks write JSON payloads on stdin; the tool
reads stdin, normalises, and POSTs to the local server.

---

## 2. Wiring a repo (e.g. workflow-examples)

### 2.1 Install and start the visualiser

```bash
pipx install .                      # in the claude-workflow-viz repo
claude-workflow-viz serve --graph examples/implement.viz.yaml
```

`serve --port 0` picks a free port and prints the dashboard URL (token embedded).
The connection file `server.json` (`{port, token}`) is written atomically, mode 0600,
in the state dir (`$CLAUDE_WORKFLOW_VIZ_STATE_DIR` || `$XDG_STATE_HOME/claude-workflow-viz`
|| `~/.local/state/claude-workflow-viz`). On shutdown the file is removed if the token
still matches.

### 2.2 Register the hooks

In the target repo's `.claude/settings.local.json`, under `hooks`, add four entries:

```json
{
  "hooks": {
    "PreToolUse":  [{ "matcher": "Workflow", "hooks": [{ "type": "command", "command": "claude-workflow-viz hook", "async": true }] }],
    "PostToolUse": [{ "matcher": "Workflow", "hooks": [{ "type": "command", "command": "claude-workflow-viz hook", "async": true }] }],
    "SubagentStart": [{ "hooks": [{ "type": "command", "command": "claude-workflow-viz hook", "async": true }] }],
    "SubagentStop":  [{ "hooks": [{ "type": "command", "command": "claude-workflow-viz hook", "async": true }] }]
  }
}
```

All four must be `async: true` — a synchronous hook on the hot path would stall the
workflow, and a hook that blocks Claude Code has already failed its contract.
workflow-examples currently has only `SessionStart` and a `PreToolUse` (Bash) hook in
`.claude/settings.json`, so this is purely additive — no existing hook is touched.

### 2.3 Why these four events

| Hook event | What the visualiser does with it |
| --- | --- |
| `PreToolUse` (Workflow) | Nothing by itself (used to correlate). |
| `PostToolUse` (Workflow) | If `tool_response.status == "async_launched"`, emits **run_start** with the `runId`. This is the launch of the whole workflow run. |
| `SubagentStart` (workflow-subagent) | Emits **step_start** for the agent's step key. |
| `SubagentStop` (workflow-subagent) | Emits **step_stop**: status derived from the response/transcript, plus the verbatim `last_assistant_message` as summary and the structured `journal.jsonl` result. |

The workflow's own `agent()` calls never fire hooks directly — Claude Code emits
`SubagentStart`/`SubagentStop` for each spawned workflow-subagent, which is the per-step
signal the visualiser keys on.

---

## 3. Event mapping table

| Claude Code signal | Visualiser event | Kind | Status derivation |
| --- | --- | --- | --- |
| Workflow `PostToolUse` with `status: async_launched` | `run_start` | run_start | — |
| workflow-subagent `SubagentStart` | `step_start` | step_start | `running` |
| workflow-subagent `SubagentStop` | `step_stop` | step_stop | response status (completed→pass, failed/error→fail, else unknown); final display status also consults the journal result's verdict (see §6) |

There is no `run_stop` emitted by the adapter. A run is finished implicitly: `RunState`
tracks per-run step statuses, and the banner shows "running" only while any run has
unfinished steps. (`EventKind` has a `run_stop` member — it exists for internal use,
but the hook adapter never produces one.)

---

## 4. How the visualiser learns who is who

For each step the adapter must answer: which **step** (to place on the graph) and which
**workflow run** (to group a session's activity). Claude Code leaves three artifacts per
workflow run, and the adapter reads them:

### 4.1 The agent transcript path

```
<session>/subagents/workflows/wf_5bafa1d7-817/agent-aa40e04dc34ef5608.jsonl
```

The transcript basename follows `agent-<label>-<identifier>.jsonl`. `label` is the
URL-encoded form of the `agent()` label argument, so the adapter unquotes it to recover
the exact string the workflow passed.

### 4.2 The per-agent meta file (`agent-<id>.meta.json`)

```json
{
  "agentType": "workflow-subagent",
  "description": "s1/code-review:r1",
  "workflowPhase": "Probe",
  "spawnDepth": 1,
  "requestShape": "foreground",
  "requestNonInteractive": false
}
```

`description` is exactly the `label` argument of the `agent()` call — this is the
**step key** the visualiser matches against the graph config. `workflowPhase` is the
`phase` argument. (For the implement workflow the phases are Plan/Develop/Gate/Review/
Bug hunt/FSM.)

### 4.3 The workflow journal (`journal.jsonl`)

```json
{"type":"launched"}
{"type":"started","key":…,"agentId":"aa40e04dc34ef5608","label":"s1/develop:r1","phase":"Develop"}
{"type":"result","key":…,"agentId":"aa40e04dc34ef5608","result":{…structured result…}}
```

The adapter takes the **last `type:result` line whose `agentId` matches** the stopping
agent, capped at a 1 MiB journal read, and attaches that structured result to the step.
The result is what later drives the verdict → colour mapping. A known race: the
`SubagentStop` hook is async and may run before Claude Code writes the result line, in
which case the step's result is `None` and the step falls back to its message status.

---

## 5. The label convention: `<slice>/<stage>:r<round>`

The implement workflow labels its agents `s1/develop:r1`, `s2/gate:r2`, and so on.
The visualiser's graph schema parses labels with the regex:

```
(?P<slice>[^/]+)/(?P<stage>[^:]+):r(?P<round>\d+)
```

(round limited to 9 digits; slice and stage must contain neither `/` nor `:`.)

This is the one place where the workflow's author and the visualiser's config author
must agree:

| Rule | Why |
| --- | --- |
| `slice.id` must be a plain token (e.g. `s1`, `auth`) | The planner's JSON schema must constrain `slices[].id` to `[A-Za-z0-9_-]+`. A slice id containing `/` or `:` would make the step unmappable and it would land in the "unmapped steps" list. |
| `stage` must be one of the graph's configured stages | Stage names come from the `label` argument's middle segment (`develop`, `gate`, `review`, `code-review`, `classify`, `verify-fsm`). |
| Round numbers ≤ 9 digits | Trivially safe for the implement workflow (max 3). |

Nodes in the graph config match either by `step_key` (exact string match against the
label, no slice/round parsing — used for the once-per-run agents like `pre-flight/head-check`,
`planner`, `gate-baseline`) or by `stage` (matches any slice, creating one instance per
`(slice, round)`).

---

## 6. Verdict → colour mapping for the implement workflow

The structured result of each agent is inspected in field order `verdict`, `status`,
`gate` (case-insensitive) against `static/status_rules.json`:

| Rule field | Values → pass | Values → fail |
| --- | --- | --- |
| `verdict` | APPROVED, PASS, GREEN, SKIPPED | CHANGES_REQUESTED, FAIL, FINDING, RED, UNVERIFIED |
| `status` | (same value sets) | (same value sets) |
| `gate` | (same value sets) | (same value sets) |

Applied to each implement.js agent schema:

| Agent (schema) | Result → colour | Correct? |
| --- | --- | --- |
| pre-flight (`{sha}`) | no recognised field → **pass** | Yes — it is a guard; failure never renders. |
| planner (`{status: PLANNED\|NEEDS_CONTEXT, …}`) | `NEEDS_CONTEXT` is not a recognised status → **pass** | **Gap** — a needs-context plan renders green. |
| gate-baseline (`{formatViolations[], failingTestNames[], note}`) | no recognised field → **pass** | Acceptable — it reports, doesn't judge. |
| develop (`{status: DONE\|DONE_WITH_CONCERNS\|NEEDS_CONTEXT\|BLOCKED, …}`) | none recognised → **pass** | **Gap** — a BLOCKED or NEEDS_CONTEXT slice renders green. |
| gate (`{status: green\|red\|unverified, …}`) | green→pass; red→fail; **unverified→fail** | The unverified→fail is deliberate: the rules file comments "an unverified gate is not green", matching how the workflow treats it (proceeds, but it is not a clean pass). |
| review (`{verdict: APPROVED\|CHANGES_REQUESTED, …}`) | APPROVED→pass, CHANGES_REQUESTED→fail | Correct. |
| code-review (`{ran, blocking, findings[]}`) | no recognised field → **pass** | **Gap** — a blocking code review renders green. |
| classify (`{touchesConcurrency, sourceFiles[], rationale}`) | no recognised field → **pass** | Acceptable — classification has no verdict semantics. |
| verify-fsm (`{verdict: PASS\|FINDING\|UNVERIFIED\|SKIPPED, …}`) | PASS/SKIPPED→pass; FINDING/UNVERIFIED→fail | Correct. |

Three mapping gaps to know about: develop `BLOCKED`/`NEEDS_CONTEXT`, code-review
`blocking: true`, and planner `NEEDS_CONTEXT` all render as pass with the current rules
file. Closing them means either adding those exact values to `status_rules.json` (with
the schema value names, e.g. `DONE_WITH_CONCERNS` → pass, `BLOCKED` → fail, `NEEDS_CONTEXT`
→ fail) or having the workflow emit a `verdict` field the rules already know.

---

## 7. Run lifecycle

1. `/implement` runs `agent()` for `pre-flight/head-check` → the first workflow-subagent
   starts. `SubagentStart` hooks fire per agent.
2. When Claude Code launches the workflow (the Workflow tool's `PostToolUse` with
   `status: "async_launched"`), the visualiser emits `run_start` and stores the `runId`
   (or the workflow run-dir name).
3. Each agent's start/stop streams in; the graph lights up node by node.
4. Retries (round 2+ of a slice) re-enter the same nodes: unfinished nodes with
   `round > 1` render as "retry", and `on_fail` edges back into a node that re-entered
   at a higher round render as loop-back edges.
5. When the workflow returns and no run has unfinished steps, the banner drops its
   "running" state. The run is finished implicitly — there is no run_stop event.

Note the launch timing: `PostToolUse` fires at launch, not completion, so the run shows
as running for the whole workflow execution, and the only completion signal is the last
step stopping.

---

## 8. Graph config vs the real control flow

`examples/implement.viz.yaml` (12 nodes) models the workflow as:

```
pre-flight -> planner -> gate-baseline -> develop -> gate -> review -> code-review -> classify -> verify-fsm -> done
                          |                                                                  |
                          +----(on_fail)----> blocked                                       +----(on_fail)----> develop
```

Terminals: `done`, `blocked`, `needs-context`; `max_rounds: 3`,
`on_rounds_exhausted: blocked`.

Two deliberate approximations to know about:

1. **classify `on_fail` → blocked**, but the real flow treats a missing classify result as
   a blocker that loops back to the developer — visually it lands on `blocked` instead of
   showing another `develop` re-entry.
2. **develop `on_fail` → blocked**, but a developer returning `NEEDS_CONTEXT` in the real
   flow ends the slice as NEEDS_CONTEXT (and typically the whole run), not `blocked`.
   `needs-context` exists as a terminal but only `planner` routes to it in the example.

Everything else mirrors the JS: gate red → back to develop; review CHANGES_REQUESTED,
code-review blocking, or fsm FINDING → back to develop; the loop continues until blockers
are empty or the round cap (3) is exhausted.

---

## 9. End-to-end sequence

```mermaid
sequenceDiagram
    participant W as /implement workflow (JS)
    participant CC as Claude Code
    participant H as viz hook (stdin)
    participant S as viz server
    participant B as Browser (SSE)

    W->>CC: agent() s1/develop:r1
    CC->>H: SubagentStart payload
    H->>S: POST /ingest (step_start)
    S-->>B: event: step_start s1/develop:r1
    CC->>CC: (agent runs, writes transcript)
    CC->>H: SubagentStop payload
    H->>H: read meta.json + journal.jsonl
    H->>S: POST /ingest (step_stop + result)
    S-->>B: event: step_stop s1/develop:r1 (DONE)
    Note over B: node lights green; edge advances
```

Text alternative:

```
/implement  ->  Claude Code  ->  hook (stdin)  ->  server (POST /ingest)  ->  browser (SSE)
   agent()          |                                                          ^
   s1/develop:r1    +- SubagentStart / SubagentStop payloads                  |
                                                                            graph re-renders
```

---

## 10. What Claude Code must keep stable (the fragile contract)

Everything above works as long as these hold — they are outside the visualiser's control:

- `agent()` labels keep the `<slice>/<stage>:r<round>` shape, with slice/stage free of
  `/` and `:`.
- The `agent-<id>.meta.json` keeps the `description` (= label) and `workflowPhase` fields.
- `journal.jsonl` keeps `type:"result"` lines carrying the agent's structured result
  under `agentId`.
- `SubagentStop` payloads keep `agent_transcript_path`, `agent_id`, `agent_type:
  "workflow-subagent"`, and `last_assistant_message`.
- Workflow runs keep the `session/subagents/workflows/wf_<id>/` directory layout.
- Workflow `PostToolUse` keeps `tool_response.status == "async_launched"` at launch.

The probe fixtures in `tests/fixtures/` (`probe_payloads.jsonl`, `status_cases.json`)
pin these shapes; a Claude Code change that breaks any of them shows up as unmapped steps
or a dead graph, and the fixtures are where to look first.
