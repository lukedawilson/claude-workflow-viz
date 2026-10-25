// Browser page: wires the pure core (viz-core.js) to Mermaid, the SSE stream and the DOM.
// Event text reaches the DOM only through textContent; Mermaid's SVG is parsed with DOMParser.
import {
  applyEvent,
  bannerStatus,
  chooseSlice,
  buildFlowchart,
  describeResult,
  graphChanged,
  graphRetryDelaySeconds,
  graphFingerprint,
  initialState,
  instancesForNode,
  mermaidEdgeEndsFromElementId,
  mermaidIds,
  mermaidNodeIdFromElementId,
  needsGraphRefetch,
  nodeStatus,
  sessionWorkflows,
  sliceNames,
  sliceView,
  viewClasses,
  workflowNames,
  unmappedSteps,
} from "./viz-core.js";

const token = new URLSearchParams(location.search).get("token") ?? "";
const query = `?token=${encodeURIComponent(token)}`;
const urlWorkflow = new URLSearchParams(location.search).get("workflow") ?? "";

const elements = {
  banner: document.getElementById("banner"),
  graph: document.getElementById("graph"),
  workflow: document.getElementById("workflow-selector"),
  slice: document.getElementById("slice-selector"),
  round: document.getElementById("round-selector"),
  console: document.getElementById("console"),
  title: document.getElementById("console-title"),
  status: document.getElementById("console-status"),
  verdict: document.getElementById("console-verdict"),
  note: document.getElementById("console-note"),
  summary: document.getElementById("console-summary"),
  result: document.getElementById("console-result"),
  unmapped: document.getElementById("unmapped"),
  message: document.getElementById("message"),
};

const page = {
  graph: { nodes: [] },
  source: "linear",
  rules: { fields: [], verdicts: {} },
  snapshot: { sessions: {} },
  log: [],
  states: Object.create(null),
  workflows: Object.create(null),
  chosenWorkflow: urlWorkflow || null,
  sessionId: null,
  renderedFingerprint: null,
  chosenSlice: null,
  selectedNode: null,
  chosenRound: null,
  renderCount: 0,
};

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
  flowchart: { htmlLabels: false },
});

function showMessage(text) {
  elements.message.textContent = text;
}

async function fetchGraph() {
  const params = new URLSearchParams({ token });
  const workflow = activeWorkflow();
  if (workflow) {
    params.set("workflow", workflow);
  }
  const response = await fetch(`/graph?${params}`);
  if (!response.ok) {
    throw new Error(`GET /graph answered ${response.status}`);
  }
  const document_ = await response.json();
  page.graph = document_.graph;
  page.source = document_.source;
  page.rules = document_.status_rules;
}

function activeWorkflow() {
  page.workflows = sessionWorkflows(page.snapshot, page.log);
  if (page.chosenWorkflow) {
    return page.chosenWorkflow;
  }
  return page.workflows[page.sessionId] ?? "";
}

function rebuildStates() {
  page.states = Object.create(null);
  for (const sessionId of Object.keys(page.snapshot.sessions ?? {})) {
    page.states[sessionId] = initialState(page.snapshot, sessionId, page.graph);
  }
  for (const event of page.log) {
    const state =
      page.states[event.session_id] ?? initialState(page.snapshot, event.session_id, page.graph);
    page.states[event.session_id] = applyEvent(state, event, page.graph, page.rules);
  }
}

function currentState() {
  return page.states[page.sessionId] ?? null;
}

function currentSlice(state) {
  const names = sliceNames(state);
  if (page.chosenSlice !== null) {
    page.chosenSlice = chooseSlice(names, page.chosenSlice);
    return page.chosenSlice ?? "";
  }
  const latest = Object.values(state.instances)
    .filter((item) => item.nodeId !== null && item.slice !== "")
    .sort((left, right) => right.sequence - left.sequence)[0];
  return latest?.slice ?? names[0] ?? "";
}

// The only place mermaid.render is called, and only when the graph differs from the drawn one.
async function renderGraphIfChanged() {
  if (page.graph.nodes.length === 0 || !graphChanged(page.renderedFingerprint, page.graph)) {
    return;
  }
  const fingerprint = graphFingerprint(page.graph);
  page.renderCount += 1;
  const { svg } = await mermaid.render(`workflow-graph-${page.renderCount}`, buildFlowchart(page.graph));
  const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
  if (parsed.querySelector("parsererror")) {
    throw new Error("Mermaid produced SVG that could not be parsed");
  }
  elements.graph.replaceChildren(document.importNode(parsed.documentElement, true));
  page.renderedFingerprint = fingerprint;
  elements.graph.querySelector("svg").addEventListener("click", onGraphClick);
}

function mermaidIdOf(element) {
  return mermaidNodeIdFromElementId(element.id);
}

const STATUS_CLASSES = ["pending", "running", "retry", "pass", "fail", "skipped"].map(
  (name) => `status-${name}`,
);

function edgeEnds(element) {
  return mermaidEdgeEndsFromElementId(element.id);
}

function hasEdge(list, ends) {
  return list.some((edge) => edge.from === ends.from && edge.to === ends.to);
}

// Status changes only touch classes on the SVG that is already drawn.
function applyClasses() {
  const state = currentState();
  const svg = elements.graph.querySelector("svg");
  if (state === null || svg === null) {
    return;
  }
  const slice = currentSlice(state);
  const classes = viewClasses(state, page.graph, page.rules, slice);
  const ids = mermaidIds(page.graph);
  const toMermaid = (edge) => edge && { from: ids.get(edge.from), to: ids.get(edge.to) };
  const active = toMermaid(classes.activeEdge);
  const loopBack = classes.loopBackEdges.map(toMermaid);
  const skipped = new Set([...classes.skipped].map((nodeId) => ids.get(nodeId)));
  for (const node of svg.querySelectorAll("g.node")) {
    const id = mermaidIdOf(node);
    node.classList.remove(...STATUS_CLASSES);
    if (id !== null && skipped.has(id)) {
      node.classList.add("status-skipped");
    } else if (id !== null && classes.nodes[id]) {
      node.classList.add(classes.nodes[id]);
    }
    node.classList.toggle("selected", id !== null && id === ids.get(page.selectedNode));
  }
  for (const edge of svg.querySelectorAll(".flowchart-link")) {
    const ends = edgeEnds(edge);
    const skippedEnd = ends !== null && (skipped.has(ends.from) || skipped.has(ends.to));
    edge.classList.toggle("edge-active", ends !== null && active !== null && hasEdge([active], ends));
    edge.classList.toggle("edge-loop-back", ends !== null && hasEdge(loopBack, ends));
    edge.classList.toggle("edge-skipped", skippedEnd);
  }
}

function renderBanner() {
  const state = currentState();
  const status = state === null ? "waiting" : bannerStatus(state);
  elements.banner.textContent = status;
  elements.banner.className = `banner banner-${status}`;
}

// Steps with no node on the graph (a label the config does not map) are listed, never dropped.
function renderUnmapped() {
  const state = currentState();
  const steps = state === null ? [] : unmappedSteps(state, page.rules);
  elements.unmapped.hidden = steps.length === 0;
  elements.unmapped.textContent =
    steps.length === 0
      ? ""
      : `Not on the graph: ${steps.map((step) => `${step.stepKey} (${step.status})`).join(", ")}`;
}

function fillSelect(select, values, selected) {
  const current = [...select.options].map((option) => option.value);
  if (current.join("\n") !== values.join("\n")) {
    select.replaceChildren(
      ...values.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value === "" ? "(no slice)" : value;
        return option;
      }),
    );
  }
  select.value = selected;
}

function renderSliceSelector() {
  const state = currentState();
  if (state === null) {
    return;
  }
  const names = sliceNames(state);
  fillSelect(elements.slice, names.length > 0 ? names : [""], currentSlice(state));
}

function renderWorkflowSelector() {
  const names = workflowNames(page.workflows);
  if (page.chosenWorkflow && !names.includes(page.chosenWorkflow)) {
    names.unshift(page.chosenWorkflow);
  }
  if (names.length === 0) {
    elements.workflow.hidden = true;
    return;
  }
  elements.workflow.hidden = false;
  const selected = page.chosenWorkflow ?? page.workflows[page.sessionId] ?? names[0];
  fillSelect(elements.workflow, names, selected);
}

function renderConsole() {
  const state = currentState();
  if (state === null || page.selectedNode === null) {
    elements.console.hidden = true;
    return;
  }
  const view = sliceView(state, currentSlice(state));
  const instances = instancesForNode(view, page.selectedNode);
  const node = page.graph.nodes.find((item) => item.id === page.selectedNode);
  elements.console.hidden = false;
  elements.title.textContent = node ? node.label : page.selectedNode;
  const rounds = instances.map((item) => String(item.round ?? 1));
  const latest = rounds.at(-1) ?? "";
  const round = rounds.includes(page.chosenRound) ? page.chosenRound : latest;
  fillSelect(elements.round, rounds, round);
  const instance = instances.find((item) => String(item.round ?? 1) === round) ?? null;
  const described = describeResult(instance?.result ?? null, page.rules);
  elements.status.textContent = nodeStatus(instance, page.rules);
  elements.verdict.textContent = described.verdict;
  elements.note.textContent = described.note;
  elements.summary.textContent = instance?.summary ?? "";
  elements.result.textContent =
    instance?.result === null || instance?.result === undefined
      ? ""
      : JSON.stringify(instance.result, null, 2);
}

function refresh() {
  renderBanner();
  renderUnmapped();
  renderSliceSelector();
  renderWorkflowSelector();
  applyClasses();
  renderConsole();
}

function onGraphClick(clickEvent) {
  const element = clickEvent.target.closest("g.node");
  const id = element === null ? null : mermaidIdOf(element);
  const entry = [...mermaidIds(page.graph)].find(([, value]) => value === id);
  if (entry === undefined) {
    return;
  }
  page.selectedNode = entry[0];
  page.chosenRound = null;
  refresh();
}

elements.slice.addEventListener("change", () => {
  page.chosenSlice = elements.slice.value;
  page.chosenRound = null;
  refresh();
});

elements.workflow.addEventListener("change", async () => {
  page.chosenWorkflow = elements.workflow.value;
  await refetchGraph();
});

elements.round.addEventListener("change", () => {
  page.chosenRound = elements.round.value;
  renderConsole();
});

async function onSnapshot(message) {
  page.snapshot = JSON.parse(message.data);
  page.log = [];
  const sessionIds = Object.keys(page.snapshot.sessions ?? {});
  page.sessionId = sessionIds.at(-1) ?? page.sessionId;
  if (page.source === "linear" || activeWorkflow()) {
    await fetchGraph();
  }
  rebuildStates();
  await renderGraphIfChanged();
  refresh();
}

async function onEvent(message) {
  const event = JSON.parse(message.data);
  const previousWorkflow = activeWorkflow();
  page.log.push(event);
  page.sessionId = event.session_id;
  if (needsGraphRefetch(page.source, page.graph, event) || activeWorkflow() !== previousWorkflow) {
    await fetchGraph();
    rebuildStates();
  } else {
    const state =
      page.states[event.session_id] ?? initialState(page.snapshot, event.session_id, page.graph);
    page.states[event.session_id] = applyEvent(state, event, page.graph, page.rules);
  }
  await renderGraphIfChanged();
  refresh();
}

async function refetchGraph() {
  try {
    await fetchGraph();
    rebuildStates();
    await renderGraphIfChanged();
    refresh();
    showMessage("");
  } catch (error) {
    showMessage(`graph load failed: ${error}`);
  }
}

function sleep(seconds) {
  return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
}

async function loadGraphWithRetry() {
  for (let attempt = 1; ; attempt += 1) {
    try {
      await fetchGraph();
      await renderGraphIfChanged();
      showMessage("");
      return;
    } catch (error) {
      const delay = graphRetryDelaySeconds(attempt);
      showMessage(`graph load failed: ${error}; retrying in ${delay}s`);
      await sleep(delay);
    }
  }
}

async function start() {
  await loadGraphWithRetry();
  const stream = new EventSource(`/stream${query}`);
  stream.addEventListener("snapshot", (message) => onSnapshot(message).catch(showError));
  stream.addEventListener("event", (message) => onEvent(message).catch(showError));
  stream.addEventListener("error", () => showMessage("stream disconnected, retrying"));
  stream.addEventListener("open", () => showMessage(""));
}

function showError(error) {
  showMessage(String(error));
}

start();
