# Unit C (install) — NFR Requirements

## Security (blocking extension — zero findings)

The installer adds no network surface. Checks applied:

- No secrets anywhere: the five registrations carry the bare command
  (`claude-workflow-viz hook`, no token); the rendered `/viz` command contains
  no token (the /viz agent gets the target path, not credentials).
- Fresh `.claude/settings.local.json` created 0600 (NFRC3-A), matching Claude
  Code's own treatment.
- Atomic writes for both files (NFRC1-A): temp file in the same directory +
  `os.replace` — a torn file cannot result from an interrupt.
- No new runtime dependencies (SECURITY-12); stdlib only.
- No input surfaces beyond argv and files already trusted by the repo owner
  (interactive, human-only — UEC4-A).

## Reliability

- Hard stops are loud and partial-free (UC5-B, D8): invalid settings JSON and
  verification failure.
- Verification captures stdout/stderr and includes them in the failure message
  (NFRC2-A) — a failing hook is diagnosable from the install output.
- Merge presence detection is semantic (NFRC4-A): command-string match, immune
  to formatting drift; a user's own same-event hook never blocks ours.
- Idempotency (UC7-B): a second install re-verifies and re-prints but performs
  zero writes.
- Atomic rename guarantees the reader (Claude Code, the agent) never observes a
  half-written file.

## Performance

No budget. The installer runs once per repo; the only subprocess is the verify
call, bounded by the hook's own 1-second behaviour.

## Availability / Scalability

Not applicable — desktop tool, install-time, single human (project profile
NRA2/NRA3).

## Maintainability

- The /viz template content is imported from the graph source
  (`VIZ_COMMAND_TEMPLATE`); no duplication (UEC3-A, R12).
- The five registrations are a single defined constant list; the README's
  wiring section stays the human-facing copy.

## Usability

- One command: `claude-workflow-viz install [--viz-dir <path>] [--force]`.
- Summary prints one line per action plus the next step (UC6-A).
- Re-running is safe and reprints the same summary (UC7-B).

## PBT targets (PBT-09 Hypothesis)

- Merge fixpoint: applying the merge to any settings JSON twice yields the same
  bytes (PBT-02 round-trip / PBT-03 invariant).
- Template render: substituting the viz-dir twice equals substituting once; the
  rendered command always contains the recorded viz-dir.
- Semantic presence: a registration written with any JSON formatting counts as
  present iff its command is `claude-workflow-viz hook`.
