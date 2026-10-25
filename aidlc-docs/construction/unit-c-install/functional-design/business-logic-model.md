# Unit C (install) — Business Logic Model

## Flow 1: install (human at a terminal)

1. **Resolve viz-dir** (UC1-B): `--viz-dir <path>` if given, else the default
   `.claude-local/viz/` — no prompt.
2. **Verify** (UC3-B): run `claude-workflow-viz hook` with empty stdin. Require
   exit 0; else hard stop (D8 raise, cli prints, nothing written). Resolve the
   PATH binary (`shutil.which`) and hold its path for the summary.
3. **Ensure directories** (UC5-B): create `.claude/` and `.claude/commands/` if
   missing.
4. **Merge settings** (UC2-C): read `.claude/settings.local.json` if it exists.
   - Invalid JSON → hard stop, loud (UC5-B).
   - All five registrations already present → no write; the file keeps its exact
     bytes.
   - Otherwise write the minimal merged form: every existing key and entry
     untouched, the missing registrations appended to their hook lists.
   - File absent → write the merged form fresh (all five are "missing").
5. **Deploy /viz command** (UC4-A): render `VIZ_COMMAND_TEMPLATE` with the
   viz-dir substituted (UEC2-A). If `.claude/commands/viz.md` exists and no
   `--force` → skip; with `--force` → overwrite.
6. **Print summary** (UC6-A): one line per action (binary path, hooks added or
   "already present", command created / skipped / forced, viz-dir) plus
   "run a workflow to see the dashboard".

## Flow 2: install again (idempotency, UC7-B)

Steps 1-3 re-run (re-verify, re-print allowed), steps 4-5 perform zero writes:
settings bytes unchanged (all five present), /viz command skipped (exists, no
`--force`). Summary reflects that. Net effect: no file's bytes change.

## Failure inventory

| Failure | Behaviour |
| --- | --- |
| hook verify non-zero exit | hard stop, loud, nothing written (UC5-B) |
| `claude-workflow-viz` not on PATH | hard stop, loud (verification can't run) |
| settings.local.json invalid JSON | hard stop, loud, names the file (UC5-B) |
| target dir unwritable | hard stop, loud (OS error surfaces at the first write) |
| missing .claude dirs | created silently (UC5-B), not a failure |
| /viz command exists, no --force | not a failure; skipped and reported (UC4-A) |

The installer never runs on the hook path (UEC4-A), so loud raising cannot harm
a workflow run.
