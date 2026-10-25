# Unit of Work Story Map

No user stories exist (User Stories stage skipped by approved plan). The map is a
requirements→units traceability table: every functional and non-functional requirement
from requirements.md is assigned to at least one unit.

## Requirements → units

| Requirement | Unit A | Unit B | Unit C | Unit D | Note |
| --- | --- | --- | --- | --- | --- |
| FR1 Installer (pipx verify, 5 hooks idempotent, viz-dir choice) | | | ✅ | `install/installer.py` |
| FR2 Entry point (Claude Code command) | | | ✅ | `/viz` command created by C |
| FR3 Dynamic graph at invoke time | ✅ | ✅ | | A parses; B triggers at invoke and feeds /graph |
| FR4 Strict static-analysis subset | ✅ | | | parser + named failures |
| FR5 Agent-generated fallback | ✅ | | | prompt + template content; the agent itself runs via C's command |
| FR6 Invoke-time bootstrap (start/reuse, open dashboard) | | ✅ | | `invoke/bootstrap.py` |
| FR7 Workflow-agnostic (any repo) | constraint | constraint | ✅ | C installs into any repo; A/B never assume a workflow name |
| FR8 README smoke test fix + content | | ✅ (invoke/endpoint sections) | ✅ (installer section) | drift half already fixed by 000 |
| NFR1 Security (blocking) | | ✅ (/shutdown, spawn paths) | ✅ (settings merge) | Security review at each unit's NFR Requirements |
| NFR2 Reliability (never-fails hook) | | ✅ | | the unit-bounding invariant (UE4) |
| NFR3 PBT partial | ✅ | | | to_yaml round-trip, parser invariants |
| NFR4 Resiliency minimal | | ✅ (linear degradation, bounded wait) | | |
| NFR5 Usability (no manual serve steps) | | ✅ (auto-open) | ✅ (one command) | |
| NFR6 Maintainability (documented subset) | ✅ | | | subset docs mirror the parser |

## Journey by unit

- **Unit A** delivers the graph source. Verifiable standalone: parse the fixture corpus,
  named failures per construct class, `to_yaml()` round-trip, PBT green. Nothing user-
  visible yet.
- **Unit B** delivers the hook path. Verifiable standalone: hook payload fixtures drive
  the dispatcher; a test server accepts the run_start forward; the detached-spawn path
  is exercised against the real `serve` process; SessionEnd stops it. User-visible: the
  dashboard opens itself when a workflow starts.
- **Unit C** delivers install. Verifiable standalone: double-install idempotency,
  settings merge preservation, template creation, viz-dir choice. User-visible: the
  single bootstrap command that ties A+B together.
- **Unit D** delivers skipped-stage visualisation. Verifiable standalone: pure skip
  inference under Node tests (gated skip, pending-until-reached, superseded-by-instance).
  User-visible: a skipped stage is coloured distinctly.

The Q8 success criterion spans all four units and is the construction-phase acceptance
gate: after bootstrap in workflow-examples and running /implement, the dashboard shows
the correct live graph with zero hand-authored config and no manual serve steps.
