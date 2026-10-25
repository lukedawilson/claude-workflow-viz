# API Documentation

## REST APIs

All endpoints are served on 127.0.0.1 only. The Host check runs first, then the token check,
before the body is read. Errors are empty-body responses.

### POST /ingest
- **Method**: POST
- **Path**: /ingest
- **Purpose**: Ingest one normalised hook event into the run state.
- **Request**: Header `Authorization: Bearer <token>`. Body: one JSON event (see Data Models:
  Event). At most 65536 bytes (`MAXIMUM_BODY_BYTES`).
- **Response**: 204 No Content (applied); 400 Bad Request (bad JSON or invalid event — the
  body is rejected without being applied); 401 Unauthorized (missing or wrong token);
  413 Request Entity Too Large (body over the cap; a bounded amount is drained so the client
  can read the response); 421 Misdirected Request (Host not `127.0.0.1:<port>` or
  `localhost:<port>`); 404 for any other path. A body shorter than its Content-Length closes
  the connection once the read times out.

### GET /stream
- **Method**: GET
- **Path**: /stream?token=<token>
- **Purpose**: Live server-sent events stream. The token is a query parameter because a
  browser `EventSource` cannot set headers.
- **Request**: Query parameter `token`.
- **Response**: `text/event-stream`. First one `snapshot` event holding the current run
  state, then one `event` per applied event; a `: keep-alive` comment every
  `keepalive_seconds` (default 15) when idle. Subscribing and snapshotting happen under one
  lock, so each event is in the snapshot or delivered afterwards — never lost, never in both.
  401 on a wrong token; 421 on a disallowed Host.

### GET /graph
- **Method**: GET
- **Path**: /graph?token=<token>
- **Purpose**: The graph document the UI renders: nodes, edges and the shared status rules.
- **Request**: Query parameter `token`.
- **Response**: JSON `{"graph", "source", "status_rules"}`. `source` is `config` when
  `serve --graph` supplied the graph, else `linear` (one node per stage, or step key when a
  step has no stage, seen so far in first-seen order). `status_rules` is the content of
  `status_rules.json`. 401 on a wrong token; 421 on a disallowed Host.

### GET / and GET /static/<name>
- **Method**: GET
- **Path**: / (index.html) and /static/<name>
- **Purpose**: The web UI from the package's static directory.
- **Request**: none (no token required).
- **Response**: The named file with its Content-Type, `Cache-Control: no-store`, and hardened
  headers (`X-Content-Type-Options: nosniff`, a restrictive Content-Security-Policy). Only
  names found by listing the directory at start with a `.html`, `.js`, `.css` or `.json`
  extension are served; anything else (including `VENDORED.md`, `mermaid.LICENSE` and
  traversal attempts) answers 404.

## Internal APIs

### Event (events.py)
- **Methods**: `Event.from_dict(data) -> EventResult` (validates and builds, never raises;
  returns `EventError` on any problem); `Event.to_dict() -> dict` (JSON-serialisable, omits
  unset optional fields).
- **Parameters**: `data` is a mapping with required `session_id` (non-empty string),
  `ts` (finite number of epoch seconds), `kind`, `step_key`, `status`, `summary`; optional
  `agent_id`, `run_id`, `slice`, `stage`, `round` (integer or null, not bool), `phase`,
  `result` (bounded structured JSON).
- **Return Types**: `EventResult = Event | EventError`; `EventError` carries a typed
  `EventErrorCode` and a message.

### normalise (hook_adapter.py)
- **Methods**: `normalise(payload, now) -> Event | None | EventError`;
  `step_key_for(payload) -> str`.
- **Parameters**: `payload` is a Claude Code hook payload mapping; `now` is a callable
  returning epoch seconds (injected for tests).
- **Return Types**: `Event` for a tracked payload; `None` when the payload is not one the
  visualiser tracks (e.g. a non-Agent/Workflow tool); `EventError` when the payload is
  malformed (missing `session_id` or `hook_event_name`).

### RunState (run_state.py)
- **Methods**: `apply(event) -> None`; `snapshot(session_id=None) -> dict`;
  `subscribe_with_snapshot(session_id=None) -> (queue.Queue, dict)`;
  `subscribe() -> queue.Queue`; `unsubscribe(subscriber) -> None`.
- **Parameters**: constructor bounds `event_log_maximum`, `session_maximum`,
  `step_maximum`, `status_history_maximum` (each at least 1).
- **Return Types**: the snapshot shape
  `{"sessions": {id: {"steps": {key: step}, "runs": {run_id: {"status", "stopped",
  "step_keys"}}, "events": [event]}}}`.

### Graph (graph.py)
- **Methods**: `Graph.load(path) -> GraphResult`; `Graph.linear(step_stages) -> Graph`;
  `Graph.node_for(stage_or_step_key) -> str | None`; `Graph.to_dict() -> dict`.
- **Parameters**: `path` to a `<workflow>.viz.yaml`; `step_stages` is a sequence of stage
  names in first-seen order.
- **Return Types**: `GraphResult = Graph | GraphError` with a typed `GraphErrorCode`.

### Connection (connection_file.py)
- **Methods**: `Connection.read() -> Connection | None` (never raises);
  `Connection.write() -> Path` (atomic, 0600);
  `Connection.remove_if_token_matches(token) -> None` (deletes only while it still holds
  `token`); `generate_token() -> str`; `tokens_match(expected, provided) -> bool`
  (constant-time).
- **Parameters**: `port` (int 1-65535), `token` (non-empty string).
- **Return Types**: `Connection(port, token)` frozen dataclass; `read` returns `None` for a
  missing, unreadable or malformed file.

### verdict_status (node_status.py)
- **Methods**: `verdict_status(result) -> str | None`.
- **Parameters**: `result` is a structured step result (any JSON value).
- **Return Types**: `"pass"` or `"fail"` when `result` is a mapping holding a recognised
  verdict in one of the rule fields (read in rule order, case-insensitive); `None` otherwise.

### viz-core.js exports (pure reducer, no DOM)
- **Methods**: `initialState(snapshot, sessionId, graph)`,
  `applyEvent(state, event, graph, rules)`, `nodeStatus(instance, rules)`,
  `parseStepIdentity(event, graph)`, `activeEdge(state, graph, slice)`,
  `loopBackEdges(state, graph, slice)`, `viewClasses(state, graph, rules, slice)`,
  `describeResult(result, rules)`, `unmappedSteps(state, rules)`, `bannerStatus(state)`,
  `buildFlowchart(graph)`, `graphFingerprint(graph)`, `graphChanged(renderedFingerprint,
  graph)`, `needsGraphRefetch(source, graph, event)`, `sliceNames(state)`,
  `sliceView(state, slice)`, `instancesForNode(view, nodeId)`, `mermaidIds(graph)`,
  `mermaidNodeIdFromElementId(elementId)`, `mermaidEdgeEndsFromElementId(elementId)`,
  `chooseSlice(availableSlices, chosenSlice)`, `graphRetryDelaySeconds(attempt)`,
  `eventIdentity(event)`, `escapeHtml(text)`.
- **Parameters**: state/snapshot/graph/rules as produced by the server endpoints.
- **Return Types**: plain JSON-serialisable objects; state updates are immutable-ish
  (new objects, prototype-less maps).

## Data Models

### Event (events.py)
- **Fields**: `session_id` (str, required non-empty); `ts` (float epoch seconds);
  `kind` (EventKind: run_start, run_stop, step_start, step_stop); `step_key` (str);
  `status` (EventStatus: running, pass, fail, unknown); `summary` (str, truncated to 500
  chars); `agent_id`, `run_id`, `slice`, `stage`, `phase` (optional str, default "");
  `round` (optional int or None, never bool); `result` (optional structured JSON, bounded to
  16384 bytes compact JSON, else stored as None).
- **Relationships**: consumed by `RunState.apply`; serialised by `to_dict` for the hook POST
  and the SSE stream.
- **Validation**: `from_dict` returns typed `EventError`s (`not_mapping`, `missing_field`,
  `empty`, `not_string`, `bad_kind`, `bad_status`, `bad_timestamp`,
  `non_finite_timestamp`, `timestamp_too_large`, `bad_round`, `bad_result`,
  `result_too_deep`).

### Step (run_state.py, internal `_Step`)
- **Fields**: `statuses` (deque, max 100); `summary` (str); `finished` (bool);
  `agent_id`, `run_id`, `slice`, `stage` (str); `round` (int | None); `phase` (str);
  `result` (any, latest non-None). Snapshot adds `node_status` via `display_status()`.
- **Relationships**: one per step key per session; steps reference a run by `run_id`.
- **Validation**: only step kinds create steps; a stop with no prior start creates a finished
  step; a late start (with agent_id) on a finished step does not reopen it.

### Run (run_state.py)
- **Fields**: `status` ("running" | "finished"); `stopped` (bool, explicit run_stop);
  `step_keys` (list of step keys with that run_id).
- **Relationships**: created by a run-level event or by its first step; an explicit
  `run_stop` is final for that run id.

### Graph / Node (graph.py)
- **Fields**: Graph: `name`, `entry`, `nodes` (tuple), `max_rounds` (optional positive int),
  `on_rounds_exhausted` (node id, required when max_rounds set), `step_pattern` (optional
  regex with a named `stage` group). Node: `id`, `label`, `stage` (optional, unique),
  `step_key` (optional, unique), `terminal` (bool), `on_pass` (required on non-terminal),
  `on_fail` (optional).
- **Relationships**: a value may not be one node's stage and another's step_key; terminal
  nodes have no stage, step_key or outgoing edges; reserved terminal ids are `done`,
  `blocked`, `needs-context`.
- **Validation**: unknown and duplicate keys rejected at every level; unreadable file,
  bad YAML, unsafe patterns (length, nested quantifiers, Python-only syntax, uncompilable,
  missing stage group) and dangling references all map to typed `GraphErrorCode`s.

### Connection (connection_file.py)
- **Fields**: `port` (int), `token` (str, `secrets.token_urlsafe(32)`).
- **Relationships**: persisted as `server.json` in the state directory; written by `serve`,
  read by `hook`.
- **Validation**: `read` requires a valid port and a non-empty string token; otherwise None.
