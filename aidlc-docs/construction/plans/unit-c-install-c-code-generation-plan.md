# Unit C (install) — Code Generation Plan

TDD red-first per step. Filename carries the `-c-` middle segment for the
engine glob. Context docs: unit-c-install/{functional-design,nfr-requirements,
nfr-design}/ + inception/application-design/ + requirements.md.

## Steps

- [ ] Step 1: `install/installer.py` — Installer application service + value
      objects (InstallSummary, HookRegistration, VizCommand render). Verify:
      `shutil.which` + `subprocess.run([binary,"hook"], input="", capture_output=True)`
      require exit 0, capture output for the failure message (NFRC2-A). Merge:
      semantic presence by hook event name + command string (NFRC4-A);
      byte-for-byte preserve when all five present, else minimal merged form
      `json.dump(indent=2)` (UC2-C); atomic write temp+`os.replace` (NFRC1-A);
      fresh file 0600 (NFRC3-A); create `.claude/`+`.claude/commands/` (UC5-B);
      /viz deploy skip-unless---force (UC4-A, template imported from
      graph_source VIZ_COMMAND_TEMPLATE, UEC3-A); summary lines (UC6-A);
      hard stops invalid JSON + verify failure (UC5-B); may raise (D8).
      Tests: tests/test_installer.py red-first.
- [ ] Step 2: `cli.py` — `install` subcommand: argparse `--viz-dir` (default
      `.claude-local/viz/`, UC1-B) + `--force`; catches raises, prints loud
      (R8). Tests for arg parse + failure path.
- [ ] Step 3: `pyproject.toml` — hatchling packages list +=
      `src/claude_workflow_viz/install`.
- [ ] Step 4: Hypothesis properties: merge fixpoint (twice = same bytes),
      template render idempotence + always-contains-viz-dir, semantic presence
      equivalence (any JSON formatting, command-string match) — in
      tests/test_installer_properties.py.
- [ ] Step 5: README — installer section (FR8 content half): install command,
      --viz-dir, --force, idempotency, what happens on the next workflow run.
- [ ] Step 6: N/A — API/Repository/Database/Frontend/Infrastructure layers
      (no new HTTP surface, no persistence, no UI, no IaC).
- [ ] Step 7: `aidlc-docs/construction/unit-c-install/code/summary.md` — created
      and modified files, rule coverage.

Out of scope: Units A/B changes (only importing the existing template value),
Unit D (FR9), agent-fallback behaviour (Unit A), README hook-wiring section
(exists from earlier units).
