# Workflow fixtures — provenance

These three files are example workflows authored for this repository
(part of the Apache-2.0 claude-workflow-viz project). They exercise the parser's
supported subset and its named failure paths.

- `implement.js` — a generic multi-phase change workflow fully inside the parser
  subset: `meta`, `MAX_ROUNDS`, literal labels (`pre-flight/head-check`,
  `planner`, `gate-baseline`), template labels (`${slice.id}/<stage>:r${round}`),
  a `while` loop with `continue` loop-backs, a gated `if` agent call, an
  exhaustion return, and early literal returns (`DONE`, `NEEDS_CONTEXT`,
  `BLOCKED`).
- `rca.js` — a root-cause workflow that deliberately uses a round-first label
  (`r${round}/investigate`), which is outside the standard
  `<slice>/<stage>:r<round>` shape; the parser must report `UnsupportedLabel`.
- `cross-repo-check.js` — two literal-label agents in a trivial chain; the
  simplest parse case.

If a future unit extends the subset, extend these examples deliberately and
update the assertions that pin them.
