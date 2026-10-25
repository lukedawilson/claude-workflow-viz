# Unit C (install) — Domain Entities

Domain model for the install bounded context (UEC1-A: installer + cli install
subcommand + template deployment co-evolve; one runtime context UEC4-A: human at
a terminal, never on the hook path).

## Entities and value objects

### Installer

Application service at the interactive boundary (descent step 5, may raise per
D8-B). Owns every repo write (UEC3-A): settings merge, command deployment,
summary printing. Imports the template content as a value (UEC3-A).

```
Installer.run(target_repo: Path, viz_dir: Path | None, force: bool) -> InstallSummary
```

Behaviours (from the Q&A):

- verify (UC3-B): run the hook with empty stdin, require exit 0; resolve which
  PATH binary provides `claude-workflow-viz` and print that path.
- merge the five registrations into `.claude/settings.local.json` (UC2-C):
  byte-for-byte preserved if all five present; otherwise write the minimal
  merged form (append only the missing registrations; no formatting churn).
- deploy `.claude/commands/viz.md` (UC4-A): skip if it exists unless `--force`.
- create missing `.claude` / `.claude/commands` dirs silently (UC5-B).
- hard stops, loud, nothing partial (UC5-B): invalid settings JSON, verification
  failure.
- summary (UC6-A): one line per action taken plus what happens next.

### InstallSummary

Value object: the record of what happened. Fields: binary_path, hooks_added
(names), hooks_present (count), command_written | command_skipped | command_forced,
viz_dir. Rendered as the UC6-A output.

### HookRegistration

Value object: one registration. The five are byte-identical in shape
(`{"type":"command","command":"claude-workflow-viz hook","async":true}` for the
four README-contract hooks; SessionEnd the fifth). Identity for merge purposes =
hook event name (PreToolUse/PostToolUse matcher Workflow, SubagentStart,
SubagentStop, SessionEnd).

### VizCommand

Value object: the rendered `/viz` command content. Produced by substituting the
viz-dir into the `VIZ_COMMAND_TEMPLATE` value imported from the graph source
(UEC2-A: the choice is rendered into the command file itself; no other record).

### VizDirChoice

Value object: the resolved viz-dir. `--viz-dir <path>` wins; omitted → default
`.claude-local/viz/` with no prompt (UC1-B).

### CLI entry point

`cli.py` gains the `install` subcommand (D9). Same bounded context (UEC1-A):
parses the flag, catches installer raises, prints the failure loudly (D8).

## Relationships

```
InstallSummary  *--  HookRegistration
Installer ..> InstallSummary        (produces)
Installer ..> HookRegistration      (merges into settings.local.json)
Installer ..> VizCommand            (renders and writes)
Installer ..> VizDirChoice          (resolves via flag-or-default)
Installer ..> VIZ_COMMAND_TEMPLATE  (imported value from graph_source)
```

No persistence beyond the repo files themselves; the state of the install is the
files it wrote (UEC2-A).
