# Component Methods

Method-level design for the unit-1 components identified in components.md. Signatures
are indicative; construction fixes exact names. All new domain behaviour returns typed
results or typed errors (D8-B); only the installer boundary raises.

## `install/installer.py`

```
run(target_repo: Path, viz_dir: VizDirChoice) -> InstallOutcome   # raises at boundary on terminal failure (D8-B)
```

Behaviour:

1. Verify the tool: run the hook path once with empty stdin and require exit 0 (proves
   `claude-workflow-viz` is on PATH and silent).
2. Merge the five hook registrations into `.claude/settings.local.json` idempotently:
   - PreToolUse (matcher `Workflow`), PostToolUse (matcher `Workflow`), SubagentStart,
     SubagentStop — each `{"type":"command","command":"claude-workflow-viz hook","async":true}`,
     byte-identical to today's README contract (D10);
   - SessionEnd — same shape, added if absent (Q6-B).
   Existing registrations are preserved; only missing ones are added; an already-correct
   file is untouched. Invalid JSON fails loudly naming the file (D8).
3. Create `.claude/commands/viz.md` from the packaged template (FR2); overwrite only on
   explicit `--force`.
4. Record the fallback-yaml directory choice: `--viz-dir` flag or terminal prompt (Q4):
   default `.claude-local/viz/`, alternative `.claude/viz/`.
5. Print the install summary: registrations written, command created, what happens on
   the next workflow run.

Idempotency contract: running the installer twice changes nothing.

## `graph_source/parser.py`

```
class WorkflowSource:
    def __init__(self, source_text: str, source_path: Path): ...
    def parse(self) -> Graph | ParseFailure      # D5: the Graph.load shape, or a named failure
```

Supported subset (FR4, never guesses):

- `export const meta = {...}` — workflow name (and phases where present);
- `agent(...)` call sites whose label is a string literal or a template literal whose
  `${...}` segments are literals or static-known names — else `UnsupportedLabel`;
- `const MAX_ROUNDS = <int>` — else `MissingMaxRounds`;
- `while`/`for` loops whose `continue` targets re-enter an earlier agent — loop-back
  edges; unsupported control flow → `UnsupportedControlFlow`;
- early `return <literal outcome>` — terminal edges; computed outcomes →
  `UnsupportedTerminal`;
- `if`-guarded `agent()` — conditional node; else `UnsupportedConditional`;
- `Promise.all([agent(...), ...])` groups — parallel nodes; else `UnsupportedParallel`.

Each failure names the construct class and cites file:line. The parser never emits a
best-effort graph for input outside this subset (D4).

## `graph_source/parse_failures.py`

```
class ParseFailure(ABC):     # code: str (stable machine code), message: str,
                             # location: SourceLocation, context: str (the offending line)
class UnsupportedLabel(ParseFailure): ...
class MissingMaxRounds(ParseFailure): ...
class UnsupportedControlFlow(ParseFailure): ...
class UnsupportedTerminal(ParseFailure): ...
class UnsupportedConditional(ParseFailure): ...
class UnsupportedParallel(ParseFailure): ...
def summarise(failures: Sequence[ParseFailure]) -> str    # one line per failure
```

`code` values are stable strings the command template can quote verbatim (D4: "give the
agentic yaml generator some information to work with").

## `graph_source/agent_prompt.py`

```
def build_fallback_prompt(workflow_path: Path,
                          failures: Sequence[ParseFailure],
                          viz_dir: Path) -> str
```

Produces the prompt the `/viz` command agent runs: the failure summary, the supported
viz.yaml schema reference, the target path `<viz_dir>/<workflow>.viz.yaml`, and the
instruction that the written yaml must load under `Graph.load` with zero errors.
Pure derivation from `ParseFailure` values (no I/O).

## `graph/graph.py` (unit-1 addition)

```
Graph.to_yaml() -> str        # inverse of Graph.load's schema; round-trips losslessly
```

The serialized form is byte-compatible with the hand-authored schema (D5: one contract).
The entity owns its persistence (DOMAIN-08).

## `invoke/bootstrap.py`

```
run(payload: WorkflowHookPayload, cwd: Path) -> None     # never raises; silent
```

1. `Connection.read()` → if a connection file exists, probe `/graph` with the token;
   a live server is reused as-is (Q2: start-or-reuse via server.json).
2. No live server:
   a. statically parse the invoked workflow (path derived from the PreToolUse payload);
   b. on `Graph`: write the transient cache yaml to the state dir and spawn
      `serve --port 0 --graph <cache>` detached, with stdout/stderr to a state-dir log
      file — never the hook's streams (NFR2);
   c. on `ParseFailure`: spawn `serve` with no `--graph` (linear mode); the dashboard's
      existing unmapped-step warning surfaces the degradation (NFR4, Wrinkle 2);
   d. wait, bounded (a few seconds), for the connection file to appear;
   e. open the dashboard URL in the default browser (`open`/`xdg-open`, Q2b) using the
      token from the connection file.
3. The `run_start` event forwards through the existing normalise→POST /ingest path
   (unchanged hook forwarding).
4. Every failure path is swallowed by the dispatcher's silence wrapper.

## `dashboard/connection_file.py` (unit-1 addition)

```
Connection.stop_server() -> None      # POST /shutdown with Bearer token, 1s timeout
                                       # (mirrors hook_command's /ingest POST; empty ProxyHandler)
```

`LOOPBACK_ADDRESS` relocates from `dashboard/server.py` to this module (both `stop_server`
and the hook path read it here; importing `server` from `connection_file` would cycle).

## `dashboard/server.py` (unit-1 addition)

```
POST /shutdown                        # Bearer token + Host allowlist (same checks as /ingest)
```

Stops the server and removes its connection file if it still holds the server's token —
the same shutdown sequence as SIGINT today. 401 on a missing/wrong token, 204 on
success. The server owns its own lifecycle; there is no PID handling anywhere.

## `workflow/hook_command.py` (unit-1 change)

The dispatcher (D10): after `normalise`, keyed on `hook_event_name`:

| Payload | Behaviour |
| --- | --- |
| Workflow `PreToolUse` | `invoke.bootstrap.run(...)` then forward the event as today |
| `SessionEnd` | `invoke.shutdown.run()` (no forward) |
| everything else | forward only, exactly as today |

The `run_hook` silence wrapper (suppress `BaseException`, exit 0, no output) is
unchanged and covers the new branches.
