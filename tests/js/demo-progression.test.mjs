import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  initialState,
  applyEvent,
  bannerStatus,
  mermaidIds,
  viewClasses,
} from "../../src/claude_workflow_viz/static/viz-core.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "..", "fixtures");

const progression = JSON.parse(
  readFileSync(join(fixtures, "demo-progression.json"), "utf8"),
);
const graph = JSON.parse(
  readFileSync(join(fixtures, "implement-graph.json"), "utf8"),
);
const rules = { verdicts: {}, fields: ["verdict", "status", "gate"] };

test("the demo progression ends in a finished run", () => {
  let state = initialState(
    { sessions: { demo: { steps: {}, runs: {}, events: [] } } },
    "demo",
    graph,
  );
  for (const event of progression) {
    state = applyEvent(state, event, graph, rules);
  }
  assert.equal(bannerStatus(state), "finished");
});

test("the demo progression marks the gated verify-fsm stage as skipped", () => {
  let state = initialState(
    { sessions: { demo: { steps: {}, runs: {}, events: [] } } },
    "demo",
    graph,
  );
  for (const event of progression) {
    state = applyEvent(state, event, graph, rules);
  }
  const view = viewClasses(state, graph, rules, "s1");
  assert.ok(
    view.skipped.has("verify-fsm"),
    `expected verify-fsm to be skipped, got: ${[...view.skipped].join(", ") || "(none)"}`,
  );
});

test("a terminal node goes green when the run hits it", () => {
  let state = initialState(
    { sessions: { demo: { steps: {}, runs: {}, events: [] } } },
    "demo",
    graph,
  );
  for (const event of progression) {
    state = applyEvent(state, event, graph, rules);
  }
  const view = viewClasses(state, graph, rules, "s1");
  assert.equal(view.nodes[mermaidIds(graph).get("done")], "status-pass");
});
