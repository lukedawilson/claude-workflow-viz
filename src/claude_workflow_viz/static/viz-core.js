// Pure core of the visualiser UI: no DOM and no browser globals, so `node --test` can run it.
// Status words come from the rules data passed in (status_rules.json), never from this file.

const LABEL_ESCAPES = [
  ["#", "#35;"],
  ['"', "#quot;"],
  ["[", "#91;"],
  ["]", "#93;"],
  ["<", "#lt;"],
  [">", "#gt;"],
];

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (character) => HTML_ESCAPES[character]);
}

// Maps keyed by a server-supplied id have no prototype, so ids such as `__proto__` and
// `constructor` are ordinary keys. `{...x}` would give back an Object.prototype object.
function dictionary(source) {
  return Object.assign(Object.create(null), source);
}

const compiledPatterns = new Map();

// A pattern that does not compile is remembered as null, so it is not retried for every event.
function compilePattern(pattern) {
  if (!compiledPatterns.has(pattern)) {
    try {
      // Python spells a named group (?P<name>...); JavaScript spells it (?<name>...).
      compiledPatterns.set(pattern, new RegExp(`^(?:${pattern.replace(/\(\?P</g, "(?<")})$`));
    } catch (error) {
      if (!(error instanceof SyntaxError)) {
        throw error;
      }
      compiledPatterns.set(pattern, null);
    }
  }
  return compiledPatterns.get(pattern);
}

function nodeFor(graph, key) {
  const node = graph.nodes.find((item) => item.stage === key || item.step_key === key);
  return node ? node.id : null;
}

function present(value) {
  return value !== undefined && value !== null && value !== "";
}

/** Map an event (or snapshot step) to {nodeId, slice, round}, or null when it maps to no node. */
export function parseStepIdentity(event, graph) {
  let { slice, stage, round } = event;
  const stepKey = event.step_key ?? "";
  let nodeId = present(stage) ? nodeFor(graph, stage) : null;
  if (nodeId === null && graph.step_pattern && stepKey) {
    const match = compilePattern(graph.step_pattern)?.exec(stepKey);
    if (match?.groups) {
      slice = present(slice) ? slice : match.groups.slice;
      round = present(round) ? round : match.groups.round;
      nodeId = match.groups.stage ? nodeFor(graph, match.groups.stage) : null;
    }
  }
  if (nodeId === null && stepKey) {
    nodeId = nodeFor(graph, stepKey);
  }
  if (nodeId === null) {
    return null;
  }
  const parsedRound = present(round) ? Number(round) : null;
  return {
    nodeId,
    slice: present(slice) ? slice : "",
    round: Number.isInteger(parsedRound) ? parsedRound : null,
  };
}

/** Status of one instance (a snapshot-step-shaped object, or null) under the shared rules. */
export function nodeStatus(instance, rules) {
  if (instance === null || instance === undefined) {
    return "pending";
  }
  if (!instance.finished) {
    return Number.isInteger(instance.round) && instance.round > 1 ? "retry" : "running";
  }
  const verdicts = Object.fromEntries(
    Object.entries(rules.verdicts).map(([name, status]) => [name.toLowerCase(), status]),
  );
  const result = instance.result;
  if (result !== null && typeof result === "object" && !Array.isArray(result)) {
    for (const field of rules.fields) {
      const value = result[field];
      if (typeof value === "string" && Object.hasOwn(verdicts, value.toLowerCase())) {
        return verdicts[value.toLowerCase()];
      }
    }
  }
  const statuses = instance.statuses ?? [];
  const last = statuses[statuses.length - 1];
  return last === "pass" || last === "fail" ? last : "pass";
}

// JSON with object keys sorted at every depth, so key order never changes the text.
function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item ?? null)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const members = Object.keys(value)
      .sort()
      .filter((name) => value[name] !== undefined)
      .map((name) => `${JSON.stringify(name)}:${stableStringify(value[name])}`);
    return `{${members.join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

/** Events carry no id: identity is the stable JSON of the fields that distinguish one occurrence. */
export function eventIdentity(event) {
  return stableStringify([
    event.session_id,
    event.ts,
    event.kind,
    event.step_key,
    event.agent_id ?? "",
    event.status,
    event.run_id ?? "",
    event.summary ?? "",
    event.result ?? null,
  ]);
}

// A step that maps to no graph node still counts toward its run, so it gets its own instance.
function unmappedIdentity(stepKey) {
  return { nodeId: null, slice: "", round: null, stepKey };
}

function instanceKey(identity) {
  return JSON.stringify([identity.slice, identity.nodeId, identity.round, identity.stepKey ?? ""]);
}

function newInstance(identity, sequence) {
  return {
    nodeId: identity.nodeId,
    slice: identity.slice,
    round: identity.round,
    stepKey: identity.stepKey ?? "",
    statuses: [],
    summary: "",
    finished: false,
    agentId: "",
    runId: "",
    result: null,
    sequence,
  };
}

function refreshRun(runs, stopped, instances, runId) {
  if (stopped[runId]) {
    return Object.assign(dictionary(runs), { [runId]: "finished" });
  }
  const members = Object.values(instances).filter((item) => item.runId === runId);
  const status = members.some((item) => !item.finished) ? "running" : "finished";
  return Object.assign(dictionary(runs), { [runId]: status });
}

/** Build state for one session from a /stream snapshot. */
export function initialState(snapshot, sessionId, graph = { nodes: [] }) {
  const sessions = snapshot?.sessions;
  const session =
    sessions && Object.hasOwn(sessions, sessionId)
      ? sessions[sessionId]
      : { steps: {}, runs: {}, events: [] };
  const state = {
    sessionId,
    instances: dictionary(),
    runs: dictionary(),
    stopped: dictionary(),
    seen: dictionary(),
    nextSequence: 0,
  };
  for (const [stepKey, step] of Object.entries(session.steps ?? {})) {
    const identity = parseStepIdentity({ ...step, step_key: stepKey }, graph);
    const resolved = identity ?? unmappedIdentity(stepKey);
    state.instances[instanceKey(resolved)] = {
      ...newInstance(resolved, state.nextSequence),
      statuses: [...(step.statuses ?? [])],
      summary: step.summary ?? "",
      finished: Boolean(step.finished),
      agentId: step.agent_id ?? "",
      runId: step.run_id ?? "",
      result: step.result ?? null,
    };
    state.nextSequence += 1;
  }
  for (const [runId, run] of Object.entries(session.runs ?? {})) {
    state.runs[runId] = run.status;
    if (run.stopped) {
      state.stopped[runId] = true;
    }
  }
  for (const event of session.events ?? []) {
    state.seen[eventIdentity(event)] = true;
    if (event.kind === "run_stop" && event.run_id) {
      state.stopped[event.run_id] = true;
    }
  }
  return state;
}

const STEP_KINDS = ["step_start", "step_stop"];

/** Reducer: returns a new state, or the same state for a repeated or foreign-session event. */
export function applyEvent(state, event, graph, rules) {
  void rules;
  if (event.session_id !== state.sessionId) {
    return state;
  }
  const identityKey = eventIdentity(event);
  if (state.seen[identityKey]) {
    return state;
  }
  const next = { ...state, seen: Object.assign(dictionary(state.seen), { [identityKey]: true }) };
  if (!STEP_KINDS.includes(event.kind)) {
    if (event.run_id) {
      if (event.kind === "run_stop") {
        next.stopped = Object.assign(dictionary(state.stopped), { [event.run_id]: true });
      }
      next.runs = dictionary(state.runs);
      if (event.kind === "run_stop") {
        next.runs[event.run_id] = "finished";
      } else if (!(event.run_id in next.runs)) {
        next.runs[event.run_id] = "running";
      }
    }
    return next;
  }
  const identity = parseStepIdentity(event, graph) ?? unmappedIdentity(event.step_key);
  let key = event.agent_id
    ? Object.keys(state.instances).find((name) => state.instances[name].agentId === event.agent_id)
    : undefined;
  if (key === undefined) {
    key = instanceKey(identity);
  }
  const existing = state.instances[key];
  const base = existing ?? newInstance(identity, state.nextSequence);
  if (!existing) {
    next.nextSequence = state.nextSequence + 1;
  }
  const isLateStart = Boolean(event.agent_id) && event.kind === "step_start" && base.finished;
  const instance = {
    ...base,
    statuses: isLateStart ? base.statuses : [...base.statuses, event.status],
    finished: event.kind === "step_stop" || (base.finished && isLateStart),
    summary: event.summary ? event.summary : base.summary,
    result: event.result !== undefined && event.result !== null ? event.result : base.result,
    agentId: event.agent_id ? event.agent_id : base.agentId,
    runId: event.run_id ? event.run_id : base.runId,
  };
  next.instances = Object.assign(dictionary(state.instances), { [key]: instance });
  if (instance.runId) {
    next.runs = refreshRun(state.runs, state.stopped, next.instances, instance.runId);
  }
  return next;
}

export function runStatus(state, runId) {
  return state.runs[runId] ?? null;
}

function sliceInstances(state, slice) {
  return Object.values(state.instances)
    .filter((item) => item.nodeId !== null && item.slice === slice)
    .sort((left, right) => left.sequence - right.sequence);
}

/** Edge from the previous finished node to the node currently running in `slice`, else null. */
export function activeEdge(state, graph, slice) {
  void graph;
  const instances = sliceInstances(state, slice);
  const running = instances.findLast((item) => !item.finished);
  if (running === undefined) {
    return null;
  }
  const previous = instances.findLast((item) => item.finished && item.sequence < running.sequence);
  return previous === undefined ? null : { from: previous.nodeId, to: running.nodeId };
}

/** on_fail edges whose target was re-entered with round > 1, from the node that ran just before. */
export function loopBackEdges(state, graph, slice) {
  const instances = sliceInstances(state, slice);
  const edges = [];
  for (const reentry of instances.filter((item) => item.round > 1)) {
    const sources = graph.nodes.filter((node) => node.on_fail === reentry.nodeId).map((node) => node.id);
    const failing = instances.findLast(
      (item) => item.sequence < reentry.sequence && sources.includes(item.nodeId),
    );
    if (failing !== undefined && !edges.some((e) => e.from === failing.nodeId && e.to === reentry.nodeId)) {
      edges.push({ from: failing.nodeId, to: reentry.nodeId });
    }
  }
  return edges;
}

function escapeLabel(text) {
  return LABEL_ESCAPES.reduce(
    (escaped, [character, entity]) => escaped.split(character).join(entity),
    String(text),
  );
}

/** Map from graph node id to its Mermaid id (n0, n1...) because `end` and hyphens are unsafe. */
export function mermaidIds(graph) {
  return new Map(graph.nodes.map((node, index) => [node.id, `n${index}`]));
}

/** Mermaid node id (`n0`) from a rendered node element id such as `workflow-graph-1-flowchart-n0-0`. */
export function mermaidNodeIdFromElementId(elementId) {
  const match = /(?:^|-)flowchart-(n\d+)-\d+$/.exec(elementId);
  return match ? match[1] : null;
}

/** Edge ends from a rendered edge element id such as `workflow-graph-1-L_n0_n1_0`. */
export function mermaidEdgeEndsFromElementId(elementId) {
  const match = /(?:^|-)L_(n\d+)_(n\d+)_\d+$/.exec(elementId);
  return match ? { from: match[1], to: match[2] } : null;
}

/** Mermaid `flowchart TD` text. */
export function buildFlowchart(graph) {
  const ids = mermaidIds(graph);
  const lines = ["flowchart TD"];
  for (const node of graph.nodes) {
    const label = `"${escapeLabel(node.label)}"`;
    lines.push(`  ${ids.get(node.id)}${node.terminal ? `([${label}])` : `[${label}]`}`);
  }
  for (const node of graph.nodes) {
    if (node.on_pass && ids.has(node.on_pass)) {
      lines.push(`  ${ids.get(node.id)} --> ${ids.get(node.on_pass)}`);
    }
    if (node.on_fail && ids.has(node.on_fail)) {
      lines.push(`  ${ids.get(node.id)} -.->|fail| ${ids.get(node.on_fail)}`);
    }
  }
  return lines.join("\n");
}

/** Serialised graph, compared to decide whether the SVG must be rendered again. */
export function graphFingerprint(graph) {
  return JSON.stringify(graph);
}

/** True when `graph` differs from the graph that was last rendered (`null` means none yet). */
export function graphChanged(renderedFingerprint, graph) {
  return renderedFingerprint !== graphFingerprint(graph);
}

/** In a linear graph, a step with no node means the graph must be fetched again. */
export function needsGraphRefetch(source, graph, event) {
  return (
    source === "linear" &&
    STEP_KINDS.includes(event.kind) &&
    parseStepIdentity(event, graph) === null
  );
}

/** Every slice that has a mapped step, sorted; the no-slice instances belong to all of them. */
export function sliceNames(state) {
  const names = new Set(
    Object.values(state.instances)
      .filter((item) => item.nodeId !== null && item.slice !== "")
      .map((item) => item.slice),
  );
  return [...names].sort();
}

/** State restricted to one slice, with the no-slice instances (such as the planner) shown on it. */
export function sliceView(state, slice) {
  const instances = dictionary();
  for (const [key, item] of Object.entries(state.instances)) {
    if (item.nodeId !== null && (item.slice === slice || item.slice === "")) {
      instances[key] = { ...item, slice };
    }
  }
  return { ...state, instances };
}

/** Instances of one node in a view, ordered by round then arrival. */
export function instancesForNode(view, nodeId) {
  return Object.values(view.instances)
    .filter((item) => item.nodeId === nodeId)
    .sort((left, right) => (left.round ?? 0) - (right.round ?? 0) || left.sequence - right.sequence);
}

/** What the DOM needs for one slice: a status class per Mermaid node id and the edges to mark. */
export function viewClasses(state, graph, rules, slice) {
  const view = sliceView(state, slice);
  const ids = mermaidIds(graph);
  const nodes = {};
  for (const node of graph.nodes) {
    const latest = Object.values(view.instances)
      .filter((item) => item.nodeId === node.id)
      .sort((left, right) => left.sequence - right.sequence)
      .at(-1);
    nodes[ids.get(node.id)] = `status-${nodeStatus(latest ?? null, rules)}`;
  }
  return {
    nodes,
    activeEdge: activeEdge(view, graph, slice),
    loopBackEdges: loopBackEdges(view, graph, slice),
  };
}

/** Verdict and note of a structured step result; the verdict field names come from the rules. */
export function describeResult(result, rules) {
  const empty = { verdict: "", note: "" };
  if (result === null || typeof result !== "object" || Array.isArray(result)) {
    return empty;
  }
  const field = rules.fields.find((name) => typeof result[name] === "string");
  return {
    verdict: field === undefined ? "" : result[field],
    note: typeof result.note === "string" ? result.note : "",
  };
}

/** Steps that map to no node, in arrival order, so the page can list what the graph cannot show. */
export function unmappedSteps(state, rules) {
  return Object.values(state.instances)
    .filter((item) => item.nodeId === null)
    .sort((left, right) => left.sequence - right.sequence)
    .map((item) => ({ stepKey: item.stepKey, status: nodeStatus(item, rules) }));
}

/** Run banner: running while any run runs, finished once every known run is, else waiting. */
export function bannerStatus(state) {
  const statuses = Object.keys(state.runs).map((runId) => runStatus(state, runId));
  if (statuses.length === 0) {
    return "waiting";
  }
  return statuses.includes("running") ? "running" : "finished";
}

/** The chosen slice if still available, else the first available slice, else null. */
export function chooseSlice(availableSlices, chosenSlice) {
  if (chosenSlice !== null && availableSlices.includes(chosenSlice)) {
    return chosenSlice;
  }
  return availableSlices[0] ?? null;
}

/** Seconds to wait before graph load attempt number `attempt` (1-based): 2, 4, 8, then 15. */
export function graphRetryDelaySeconds(attempt) {
  return [2, 4, 8][attempt - 1] ?? 15;
}

/** Map session id -> workflow name, from run_start events in the snapshot then the live log. */
export function sessionWorkflows(snapshot, log) {
  const workflows = dictionary();
  for (const [sessionId, session] of Object.entries(snapshot?.sessions ?? {})) {
    for (const event of session.events ?? []) {
      if (event.kind === "run_start" && event.workflow) {
        workflows[sessionId] = event.workflow;
      }
    }
  }
  for (const event of log ?? []) {
    if (event.kind === "run_start" && event.workflow) {
      workflows[event.session_id] = event.workflow;
    }
  }
  return workflows;
}

/** Distinct workflow names, sorted. */
export function workflowNames(workflows) {
  return [...new Set(Object.values(workflows))].sort();
}
