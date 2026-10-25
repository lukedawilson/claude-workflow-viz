# Implementation summary — Unit C (install)

## Files created

- `src/claude_workflow_viz/install/__init__.py` — install package.
- `src/claude_workflow_viz/install/installer.py` — `Installer` application service plus the
  value objects `HookRegistration`, `InstallSummary`, and the `CommandOutcome` enum. Verify
  (`shutil.which` + `subprocess.run([binary, "hook"], input="", capture_output=True)`, exit 0
  required, NFRC2-A); semantic presence + minimal merge (NFRC4-A/UC2-C); atomic write
  temp+`os.replace` (NFRC1-A); fresh settings 0600 (NFRC3-A); `/viz` deploy skip-unless-force
  (UC4-A); summary lines (UC6-A); hard stops on invalid JSON and verify failure (UC5-B); raises
  at the boundary (D8).
- `tests/test_installer.py` — real-`hook` verify, idempotency, merge preservation,
  invalid-JSON and unreadable-settings loud stops, missing/failing binary, `/viz` skip/force,
  viz-dir choice.
- `tests/test_installer_properties.py` — Hypothesis merge fixpoint, template-render
  idempotence + always-contains-viz-dir, semantic presence (PBT targets).

## Files modified

- `src/claude_workflow_viz/graph_source/parse_failures.py` — added `VIZ_DIR_PLACEHOLDER`
  (`{viz_dir}`) and put it into `VIZ_COMMAND_TEMPLATE`'s first sentence, so the template value
  carries the substitution point R4/UEC2-A require; exported both from `__all__`.
- `src/claude_workflow_viz/cli.py` — `install` subcommand with `--viz-dir`
  (default `.claude-local/viz`, UC1-B) and `--force`; catches `InstallError`/`OSError` and
  prints loudly (R8).
- `pyproject.toml` — hatchling packages list gains `src/claude_workflow_viz.install`.
- `README.md` — installer section, install row in the subcommands table, and a pointer in the
  hook-wiring step (FR8 content half).
- `tests/test_cli.py` — install CLI success, missing-binary failure, and flag tests; help now
  lists `install`.

## Rules honoured

R1 (byte-preserve when all present, minimal merged form otherwise), R2 (five registrations
incl. SessionEnd), R3 (verify via empty-stdin hook run + report PATH binary), R4 (viz-dir
substituted into the imported template), R5 (flag-or-default, no prompt), R6 (skip without
`--force`), R7 (silent dir creation, loud hard stops), R8 (raise at boundary, cli prints), R9
(one line per action + next-step hint), R10 (second install zero writes), R11 (unrelated hooks
preserved), R12 (template imported as a value, never duplicated), R13 (workflow-agnostic),
R14 (single terminal runtime context).

## Design note

`viz_dir` is only ever substituted into the command file and printed, so the installer treats
it as a `Path` that is rendered via `str`; `VizDirChoice` is realised as the single
`DEFAULT_VIZ_DIR = Path(".claude-local", "viz")` fallback rather than a separate class.

## Tests run locally

- `.venv-sandbox/bin/python -m pytest tests/ -q -m "not docker"` → 595 passed.
- `ruff check` and `ruff format --check` → clean.
- The JS suite is unchanged in this unit; no `static/viz-core.js` edit.
