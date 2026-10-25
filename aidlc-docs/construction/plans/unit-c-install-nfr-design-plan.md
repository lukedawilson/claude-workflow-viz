# Unit C (install) — NFR Design Plan

## Steps

- [x] Step 1: Analyze NFR requirements + FD artifacts
- [x] Step 2: Create this plan with checkboxes
- [x] Step 3: Ask NFR Design questions one-by-one in chat (NRC1-NRC3)
- [x] Step 4: Store plan with [Answer]: tags
- [x] Step 5: Collect answers + write back + ambiguity analysis
- [x] Step 6: Write artifacts nfr-design-patterns.md + logical-components.md
      under aidlc-docs/construction/unit-c-install/nfr-design/
- [ ] Step 7: Present completion message + wait approval
- [ ] Step 8: Log approval + update aidlc-state.md

## Category applicability

| Category | Applicable | Notes |
| --- | --- | --- |
| Resilience | Yes | interruption semantics; six project-wide resiliency decisions NOT re-asked (NRA2=A) |
| Scalability | No | install-time |
| Performance | Confirm | no budget; verify subprocess bounded |
| Security | Yes | carry NFRC decisions; no new surface |
| Logical components | Yes | installer + cli wiring |

## Questions

### NRC1 — interruption semantics

The install sequence is verify → merge settings → deploy /viz command. An
interrupt between steps leaves earlier steps done and later ones not.

A) Resume-by-rerun: the sequence is idempotent, so re-running completes the
   remainder; no journal, no rollback, nothing to undo
B) Add a journal/transaction record so a re-run can report "resuming" vs
   "fresh"

[Answer]: A — resume-by-rerun: idempotent sequence, re-running completes the remainder; no journal, no rollback (2026-10-25T17:50:00Z)

### NRC2 — target directory validation

The installer runs inside a target repo.

A) Accept any directory: `.claude/settings.local.json` belongs to Claude Code,
   not git; the installer doesn't need a repo
B) Require a git repo (refuse otherwise)

[Answer]: A — accept any directory: .claude/settings.local.json belongs to Claude Code, not git; no repo requirement (2026-10-25T17:54:00Z)

### NRC3 — installer logging channel

The installer is interactive (UEC4-A); the hook path's debug log is for hook
runs.

A) Interactive channel only: summary and failures print to stdout/stderr;
   the installer never writes the state-dir debug log
B) Mirror failures to the state-dir debug log as well as printing

[Answer]: A — interactive channel only: summary and failures print to stdout/stderr; the installer never writes the state-dir debug log (2026-10-25T17:58:00Z)
