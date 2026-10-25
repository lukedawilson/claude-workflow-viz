# claude-workflow-viz — plan

A standalone, pipx-installable Python package that renders any Claude Code Workflow run as a live routed Mermaid flowchart: nodes are steps, edges are pass/fail routing, nodes change colour with live status, each node has a console pane, and a retry loop-back edge is highlighted. It is driven by Claude Code hooks, not by the workflow script (workflow scripts have no filesystem, network or shell access).

The built-in `/workflows` progress tree is not the target. The package must be shareable and generic: the step graph is data (a config file), not hardcoded to any one workflow.

## Architecture

```
Claude Code run
   | hook (async:true, non-blocking)                 +- GET /         static UI
   v                                                 +- GET /stream   SSE live events
[ claude-workflow-viz hook ] --POST /ingest (token)->[ claude-workflow-viz serve ]
   normalises payload -> event                         per-session run state
   {session_id, ts, kind, step_key, status, summary}   renders graph-config nodes/edges
                                                          |
                                                browser --+  routed flowchart, live
```

| Component | Entry point | Role |
|---|---|---|
| Emitter | `claude-workflow-viz hook` | Reads hook JSON on stdin, normalises it to an event, POSTs to localhost. Token-guarded. Fails silent: never blocks or breaks a run. |
| Server | `claude-workflow-viz serve` | Localhost ingest, per-session run state, SSE stream. Auto-started on first event. |
| UI | static files, no build step | Mermaid `flowchart` re-rendered from the graph config on each SSE event; per-node `class` for pending / running / pass / fail / retry; highlighted active edge; per-node console pane. |
| Graph config | `<workflow>.viz.yaml` | Nodes, `on_pass` / `on_fail` edges, and the mapping from a step identity (label / agent_type / transcript pattern) to a node plus instance dimensions (slice, round). |

Stack: Python (pipx), vanilla JS UI, Mermaid.

## Event-source interface

Two adapters emit the same normalised event stream, so the server and UI do not care which one is live:

| Adapter | Source |
|---|---|
| Hook adapter | `SubagentStart` / `SubagentStop`, per-agent `PreToolUse` / `PostToolUse` on `Agent`, `PreToolUse` / `PostToolUse` on `Workflow` for run start and stop. |
| Transcript-tail adapter | Tails `~/.claude/projects/<project>/<session>/subagents/agent-<label>-<id>.jsonl`, bracketed by the `Workflow` hooks. |

## Phase 0 — probe spike (gates everything)

Claude Code docs do not say whether per-agent hooks fire for `agent()` calls inside a Workflow script, and the `Agent` payload has no documented `label` or `phase` field.

- Wire an `async:true` logging hook on `SubagentStart`, `SubagentStop`, `PreToolUse` / `PostToolUse` matched to `Agent`, and `PreToolUse` / `PostToolUse` matched to `Workflow`.
- Run a two-agent toy workflow with distinct labels.
- Record which events fire, and whether `agent_type`, `description`, `agent_transcript_path` (and its basename) or `last_assistant_message` identify the step.

| Probe result | Feed |
|---|---|
| Per-agent events fire with a usable step identity | Hook adapter |
| They fire but only carry `agent_type` / transcript path | Hook adapter, identity parsed from the `agent_transcript_path` basename |
| They do not fire inside workflows | Transcript-tail adapter, bracketed by the `Workflow` hooks |

## Phases

| Phase | Output |
|---|---|
| 0 | Probe spike and decision on the event source |
| 1 | Package skeleton, `serve` and `hook` entry points, event schema, token-guarded SSE ingest, in-memory run state, silent degrade |
| 2 | Config-driven Mermaid routed-graph UI: live status, edges, retry loop-back, console pane |
| 3 | `implement.viz.yaml` example, a `settings.json` snippet referencing the installed entry point, opt-in docs |
| 4 | Packaging for pipx, versioning, README, a second generic example proving the package is not workflow-examples-specific |

## Example: the /implement graph

Static nodes: `planner`, then per slice `develop -> gate -> review -> code-review -> classify -> verify-fsm`, then `done` / `blocked` / `needs-context`. A failing gate, review, code-review or verify-fsm routes back to `develop` with the round incremented, bounded at three rounds.

`implement.js` tags every agent with the label `<slice>/<stage>:r<round>` (stages: `develop`, `gate`, `review`, `code-review`, `classify`, `verify-fsm`), so the config parses (slice, stage, round) without editing `implement.js`. Node colour comes from the agent's structured return: developer status, gate green / red / unverified, reviewer APPROVED / CHANGES_REQUESTED, verify-fsm PASS / FINDING / UNVERIFIED / SKIPPED.

## Risks

| Risk | Mitigation |
|---|---|
| Per-agent hooks may not fire inside workflows | Event-source interface plus the transcript-tail adapter; Phase 0 settles it before building |
| No label or phase in the hook payload | Recover from the `agent_transcript_path` basename |
| Transcript-tail relies on an undocumented JSONL layout | Pinned parser with a schema smoke test; used only if Phase 0 forces it |
| `last_assistant_message` for a schema'd agent is undocumented | Parse defensively, fall back to the transcript tail |
