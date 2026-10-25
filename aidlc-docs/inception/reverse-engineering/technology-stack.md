# Technology Stack

## Programming Languages
- Python — ≥ 3.12 — the package: CLI, server, state, config validation (12 modules).
- JavaScript (ES modules) — no build step — the UI: pure reducer (viz-core.js) and DOM
  wiring (app.js).
- HTML/CSS — static page and status styling.
- Bash — dev scripts (trigger-agentic-dev-loop.sh, apply-patches.sh).
- YAML — graph config format (`.viz.yaml`) and the dev-loop pipeline.

## Frameworks
- none — the server uses the Python stdlib `http.server`; the UI is framework-free vanilla
  JS.
- Mermaid (vendored in-tree, minified) — client-side flowchart rendering.

## Infrastructure
- none in the product. Local-only: loopback HTTP on 127.0.0.1, state directory under
  `$XDG_STATE_HOME/claude-workflow-viz` or `~/.local/state/claude-workflow-viz`.

## Build Tools
- hatchling — wheel build backend (configured in pyproject.toml).
- uv — dependency locking (`uv.lock`).
- pipx — intended install method (`claude-workflow-viz` console script).

## Testing Tools
- pytest ≥ 8 — Python unit and smoke tests.
- Node `node --test` — the pure JS core suite.
- ruff ≥ 0.6 — linting and formatting gate.
- pip-audit — dependency CVE audit in the dev loop's restore step.
