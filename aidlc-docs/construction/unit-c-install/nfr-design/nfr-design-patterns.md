# Unit C (install) — NFR Design Patterns

## Resilience

- **Resume-by-rerun** (NRC1-A): the install sequence is idempotent, so an
  interrupted install recovers by re-running — the remaining steps complete,
  the completed ones no-op (UC7-B). No journal, no rollback, nothing to undo.
  Atomic per-file writes (NFRC1-A) mean no file is ever left torn; the worst
  interruption state is "some steps not yet done", which the re-run finishes.
- Project-wide resiliency decisions apply unchanged (NRA2-A): change
  management = AI-DLC units, rollback = reinstall the wheel, deployment =
  `pipx install --force`, testing = fixture + determinism tests.
- Failure behaviour is loud at the interactive boundary (UC5-B, D8): invalid
  settings JSON and verification failure stop the run, nothing partial.

## Security

- Carried from NFR Requirements: no network surface, no secrets written,
  fresh settings file 0600 (NFRC3-A), atomic writes, stdlib only.
- The installer's subprocess boundary is the verify call only — captured
  output, no shell interpolation (command is a fixed argv list).
- No debug-log writes from the installer (NRC3-A): failures print to
  stdout/stderr only; the state-dir debug log stays a hook-path concern, so
  an install can never leak or corrupt hook diagnostics.

## Performance / Scalability

- No budget; no scaling dimension (NRC2-A: single directory, single human).
- The verify subprocess is the only runtime cost, bounded by the hook's own
  short timeout.

## Logical components

See logical-components.md. No infrastructure elements; no new network or
storage beyond the repo files themselves.
