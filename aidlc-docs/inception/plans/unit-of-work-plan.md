# Unit of Work Plan

Decomposition plan for unit-1 work. Brownfield monolith: single Python package
(`claude_workflow_viz`), no user stories (User Stories SKIPped per execution plan).
"Module" = logical grouping within the package; "Unit of Work" = planning context.

## Part 1 — Planning

- [x] Analyze decomposition-relevant context (requirements.md, application design)
- [x] Domain Exposition (Domain Standards Phase 1) — questions below, answers first
- [x] Derive unit decomposition FROM the exposition answers (DOMAIN-03 trace list)
- [x] Generate context-appropriate decomposition questions
- [x] Collect answers ([Answer]: tags below)
- [x] Analyze answers for ambiguities (vague/contradictory/undefined-criteria)
- [x] Resolve ambiguities with follow-up questions if needed
- [x] Domain Validation (DOMAIN-04..08) on the unit model
- [ ] Get user approval of the decomposition approach
- [ ] Log approval in audit.md
- [ ] Mark Units Generation Part 1 complete in aidlc-state.md

## Part 2 — Generation

- [x] Generate `aidlc-docs/inception/application-design/unit-of-work.md` (unit definitions and responsibilities)
- [x] Generate `aidlc-docs/inception/application-design/unit-of-work-dependency.md` (dependency matrix)
- [x] Generate `aidlc-docs/inception/application-design/unit-of-work-story-map.md` (stories→units mapping)
- [x] Validate unit boundaries and dependencies (cycle check, contract check)
- [x] Ensure all requirements (FR1-FR8, NFR1-NFR6) are assigned to units
- [ ] Present completion message and wait for explicit approval
- [ ] Log approval and mark Units Generation complete in aidlc-state.md

## Mandatory Unit Artifacts

- [ ] `unit-of-work.md` — unit definitions and responsibilities
- [ ] `unit-of-work-dependency.md` — dependency matrix
- [ ] `unit-of-work-story-map.md` — story mappings (requirements→units here; no stories exist)
- [ ] Greenfield code-organization strategy — N/A: brownfield, layout already decided by
      application design D7 + planning-docs/000

## Question Categories — Applicability

- **Story Grouping** — applicable: no stories; units must be defined from the
  application-design component clusters.
- **Dependencies** — applicable: build order between clusters and the standalone 000
  module move must be pinned.
- **Team Alignment** — N/A (justified): single-author project; no team structure evidence
  in requirements or design.
- **Technical Considerations** — N/A for unit boundaries (justified): one wheel deployed
  via pipx; no unit-specific deployment differences. Sequencing of the 000 move is a
  dependency question, covered below.
- **Business Domain** — partially applicable: the three runtime contexts (install /
  invoke / session-end) from D1 are the only bounded-context evidence; folded into UG1.
- **Code Organization (greenfield multi-unit only)** — N/A (justified): brownfield.

## Domain Exposition (Domain Standards Phase 1)

Per the user's directive (2026-10-25T01:50:00Z), the two-phase domain flow runs NOW, at
Units Generation, so the unit decomposition is derived from exposition answers rather
than asserted. Each question cites its source requirement and uses the requirement's
vocabulary. No decomposition model is proposed before these are answered (DOMAIN-02).

### UE1: Change-togetherness of the graph source (cites FR3 "dynamic graph generation at
invoke time", FR4 "strict static-analysis subset", FR5 "agent-generated fallback")

FR3 says the graph is generated at invoke time from the invoked workflow's JavaScript.
FR4 defines the strict static-analysis subset; FR5 defines the agent fallback that
writes a `<workflow>.viz.yaml` when the subset cannot parse. In the design these live
together under the "graph source" concept (D2): parser, parse failures, fallback prompt.

Does the "graph source" concept change as one — a single bounded context whose parts
(the strict parser, its named failures, the fallback prompt) evolve together whenever
the supported subset changes — or do the static-analysis part (FR4) and the
agent-fallback part (FR5) change independently and belong in separate units?

A) One bounded context: subset change touches parser, failures, AND prompt together
B) Two: FR4 (parser + failures) and FR5 (fallback prompt) evolve separately
X) Other (please describe after [Answer]: tag below)

[Answer]: A — one bounded context: parser, named failures, and fallback prompt evolve
together whenever the supported subset changes.
(User, 2026-10-25T01:58:00Z)

### UE2: State ownership of the server lifecycle (cites FR6 "invoke-time bootstrap" +
"SessionEnd stops server", Q6)

FR6 spans two moments: start-or-reuse the server at invoke time, and stop it at session
end. The design places Bootstrap in `invoke/`, the stop call on the Connection value
object, and `POST /shutdown` on the server. The server process is the only state that
spans a whole session.

Does the server lifecycle (start, reuse, stop, connection file) change as one — a single
bounded context for construction purposes — or is invoke-time start separate from
session-end stop?

A) One: the whole lifecycle changes together; splitting start from stop would leave two
partial views of the same state
B) Two: invoke-time bootstrap and session-end shutdown are separable slices
X) Other (please describe after [Answer]: tag below)

[Answer]: A — the server lifecycle is one bounded context; start and stop change
together. (User, 2026-10-25T02:00:00Z)

### UE3: The install context as one bounded context (cites FR1 "Installer", FR2 "entry
point command", D1 "install runtime context", D6 "interactive human actor")

FR1 installs and verifies the tool, writes the hook registrations, and records the
fallback-yaml directory choice. FR2 adds the `/viz` command template. D1 named three
runtime contexts (install, invoke, session-end) and D6 named the human as the only actor
in the install context.

Is the install context one bounded context — installer, command template, and the cli
subcommand that hosts it, changing together whenever the bootstrap story changes — or
does the `/viz` command template (FR2/FR5) belong with the graph source it feeds?

A) One: install is the human-facing bootstrap context; the command template lives there
because it is created at install time
B) The command template belongs with the graph source: it is the agent-fallback entry
point and changes with FR5, not with FR1
X) Other (please describe after [Answer]: tag below)

[Answer]: B — the /viz command template's content is owned by the graph source (it
co-evolves with FR5: failure codes, fallback prompt, agent instructions); the installer
still packages and deploys it unchanged (FR1 owns deployment).
(User, 2026-10-25T02:05:00Z; AI recommendation accepted with "Confirm B")

### UE4: The hook-path invariant as a unit boundary (cites NFR2 "hooks always exit 0",
FR6, and the dispatcher design D10)

NFR2 requires the hook path to never crash a workflow; the design puts the dispatcher,
invoke-time bootstrap, and session-end shutdown behind one silence wrapper. The
"never crash a workflow" invariant is the failure mode that most tightly constrains
construction of these components.

Does that invariant define the unit boundary — everything behind the silence wrapper
(dispatcher, bootstrap, shutdown) is one unit with one acceptance gate (a workflow run
must never observe a failure) — or does the boundary follow the runtime contexts instead
(invoke and session-end as separate slices that each satisfy the invariant on their
own)?

A) One unit bounded by the invariant: dispatcher + invoke-time bootstrap + session-end
shutdown, one acceptance gate
B) Two slices bounded by runtime context: invoke-time and session-end each prove the
invariant separately
X) Other (please describe after [Answer]: tag below)

[Answer]: A — one unit bounded by the NFR2 invariant: dispatcher, invoke-time bootstrap,
and session-end shutdown are one unit with one acceptance gate (a workflow run never
observes a failure). Invoke-time and session-end may be milestones within the unit, not
separate units. (User, 2026-10-25T02:08:00Z; AI recommendation accepted)

## Derived Unit Model (DOMAIN-03 trace)

Three units, each traceable to exposition answers:

| Unit | Components | Exposition trace |
| --- | --- | --- |
| A — graph source | graph_source/parser.py, graph_source/parse_failures.py, graph_source/agent_prompt.py, /viz command template content, graph.to_yaml() | UE1=A (one bounded context), UE3=B (template content), D5 (one contract) |
| B — hook path / server lifecycle | workflow/hook_command.py dispatcher, invoke/bootstrap.py, invoke/shutdown.py (or fold), dashboard/connection_file.py stop_server + LOOPBACK_ADDRESS, dashboard/server.py POST /shutdown | UE2=A (lifecycle is one context), UE4=A (one unit, one acceptance gate), D10 |
| C — install | install/installer.py, cli.py install subcommand, template deployment | UE3=B (deployment stays with install), D6 (human actor), FR1, FR2 |

Cross-unit assignments: FR8 (README smoke fix) — the drift half was resolved by the 000
move (test aligned with the restructured README; suite green as of the module move). The
remaining half — adding README content for the new features while keeping the smoke test
green — is split: Unit B adds the invoke-time/endpoint sections (incl. /shutdown), Unit C
adds the installer section. FR8 is not a unit of its own.

AMENDMENT (2026-10-25T02:46:00Z, during Unit A Functional Design): Unit D added —
skipped-stage visualisation (FR9, static/viz-core.js inference + app.js/styles). Decision
A on the placement question. Construction order becomes A → B → C → D. Unit-of-work.md
and the story map carry the Unit D definition.

Requirements coverage: FR1/FR2/D6 → C; FR3/FR4/FR5/D5 → A; FR6/Q6/NFR2/D10 → B;
FR9 → D; NFR1 (security) and NFR4 (resiliency) span B (server /shutdown, spawn paths)
and C (settings merge); NFR3 (PBT) concentrates in A (to_yaml round-trip, parser
invariants); NFR5/NFR6 span all units. Every requirement is assigned.





### UG1: Unit boundaries

The new components cluster into three runtime contexts (D1): `install/` (install-time),
`graph_source/` (pure parse), `invoke/` + `dashboard/` additions (invoke-time/session-end).
All ship in one wheel, constructed by one dev loop.

A) Three units matching the runtime contexts — graph_source first (pure, no HTTP), then
invoke+dashboard, then installer+cli+README
B) One unit — the whole feature is one cohesive slice; subpackage boundaries already
encode the structure; the per-unit construction loop runs once
X) Other (please describe after [Answer]: tag below)

[Answer]: DERIVED from the Domain Exposition (DOMAIN-03; not asked separately — UE1-UE4
subsumed this question). Three units:
- **Unit A "graph source"**: parser, parse failures, fallback prompt, /viz command
  template content, graph.to_yaml() — traced to UE1=A, UE3=B, D5, FR3/FR4/FR5.
- **Unit B "hook path / server lifecycle"**: dispatcher, invoke-time bootstrap,
  session-end shutdown, Connection.stop_server + LOOPBACK_ADDRESS relocation,
  POST /shutdown — traced to UE2=A, UE4=A, FR6, NFR2, Q6, D10.
- **Unit C "install"**: installer, cli install subcommand, template deployment — traced
  to UE3=B (deployment stays with install), FR1, FR2, D6.
  (User approved this derivation by answering UE1-UE4; derivation recorded
  2026-10-25T02:10:00Z.)

### UG2: Construction sequencing with the standalone module move

planning-docs/000 (move the nine existing modules into DDD folders) is standalone work;
unit-1 assumes the moved layout. When does 000 execute?

A) Now, via the dev loop, before CONSTRUCTION begins — units are designed against the
final layout and never touch the flat layout
B) As the first step of CONSTRUCTION, immediately before unit-1 work
X) Other (please describe after [Answer]: tag below)

[Answer]: MANDATORY — the DDD module move must not be skipped (user, verbatim:
"Make sure you don't skip the DDD step!", 2026-10-25T01:45:00Z). Resolved: the user
executed 000 in parallel via the dev loop; DONE (verbatim: "000 is done in fact",
2026-10-25T01:55:00Z; the module move). Verified: src/claude_workflow_viz now has
workflow/, graph/, dashboard/ subpackages; imports are absolute
(`claude_workflow_viz.workflow.events` etc.); pyproject hatchling packages list updated;
tests updated; dev-loop pipeline committed it. AI-DLC design work proceeds against the
moved layout. LOOPBACK_ADDRESS still lives in dashboard/server.py (000 kept it); the
unit-1 relocation to connection_file.py stands as designed.

### UG3: Unit construction order (only if UG1 = A)

If units are split, in what order should the construction phase run them?

A) graph_source → invoke/dashboard → installer (dependency order, pure-to-boundary)
B) Installer first (user-visible bootstrap earliest, parser can follow)
X) Other (please describe after [Answer]: tag below)

[Answer]: DERIVED (DOMAIN-03). Dependency order A → B → C:
- B depends on A: bootstrap parses the invoked workflow with Unit A's parser and writes
  the transient cache yaml with graph.to_yaml() (Unit A).
- C depends on B: the installer's verify step runs the hook path empty-stdin (Unit B's
  dispatcher), so C constructs after B.
Unit C otherwise imports nothing from A or B (deployment only). Sequence for the
construction phase: Unit A, then Unit B, then Unit C.
(Derived from UE answers; recorded 2026-10-25T02:10:00Z.)
