# Unit C (install) — Logical Components

| Component | Location | Type | Responsibility |
| --- | --- | --- | --- |
| Installer | `src/claude_workflow_viz/install/installer.py` | application service | verify, merge settings, deploy /viz command, summary; may raise (D8) |
| InstallSummary | `install/installer.py` | value object | per-action record, rendered per UC6-A |
| HookRegistration | `install/installer.py` | value object | the five registrations; semantic presence match (NFRC4-A) |
| VizCommand render | `install/installer.py` | value-object derivation | VIZ_COMMAND_TEMPLATE + viz-dir substitution (UEC2-A) |
| Atomic write helper | `install/installer.py` (or small shared module) | infrastructure helper | temp file in same dir + `os.replace` (NFRC1-A) |
| CLI install subcommand | `src/claude_workflow_viz/cli.py` | entry point | argparse flag parse; catches and prints (R8) |
| Template content | `src/claude_workflow_viz/graph_source/parse_failures.py` | imported value | `VIZ_COMMAND_TEMPLATE` (Unit A deliverable, UEC3-A) |

Integration points: none external. The installer reads/writes
`.claude/settings.local.json` and `.claude/commands/viz.md` in the target
directory and runs one local subprocess (`claude-workflow-viz hook`, empty
stdin) for verification. No HTTP, no daemon, no state-dir involvement
(NRC3-A).
