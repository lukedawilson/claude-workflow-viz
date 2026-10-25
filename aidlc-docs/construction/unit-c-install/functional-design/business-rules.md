# Unit C (install) — Business Rules

Numbered rules, each citing its source requirement or Q&A answer.

- **R1** (FR1, UC2-C, NFRC4-A): the settings merge preserves the existing file byte-for-byte
  when all five registrations are present; when anything is missing it writes the
  minimal merged form, appending only the missing registrations. No formatting
  normalisation, no key reordering. "Present" is a semantic match: the hook event's
  list contains a registration whose command is `claude-workflow-viz hook`,
  regardless of surrounding bytes; a same-event registration with a different
  command does not count as present.
- **R2** (FR1, D10): the five registrations are: PreToolUse (matcher Workflow),
  PostToolUse (matcher Workflow), SubagentStart, SubagentStop — each
  `{"type":"command","command":"claude-workflow-viz hook","async":true}` — plus
  SessionEnd of the same shape.
- **R3** (FR1, UC3-B): install verifies by running the hook with empty stdin and
  requiring exit 0; it also resolves and reports the PATH binary.
- **R4** (FR2, UEC2-A, UC4-A): `.claude/commands/viz.md` is rendered from the
  graph source's `VIZ_COMMAND_TEMPLATE` with the viz-dir substituted; the file
  itself is the only record of the choice.
- **R5** (Q4, UC1-B): viz-dir = `--viz-dir <path>` if given, else
  `.claude-local/viz/`, no prompt.
- **R6** (UC4-A): an existing `/viz` command is never overwritten without
  `--force`; the summary states which happened.
- **R7** (UC5-B): missing `.claude` / `.claude/commands` directories are created
  silently. Hard stops are invalid settings JSON and verification failure — loud,
  nothing partial.
- **R8** (D8-B): the installer may raise at its boundary; `cli.py` catches and
  prints. The installer is never imported by the hook path.
- **R9** (UC6-A): the summary prints one line per action taken plus the
  next-step hint ("run a workflow to see the dashboard").
- **R10** (UC7-B, acceptance): a second install re-verifies and re-prints but
  performs zero writes; every file's bytes are identical afterwards.
- **R11** (FR1 acceptance): pre-existing unrelated hooks in
  `.claude/settings.local.json` are preserved untouched.
- **R12** (UEC1-A, UEC3-A): template deployment lives in the installer; the
  template content is imported as a value from the graph source and never
  duplicated.
- **R13** (FR7): the installer is workflow-agnostic — it wires the hooks, not any
  particular workflow; graph generation happens at invoke time (Unit B).
- **R14** (UEC4-A): the install surface has one runtime context: a human at a
  terminal. No daemon, no hook-path involvement, no CI mode.

## Out of scope

- FR8's README installer section is a code-generation deliverable for this unit,
  not functional design.
- Agent-fallback generation behaviour is the graph source's (Unit A) and the
  agent's; the installer only deploys the command file.
- FR9 skipped-stage visuals (Unit D).
