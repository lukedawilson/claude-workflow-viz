# Component Inventory

## Application Packages
- `src/claude_workflow_viz` — the Python package: hook forwarder, payload normaliser,
  localhost server, run state, graph config validation, and the static UI.

## Infrastructure Packages
- none (no CDK/Terraform/CloudFormation). The repo's only infrastructure-adjacent code is
  the dev-loop sandbox definition in `agentic-dev-loop/pipeline.yaml` (a workflow config,
  not deployable infrastructure).

## Shared Packages
- `src/claude_workflow_viz/static/` — shared client assets: the pure JS reducer
  (viz-core.js), the DOM layer (app.js), the page (index.html), styles, the shared verdict
  rules (status_rules.json) and vendored Mermaid.
- `src/claude_workflow_viz/static/status_rules.json` — the single source of verdict strings
  shared by Python (`node_status.py`) and the browser.

## Test Packages
- `tests/` — pytest suite, one module per source module plus cross-cutting tests
  (smoke, server, serve shutdown, static UI, implement example, javascript).
- `tests/js/viz-core.test.mjs` — Node test suite for the pure JS core (no browser needed).
- `tests/fixtures/` — payload and status-case fixtures.

## Total Count
- **Total Packages**: 3 (application package, shared static assets, test suite)
- **Application**: 1
- **Infrastructure**: 0
- **Shared**: 1
- **Test**: 1

## Supporting Files (not packages)
- `examples/implement.viz.yaml` — example graph config.
- `docs/plan.md` — design plan.
- `agentic-dev-loop/pipeline.yaml` + `sdk_agents/` — the repo's own dev/test/review/qa loop.
- `trigger-agentic-dev-loop.sh`, `apply-patches.sh`, `tools/import-opencode-tools.sh` —
  development scripts.
- `pyproject.toml`, `uv.lock`, `opencode.json`, `README.md` — build and workspace config.
