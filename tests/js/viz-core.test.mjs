import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  activeEdge,
  applyEvent,
  bannerStatus,
  chooseSlice,
  describeResult,
  buildFlowchart,
  graphChanged,
  graphRetryDelaySeconds,
  inferSkipped,
  graphFingerprint,
  instancesForNode,
  mermaidIds,
  mermaidNodeIdFromElementId,
  mermaidEdgeEndsFromElementId,
  needsGraphRefetch,
  sliceNames,
  sliceView,
  unmappedSteps,
  viewClasses,
  escapeHtml,
  eventIdentity,
  initialState,
  loopBackEdges,
  nodeStatus,
  parseStepIdentity,
  runStatus,
  sessionWorkflows,
  workflowNames,
} from "../../src/claude_workflow_viz/static/viz-core.js";

const here = dirname(fileURLToPath(import.meta.url));
const corePath = join(here, "../../src/claude_workflow_viz/static/viz-core.js");
const rules = JSON.parse(
  readFileSync(join(here, "../../src/claude_workflow_viz/static/status_rules.json"), "utf8"),
);
const cases = JSON.parse(readFileSync(join(here, "../fixtures/status_cases.json"), "utf8"));

const STEP_PATTERN = "(?P<slice>[^/]+)/(?P<stage>[^:]+):r(?P<round>\\d+)";
const graph = {
  name: "implement",
  entry: "planner",
  step_pattern: STEP_PATTERN,
  nodes: [
    { id: "planner", label: "Planner", stage: null, step_key: "planner", terminal: false, on_pass: "develop", on_fail: "needs-context" },
    { id: "develop", label: "Develop", stage: "develop", step_key: null, terminal: false, on_pass: "gate", on_fail: "blocked" },
    { id: "gate", label: "Gate", stage: "gate", step_key: null, terminal: false, on_pass: "code-review", on_fail: "develop" },
    { id: "code-review", label: "Code review", stage: "code-review", step_key: null, terminal: false, on_pass: "done", on_fail: "develop" },
    { id: "done", label: "Done", stage: null, step_key: null, terminal: true, on_pass: null, on_fail: null },
    { id: "blocked", label: "Blocked", stage: null, step_key: null, terminal: true, on_pass: null, on_fail: null },
    { id: "needs-context", label: "Needs context", stage: null, step_key: null, terminal: true, on_pass: null, on_fail: null },
  ],
};

let clock = 0;
function event(fields) {
  clock += 1;
  return {
    session_id: "s",
    ts: clock,
    kind: "step_start",
    step_key: "",
    status: "running",
    summary: "",
    ...fields,
  };
}

const emptySnapshot = { sessions: { s: { steps: {}, runs: {}, events: [] } } };

function replay(events, snapshot = emptySnapshot) {
  return events.reduce((state, item) => applyEvent(state, item, graph, rules), initialState(snapshot, "s", graph));
}

function instanceOf(state, nodeId, round) {
  return Object.values(state.instances).find((item) => item.nodeId === nodeId && item.round === round);
}

test("parseStepIdentity maps a step label through the step pattern", () => {
  assert.deepEqual(parseStepIdentity({ step_key: "S1/code-review:r2" }, graph), {
    nodeId: "code-review",
    slice: "S1",
    round: 2,
  });
});

test("parseStepIdentity prefers explicit event fields", () => {
  const identity = parseStepIdentity(
    { step_key: "S1/gate:r1", slice: "S9", stage: "develop", round: 3 },
    graph,
  );
  assert.deepEqual(identity, { nodeId: "develop", slice: "S9", round: 3 });
});

test("parseStepIdentity maps a whole step key to a node", () => {
  assert.equal(parseStepIdentity({ step_key: "planner" }, graph).nodeId, "planner");
});

test("parseStepIdentity returns null for unmapped keys", () => {
  assert.equal(parseStepIdentity({ step_key: "agent-abc123" }, graph), null);
  assert.equal(parseStepIdentity({ step_key: "S1/unknown:r1" }, graph), null);
});

for (const item of cases.node_status) {
  test(`nodeStatus shared case: ${item.name}`, () => {
    const instance = item.step === null ? null : item.step;
    assert.equal(nodeStatus(instance, rules), item.expected);
  });
}

for (const item of cases.run_status) {
  test(`runStatus shared case: ${item.name}`, () => {
    const state = replay(item.events.map((raw) => event(raw)));
    for (const [runId, expected] of Object.entries(item.expected)) {
      assert.equal(runStatus(state, runId), expected);
    }
  });
}

test("start then stop pair by agent id across differing step keys", () => {
  const state = replay([
    event({ step_key: "S1/develop:r1", stage: "develop", slice: "S1", round: 1, agent_id: "a1" }),
    event({ kind: "step_stop", step_key: "agent-a1", status: "pass", agent_id: "a1" }),
  ]);
  const instances = Object.values(state.instances);
  assert.equal(instances.length, 1);
  assert.equal(instances[0].finished, true);
  assert.equal(nodeStatus(instances[0], rules), "pass");
});

test("stop before start yields a finished instance a later start does not reopen", () => {
  const state = replay([
    event({ kind: "step_stop", step_key: "S1/gate:r1", status: "pass", agent_id: "g1" }),
    event({ step_key: "S1/gate:r1", agent_id: "g1" }),
  ]);
  const instance = instanceOf(state, "gate", 1);
  assert.equal(instance.finished, true);
  assert.deepEqual(instance.statuses, ["pass"]);
  assert.equal(nodeStatus(instance, rules), "pass");
});

test("summary and result keep the latest non-empty value", () => {
  const state = replay([
    event({ step_key: "S1/gate:r1", summary: "first", agent_id: "g1" }),
    event({ kind: "step_stop", step_key: "S1/gate:r1", status: "pass", summary: "", result: { verdict: "FAIL" }, agent_id: "g1" }),
  ]);
  const instance = instanceOf(state, "gate", 1);
  assert.equal(instance.summary, "first");
  assert.equal(nodeStatus(instance, rules), "fail");
});

test("a round 2 develop start is retry and draws a loop-back edge from the failing stage", () => {
  const state = replay([
    event({ step_key: "S1/develop:r1", agent_id: "d1" }),
    event({ kind: "step_stop", step_key: "S1/develop:r1", status: "pass", agent_id: "d1" }),
    event({ step_key: "S1/gate:r1", agent_id: "g1" }),
    event({ kind: "step_stop", step_key: "S1/gate:r1", status: "fail", agent_id: "g1" }),
    event({ step_key: "S1/develop:r2", agent_id: "d2" }),
  ]);
  assert.equal(nodeStatus(instanceOf(state, "develop", 2), rules), "retry");
  assert.deepEqual(loopBackEdges(state, graph, "S1"), [{ from: "gate", to: "develop" }]);
  assert.deepEqual(loopBackEdges(state, graph, "S2"), []);
});

test("activeEdge runs from the previous finished node to the running node", () => {
  const state = replay([
    event({ step_key: "S1/develop:r1", agent_id: "d1" }),
    event({ kind: "step_stop", step_key: "S1/develop:r1", status: "pass", agent_id: "d1" }),
    event({ step_key: "S1/gate:r1", agent_id: "g1" }),
  ]);
  assert.deepEqual(activeEdge(state, graph, "S1"), { from: "develop", to: "gate" });
  assert.equal(activeEdge(state, graph, "S2"), null);
});

test("initialState builds instances from snapshot steps", () => {
  const snapshot = {
    sessions: {
      s: {
        steps: {
          "S1/develop:r1": {
            statuses: ["running", "pass"],
            finished: true,
            agent_id: "d1",
            run_id: "r1",
            slice: "S1",
            stage: "develop",
            round: 1,
            summary: "built",
            result: null,
          },
        },
        runs: { r1: { status: "finished", step_keys: ["S1/develop:r1"] } },
        events: [],
      },
    },
  };
  const state = initialState(snapshot, "s", graph);
  const instance = instanceOf(state, "develop", 1);
  assert.equal(instance.slice, "S1");
  assert.equal(instance.summary, "built");
  assert.equal(runStatus(state, "r1"), "finished");
});

test("an event in the snapshot events and again on the stream changes state once", () => {
  const started = event({ step_key: "S1/develop:r1", agent_id: "d1" });
  const snapshot = {
    sessions: {
      s: {
        steps: {
          "S1/develop:r1": {
            statuses: ["running"],
            finished: false,
            agent_id: "d1",
            run_id: "",
            slice: "S1",
            stage: "develop",
            round: 1,
            summary: "",
            result: null,
          },
        },
        runs: {},
        events: [started],
      },
    },
  };
  const initial = initialState(snapshot, "s", graph);
  const after = applyEvent(initial, started, graph, rules);
  assert.deepEqual(instanceOf(after, "develop", 1).statuses, ["running"]);
  const next = event({ kind: "step_stop", step_key: "S1/develop:r1", status: "pass", agent_id: "d1" });
  const once = applyEvent(after, next, graph, rules);
  const twice = applyEvent(once, next, graph, rules);
  assert.deepEqual(instanceOf(twice, "develop", 1).statuses, ["running", "pass"]);
});

test("eventIdentity separates events that differ in run, summary or result", () => {
  const base = event({ step_key: "k", agent_id: "a", run_id: "r1", summary: "one", result: { a: 1 } });
  assert.notEqual(eventIdentity(base), eventIdentity({ ...base, status: "pass" }));
  assert.notEqual(eventIdentity(base), eventIdentity({ ...base, ts: base.ts + 1 }));
  assert.notEqual(eventIdentity(base), eventIdentity({ ...base, summary: "different" }));
  assert.notEqual(eventIdentity(base), eventIdentity({ ...base, result: { a: 2 } }));
  assert.notEqual(eventIdentity(base), eventIdentity({ ...base, run_id: "r2" }));
});

test("eventIdentity ignores key order at every depth of a result", () => {
  const base = event({ step_key: "k", result: { verdict: "PASS", detail: { x: 1, y: 2 } } });
  const reordered = { ...base, result: { detail: { y: 2, x: 1 }, verdict: "PASS" } };
  assert.equal(eventIdentity(base), eventIdentity(reordered));
});

test("events identical except summary, result or run id with one timestamp are all applied", () => {
  const stop = (fields) =>
    event({ kind: "step_stop", step_key: "S1/develop:r1", status: "pass", ...fields });
  const first = stop({ summary: "one", run_id: "r1" });
  const variants = [
    first,
    { ...first, summary: "two" },
    { ...first, result: { verdict: "PASS" } },
    { ...first, run_id: "r2" },
  ];
  let state = initialState(emptySnapshot, "s", graph);
  for (const item of variants) {
    state = applyEvent(state, item, graph, rules);
  }
  assert.equal(Object.keys(state.seen).length, 4);
  assert.equal(instanceOf(state, "develop", 1).statuses.length, 4);
});

test("a snapshot event repeated on the stream with reordered result keys is applied once", () => {
  const stop = event({
    kind: "step_stop",
    step_key: "S1/develop:r1",
    status: "pass",
    result: { verdict: "PASS", detail: { x: 1, y: 2 } },
  });
  const snapshot = { sessions: { s: { steps: {}, runs: {}, events: [stop] } } };
  const initial = initialState(snapshot, "s", graph);
  const replay = { ...stop, result: { detail: { y: 2, x: 1 }, verdict: "PASS" } };
  assert.equal(applyEvent(initial, replay, graph, rules), initial);
});

test("run and session ids named after Object.prototype members are stored and read safely", () => {
  for (const id of ["__proto__", "constructor"]) {
    const absent = initialState(emptySnapshot, id);
    assert.equal(runStatus(absent, id), null);
    assert.deepEqual(Object.keys(absent.runs), []);
    const foreign = initialState({ sessions: {} }, "constructor");
    assert.deepEqual(Object.keys(foreign.instances), []);

    const state = initialState(emptySnapshot, "s", graph);
    const started = applyEvent(
      state,
      event({ kind: "step_start", step_key: "S1/develop:r1", run_id: id }),
      graph,
      rules,
    );
    assert.equal(runStatus(started, id), "running");
    const stopped = applyEvent(started, event({ kind: "run_stop", run_id: id }), graph, rules);
    assert.equal(runStatus(stopped, id), "finished");
    assert.equal(Object.getPrototypeOf(stopped.runs), null);
    assert.equal(Object.getPrototypeOf(stopped.seen), null);
    assert.equal(Object.getPrototypeOf(stopped.instances), null);
  }
  const absentRun = initialState(emptySnapshot, "s", graph);
  assert.equal(runStatus(absentRun, "__proto__"), null);
  assert.equal(runStatus(absentRun, "constructor"), null);
});

test("a session in the snapshot named __proto__ or constructor loads its own runs", () => {
  for (const id of ["__proto__", "constructor"]) {
    const sessions = JSON.parse(
      `{"${id}": {"steps": {}, "runs": {"${id}": {"status": "running"}}, "events": []}}`,
    );
    const state = initialState({ sessions }, id, graph);
    assert.equal(runStatus(state, id), "running");
  }
});

test("an invalid step_pattern falls back to the stage and step_key mapping", () => {
  const broken = { ...graph, step_pattern: "(" };
  assert.doesNotThrow(() => parseStepIdentity({ step_key: "x" }, broken));
  assert.equal(parseStepIdentity({ stage: "develop", step_key: "x" }, broken).nodeId, "develop");
  assert.equal(parseStepIdentity({ step_key: "planner" }, broken).nodeId, "planner");
  assert.equal(parseStepIdentity({ step_key: "S1/develop:r1" }, broken), null);
});

test("applyEvent does not mutate the previous state", () => {
  const before = initialState(emptySnapshot, "s", graph);
  const frozen = JSON.stringify(before);
  applyEvent(before, event({ step_key: "S1/develop:r1" }), graph, rules);
  assert.equal(JSON.stringify(before), frozen);
});

test("buildFlowchart uses sanitised ids, never a raw 'end' id", () => {
  const dangerous = {
    ...graph,
    nodes: [
      { id: "end", label: 'Say "hi" <script>[x]</script>', stage: "end", terminal: false, on_pass: "my-node", on_fail: null },
      { id: "my-node", label: "Mine", stage: "mine", terminal: true, on_pass: null, on_fail: null },
    ],
  };
  const text = buildFlowchart(dangerous);
  assert.match(text, /^flowchart TD/);
  assert.doesNotMatch(text, /(^|[\s>|])end([\s\["(]|$)/m);
  assert.doesNotMatch(text, /my-node/);
  assert.match(text, /n0/);
  assert.match(text, /n1/);
  assert.doesNotMatch(text, /<script>/);
  assert.doesNotMatch(text, /\[x\]/);
  assert.match(text, /#quot;hi#quot;/);
  assert.match(text, /#lt;script#gt;/);
});

test("buildFlowchart links on_pass and on_fail edges", () => {
  const text = buildFlowchart(graph);
  assert.match(text, /n1 -->.* n2/);
  assert.match(text, /n2 -\.->.* n1/);
});

test("escapeHtml escapes ampersand, angle brackets and both quotes", () => {
  assert.equal(escapeHtml(`&<>"'`), "&amp;&lt;&gt;&quot;&#39;");
  assert.equal(escapeHtml("plain"), "plain");
});

test("viz-core.js has no verdict literals and no browser globals", () => {
  const source = readFileSync(corePath, "utf8");
  const literals = [...source.matchAll(/(["'`])((?:\\.|(?!\1).)*)\1/g)].map((match) => match[2].toLowerCase());
  const verdicts = Object.keys(rules.verdicts).map((name) => name.toLowerCase());
  for (const literal of literals) {
    assert.ok(!verdicts.includes(literal) || ["pass", "fail"].includes(literal), `verdict literal ${literal}`);
  }
  assert.doesNotMatch(source, /["'`](PASS|FAIL)["'`]/);
  assert.doesNotMatch(source, /\b(document|window|localStorage|navigator)\b/);
});

const develop = (round, slice = "S1") =>
  event({ step_key: `${slice}/develop:r${round}`, slice, stage: "develop", round });
const stop = (round, fields = {}, slice = "S1") =>
  event({
    kind: "step_stop",
    step_key: `${slice}/gate:r${round}`,
    slice,
    stage: "gate",
    round,
    status: "pass",
    ...fields,
  });

test("graphChanged is false for an identical graph and true once a node is added", () => {
  const fingerprint = graphFingerprint(graph);
  assert.equal(graphChanged(fingerprint, structuredClone(graph)), false);
  const grown = { ...graph, nodes: [...graph.nodes, { ...graph.nodes[4], id: "extra" }] };
  assert.equal(graphChanged(fingerprint, grown), true);
  assert.equal(graphChanged(null, graph), true);
});

test("needsGraphRefetch is true only for a linear graph and a step that has no node", () => {
  const unknown = event({ step_key: "mystery", stage: "mystery" });
  assert.equal(needsGraphRefetch("linear", graph, unknown), true);
  assert.equal(needsGraphRefetch("config", graph, unknown), false);
  assert.equal(needsGraphRefetch("linear", graph, develop(1)), false);
  assert.equal(needsGraphRefetch("linear", graph, event({ kind: "run_stop" })), false);
});

test("sliceNames lists every slice seen, sorted, ignoring the no-slice instances", () => {
  const state = replay([
    event({ step_key: "planner", stage: "planner" }),
    develop(1, "S2"),
    develop(1, "S1"),
  ]);
  assert.deepEqual(sliceNames(state), ["S1", "S2"]);
});

test("sliceView shows the no-slice planner instance on every slice and hides other slices", () => {
  const state = replay([
    event({ step_key: "planner", stage: "planner" }),
    develop(1, "S1"),
    develop(1, "S2"),
  ]);
  const view = sliceView(state, "S1");
  const nodes = Object.values(view.instances).map((item) => item.nodeId).sort();
  assert.deepEqual(nodes, ["develop", "planner"]);
  assert.deepEqual(Object.values(view.instances).map((item) => item.slice), ["S1", "S1"]);
});

test("instancesForNode returns the rounds of one node in round order", () => {
  const state = replay([develop(2), develop(1)]);
  const rounds = instancesForNode(sliceView(state, "S1"), "develop").map((item) => item.round);
  assert.deepEqual(rounds, [1, 2]);
});

test("viewClasses gives each node the status of its latest instance and pending otherwise", () => {
  const state = replay([develop(1), stop(1, { result: { verdict: "FAIL" } }), develop(2)]);
  const classes = viewClasses(state, graph, rules, "S1");
  const ids = mermaidIds(graph);
  assert.equal(classes.nodes[ids.get("develop")], "status-retry");
  assert.equal(classes.nodes[ids.get("gate")], "status-fail");
  assert.equal(classes.nodes[ids.get("done")], "status-pending");
});

test("viewClasses reports the loop-back edge once develop is re-entered", () => {
  const state = replay([develop(1), stop(1, { result: { verdict: "FAIL" } }), develop(2)]);
  const classes = viewClasses(state, graph, rules, "S1");
  assert.deepEqual(classes.loopBackEdges, [{ from: "gate", to: "develop" }]);
  assert.deepEqual(classes.activeEdge, { from: "gate", to: "develop" });
});

test("mermaidIds numbers nodes in graph order, matching buildFlowchart", () => {
  const ids = mermaidIds(graph);
  assert.equal(ids.get("planner"), "n0");
  assert.match(buildFlowchart(graph), /n1\["Develop"\]/);
});

test("describeResult reads verdict and note, using the verdict fields from the shared rules", () => {
  assert.deepEqual(describeResult({ verdict: "FAIL", note: "two tests red" }, rules), {
    verdict: "FAIL",
    note: "two tests red",
  });
  assert.deepEqual(describeResult({ gate: "GREEN" }, rules), { verdict: "GREEN", note: "" });
  assert.deepEqual(describeResult(null, rules), { verdict: "", note: "" });
  assert.deepEqual(describeResult("plain text", rules), { verdict: "", note: "" });
});

test("initialState keeps a run stopped when the snapshot flags it though its stop event aged out", () => {
  const snapshot = {
    sessions: { s: { steps: {}, runs: { r1: { status: "finished", stopped: true } }, events: [] } },
  };
  const state = replay([event({ run_id: "r1", step_key: "planner", stage: "planner" })], snapshot);
  assert.equal(state.runs.r1, "finished");
});

test("bannerStatus is running while any run runs, finished once all are, else waiting", () => {
  assert.equal(bannerStatus(replay([])), "waiting");
  const running = replay([event({ run_id: "r1", step_key: "planner", stage: "planner" })]);
  assert.equal(bannerStatus(running), "running");
  const finished = applyEvent(
    running,
    event({ kind: "run_stop", run_id: "r1", step_key: "" }),
    graph,
    rules,
  );
  assert.equal(bannerStatus(finished), "finished");
  const again = applyEvent(
    finished,
    event({ run_id: "r2", step_key: "planner", stage: "planner" }),
    graph,
    rules,
  );
  assert.equal(bannerStatus(again), "running");
});

// Element ids observed from vendored Mermaid 11.17.2 rendering with render id "workflow-graph-1".
test("mermaidNodeIdFromElementId reads node ids that carry the render id prefix", () => {
  assert.equal(mermaidNodeIdFromElementId("workflow-graph-1-flowchart-n0-0"), "n0");
  assert.equal(mermaidNodeIdFromElementId("workflow-graph-12-flowchart-n13-13"), "n13");
  assert.equal(mermaidNodeIdFromElementId("flowchart-n2-2"), "n2");
  assert.equal(mermaidNodeIdFromElementId("workflow-graph-1-L_n0_n1_0"), null);
  assert.equal(mermaidNodeIdFromElementId(""), null);
});

test("mermaidEdgeEndsFromElementId reads edge ends from prefixed edge ids", () => {
  assert.deepEqual(mermaidEdgeEndsFromElementId("workflow-graph-1-L_n0_n1_0"), { from: "n0", to: "n1" });
  assert.deepEqual(mermaidEdgeEndsFromElementId("workflow-graph-3-L_n12_n3_1"), { from: "n12", to: "n3" });
  assert.deepEqual(mermaidEdgeEndsFromElementId("L_n0_n1_0"), { from: "n0", to: "n1" });
  assert.equal(mermaidEdgeEndsFromElementId("workflow-graph-1-flowchart-n0-0"), null);
  assert.equal(mermaidEdgeEndsFromElementId(""), null);
});

test("chooseSlice keeps a chosen slice that is still available", () => {
  assert.equal(chooseSlice(["S1", "S2"], "S2"), "S2");
});

test("chooseSlice resets an absent chosen slice to the first available one", () => {
  assert.equal(chooseSlice(["S1", "S2"], "S9"), "S1");
});

test("chooseSlice returns the first slice when nothing was chosen", () => {
  assert.equal(chooseSlice(["S1", "S2"], null), "S1");
});

test("chooseSlice returns null when no slice is available", () => {
  assert.equal(chooseSlice([], "S1"), null);
  assert.equal(chooseSlice([], null), null);
});

test("graphRetryDelaySeconds backs off 2, 4, 8 then stays at 15", () => {
  const delays = [1, 2, 3, 4, 5, 20].map(graphRetryDelaySeconds);
  assert.deepEqual(delays, [2, 4, 8, 15, 15, 15]);
});

test("unmappedSteps lists steps with no node, in arrival order, with their status", () => {
  const state = replay([
    event({ step_key: "mystery-one", agent_id: "a1" }),
    event({ step_key: "planner", agent_id: "a2" }),
    event({ step_key: "mystery-two", agent_id: "a3" }),
    event({ kind: "step_stop", step_key: "mystery-one", agent_id: "a1", status: "unknown" }),
  ]);
  assert.deepEqual(unmappedSteps(state, rules), [
    { stepKey: "mystery-one", status: "pass" },
    { stepKey: "mystery-two", status: "running" },
  ]);
});

test("unmappedSteps is empty when every step maps to a node", () => {
  assert.deepEqual(unmappedSteps(replay([event({ step_key: "planner", agent_id: "a1" })]), rules), []);
});

test("sessionWorkflows maps each session to its run_start workflow", () => {
  const snapshot = {
    sessions: {
      a: { steps: {}, runs: {}, events: [{ kind: "run_start", workflow: "implement" }] },
      b: { steps: {}, runs: {}, events: [{ kind: "run_start", workflow: "rca" }] },
      c: { steps: {}, runs: {}, events: [] },
    },
  };
  const workflows = sessionWorkflows(snapshot, []);
  assert.deepEqual({ ...workflows }, { a: "implement", b: "rca" });
});

test("sessionWorkflows prefers a later live log run_start", () => {
  const snapshot = {
    sessions: {
      a: { steps: {}, runs: {}, events: [{ kind: "run_start", workflow: "implement" }] },
    },
  };
  const log = [{ session_id: "a", kind: "run_start", workflow: "rca" }];
  const workflows = sessionWorkflows(snapshot, log);
  assert.deepEqual({ ...workflows }, { a: "rca" });
});

test("sessionWorkflows ignores run_start events without a workflow", () => {
  const snapshot = {
    sessions: {
      a: { steps: {}, runs: {}, events: [{ kind: "run_start" }] },
    },
  };
  assert.deepEqual({ ...sessionWorkflows(snapshot, []) }, {});
});

test("workflowNames lists distinct names sorted", () => {
  assert.deepEqual(workflowNames({ a: "rca", b: "implement", c: "rca" }), ["implement", "rca"]);
});

// --- skipped-stage inference -------------------------------------------------

function linearGraph(ids) {
  return {
    name: "chain",
    entry: ids[0],
    nodes: [
      ...ids.slice(0, -1).map((id, index) => ({
        id,
        label: id,
        stage: null,
        step_key: null,
        terminal: false,
        on_pass: ids[index + 1],
        on_fail: null,
      })),
      {
        id: ids.at(-1),
        label: ids.at(-1),
        stage: null,
        step_key: null,
        terminal: true,
        on_pass: null,
        on_fail: null,
      },
    ],
  };
}

function skippedInstance(nodeId, fields = {}) {
  return {
    nodeId,
    slice: "S1",
    round: 1,
    stepKey: "",
    statuses: ["running"],
    summary: "",
    finished: false,
    agentId: "",
    runId: "",
    result: null,
    sequence: 0,
    ...fields,
  };
}

function skippedOf(graph, instances, stopped = false) {
  return inferSkipped(graph, instances, stopped, rules);
}

test("inferSkipped marks a bypassed node once its successor arrives", () => {
  const graph = linearGraph(["a", "b", "c", "d", "e"]);
  const instances = [
    skippedInstance("a", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
    skippedInstance("c", { finished: false, sequence: 2 }),
  ];
  assert.deepEqual([...skippedOf(graph, instances)], ["b"]);
});

test("inferSkipped marks a whole bypassed tail through the transitive closure", () => {
  const graph = linearGraph(["a", "b", "c", "d"]);
  const instances = [
    skippedInstance("a", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
  ];
  assert.deepEqual([...skippedOf(graph, instances, true)], ["b", "c"]);
});

test("inferSkipped never skips a node that has an instance", () => {
  const graph = linearGraph(["a", "b", "c", "d"]);
  const instances = [
    skippedInstance("a", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
    skippedInstance("b", { finished: false, sequence: 2 }),
  ];
  assert.deepEqual([...skippedOf(graph, instances, true)], []);
});

test("inferSkipped excludes terminal nodes", () => {
  const graph = linearGraph(["a", "b", "c", "d"]);
  const instances = [
    skippedInstance("a", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
  ];
  const skipped = skippedOf(graph, instances, true);
  assert.ok(skipped.has("b"));
  assert.ok(skipped.has("c"));
  assert.ok(!skipped.has("d"));
});

test("inferSkipped is round-scoped: a higher-round re-entry is a new instance and leaves the old skip", () => {
  const graph = {
    name: "round",
    entry: "develop",
    nodes: [
      { id: "develop", label: "Develop", stage: "develop", terminal: false, on_pass: "gate", on_fail: null },
      { id: "gate", label: "Gate", stage: "gate", terminal: false, on_pass: "verify", on_fail: "develop" },
      { id: "verify", label: "Verify", stage: "verify", terminal: false, on_pass: "classify", on_fail: "develop" },
      { id: "classify", label: "Classify", stage: "classify", terminal: false, on_pass: "done", on_fail: "develop" },
      { id: "done", label: "Done", stage: null, terminal: true, on_pass: null, on_fail: null },
    ],
  };
  const instances = [
    skippedInstance("develop", { round: 1, finished: true, statuses: ["running", "pass"], sequence: 1 }),
    skippedInstance("gate", { round: 1, finished: true, statuses: ["running", "pass"], sequence: 2 }),
    skippedInstance("classify", { round: 1, finished: true, statuses: ["running", "fail"], sequence: 3 }),
    skippedInstance("develop", { round: 2, finished: false, statuses: ["running"], sequence: 4 }),
  ];
  assert.equal(instances.find((item) => item.nodeId === "develop" && item.round === 1).finished, true);
  assert.equal(instances.find((item) => item.nodeId === "develop" && item.round === 2).finished, false);
  assert.deepEqual([...skippedOf(graph, instances)], ["verify"]);
});

test("inferSkipped on an interrupted run marks only nodes whose successor arrived", () => {
  const graph = linearGraph(["a", "b", "c", "d", "e"]);
  const instances = [
    skippedInstance("a", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
    skippedInstance("c", { finished: false, sequence: 2 }),
  ];
  assert.deepEqual([...skippedOf(graph, instances)], ["b"]);
});

test("inferSkipped waits for the on_pass successor, ignoring an instanced loop-back target", () => {
  const graph = {
    name: "gated",
    entry: "develop",
    nodes: [
      { id: "develop", label: "Develop", stage: "develop", terminal: false, on_pass: "gate", on_fail: null },
      { id: "gate", label: "Gate", stage: "gate", terminal: false, on_pass: "verify", on_fail: "develop" },
      { id: "verify", label: "Verify", stage: "verify", terminal: false, on_pass: "classify", on_fail: "develop" },
      { id: "classify", label: "Classify", stage: "classify", terminal: false, on_pass: "done", on_fail: null },
      { id: "done", label: "Done", stage: null, terminal: true, on_pass: null, on_fail: null },
    ],
  };
  const instances = [
    skippedInstance("develop", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
    skippedInstance("gate", { finished: true, statuses: ["running", "pass"], sequence: 2 }),
  ];
  assert.deepEqual([...skippedOf(graph, instances)], []);
});

test("inferSkipped is deterministic and independent of instance order", () => {
  const graph = linearGraph(["a", "b", "c", "d"]);
  const instances = [
    skippedInstance("a", { finished: true, statuses: ["running", "pass"], sequence: 1 }),
    skippedInstance("c", { finished: false, sequence: 2 }),
  ];
  const first = [...skippedOf(graph, instances)].sort();
  const reversed = [...skippedOf(graph, [...instances].reverse())].sort();
  assert.deepEqual(first, ["b"]);
  assert.deepEqual(reversed, first);
});

test("viewClasses reports the skipped node ids for a slice", () => {
  const state = replay([
    event({ step_key: "planner", stage: "planner", agent_id: "p" }),
    event({ kind: "step_stop", step_key: "planner", status: "pass", agent_id: "p" }),
    develop(1),
    event({ kind: "step_stop", step_key: "S1/develop:r1", status: "pass", agent_id: "d1" }),
    event({ step_key: "S1/code-review:r1", slice: "S1", stage: "code-review", round: 1, agent_id: "c1" }),
  ]);
  assert.deepEqual([...viewClasses(state, graph, rules, "S1").skipped], ["gate"]);
});
