# Unit C (install) — NFR Requirements Plan

## Steps

- [x] Step 1: Analyze FD artifacts + requirements (FR1/FR2/FR5/FR7/FR8, NFR1-NFR6)
- [x] Step 2: Create this plan with checkboxes
- [x] Step 3: Ask NFR questions one-by-one in chat (NFRC1-NFRC4)
- [x] Step 4: Store plan with [Answer]: tags
- [x] Step 5: Collect answers + write back + ambiguity analysis
- [x] Step 6: Write artifacts nfr-requirements.md + tech-stack-decisions.md
      under aidlc-docs/construction/unit-c-install/nfr-requirements/
- [ ] Step 7: Present completion message + wait approval
- [ ] Step 8: Log approval + update aidlc-state.md

## Category applicability

| Category | Applicable | Notes |
| --- | --- | --- |
| Scalability | No | install-time only, one human |
| Performance | Confirm | no budget; runs once per install |
| Availability | No | desktop tool, N/A per project profile |
| Security | Yes | blocking extension; no new network surface; config-file writes |
| Tech stack | Yes | stdlib only expectation (SECURITY-12) |
| Reliability | Yes | atomic writes, merge edge cases, hard stops |
| Maintainability | Yes | template single-sourced from graph source |
| Usability | Yes | summary, --force, flag |

## Questions

### NFRC1 — atomic writes

The installer writes `.claude/settings.local.json` and `.claude/commands/viz.md`.
An interrupt mid-write leaves a torn file.

A) Both writes atomic: temp file in the same dir + `os.replace`
B) Plain writes for both
C) Atomic for settings.local.json only (the file Claude Code reads every session);
   viz.md plain

[Answer]: A — both writes atomic: temp file in the same dir + `os.replace` (2026-10-25T17:18:00Z)

### NFRC2 — verify subprocess output

The verification step runs `claude-workflow-viz hook` with empty stdin.

A) Capture stdout/stderr; on non-zero exit include them in the loud failure
   message (diagnosable)
B) Discard; report the exit code only

[Answer]: A — capture stdout/stderr; on non-zero exit include them in the loud failure message (2026-10-25T17:22:00Z)

### NFRC3 — fresh settings.local.json permissions

When the file does not exist and the installer creates it:

A) Create it 0600 (matches Claude Code's own treatment of settings files)
B) Leave the default umask

[Answer]: A — create it 0600, matching Claude Code's own treatment of settings files (2026-10-25T17:26:00Z)

### NFRC4 — same hook event, different registration

A hook event may already have a registration with a DIFFERENT command (a
user's own wrapper for PreToolUse Workflow, say). "Present" detection by hook
event name would skip ours and the dashboard would never start.

A) Treat identity as hook event name + `claude-workflow-viz hook` command;
   a same-event registration with a different command does NOT count as
   present — ours is appended alongside (two commands fire; Claude Code runs
   all hooks for an event)
B) Treat identity as hook event name alone; any same-event registration
   counts as present — skip ours, note it in the summary
C) Treat identity as the exact registration bytes; only a byte-identical
   entry counts as present

[Answer]: A — identity = hook event name + `claude-workflow-viz hook` command; a same-event registration with a different command does NOT count as present; ours is appended alongside (2026-10-25T17:32:00Z)
