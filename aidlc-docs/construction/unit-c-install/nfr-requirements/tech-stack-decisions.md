# Unit C (install) — Tech Stack Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| 1 | Stdlib only: `argparse` (install subcommand), `json`, `shutil.which`, `subprocess`, `tempfile` + `os.replace` | No new runtime dependencies (SECURITY-12); install-time tool, no framework |
| 2 | Atomic writes: `tempfile.NamedTemporaryFile(dir=target_dir)` + `os.replace` (NFRC1-A) | Torn-file prevention for the file Claude Code reads every session |
| 3 | Fresh settings file 0600 (NFRC3-A) | Matches Claude Code's own treatment of settings files |
| 4 | Verify via `subprocess.run([binary, "hook"], input="", capture_output=True)` (NFRC2-A) | Exit code + captured output in the loud failure |
| 5 | Semantic merge presence: match on hook event name + `command == "claude-workflow-viz hook"` (NFRC4-A) | Idempotent against formatting drift; never blocks a user's own hook |
| 6 | Merged-form JSON written with `json.dump(indent=2)`; preserved file untouched (UC2-C) | Minimal diff on write; byte-identical when nothing missing |
| 7 | PBT: Hypothesis (PBT-09, project-wide decision) | Merge fixpoint + template-render properties |
| 8 | Template content imported from `claude_workflow_viz.graph_source.parse_failures.VIZ_COMMAND_TEMPLATE` (UEC3-A) | Single source of truth with the graph source |

No decisions change the existing stack (Python ≥3.12, hatchling, pyyaml only
runtime dep) or add anything to the hook path.
