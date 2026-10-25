# Application Design Plan

**Stage**: Application Design (INCEPTION phase)
**Date**: 2026-10-25
**Execution Plan Reference**: `aidlc-docs/inception/plans/execution-plan.md`
**Extensions Active**: Domain Standards (blocking, two-phase), Security (blocking),
Property-Based Testing (partial), Resiliency (minimal)

**Domain Standards note**: The Service Layer Design question category and the
`services.md` artifact are superseded by the descent audit (DOMAIN-06). Phase 1
(Domain Exposition) must complete before any model is proposed (DOMAIN-02).
`coding-standards-ddd.yaml` has been read before this plan (required).

---

## Plan Checkboxes

- [x] Analyze context (requirements.md read; user stories skipped by plan)
- [x] Create application design plan with questions
- [x] Domain Exposition: ask D1–D6 inline, record answers below (Phase 1)
- [x] Design questions: D7-D10 all answered (D7 X same-wheel DDD folders + standalone move, D8 B, D9 A install, D10 A dispatcher)
- [ ] Analyze answers for ambiguity; follow-ups if needed
- [ ] Generate components.md
- [ ] Generate component-methods.md
- [ ] Generate descent-audit.md (supersedes services.md)
- [ ] Generate component-dependency.md
- [ ] Generate application-design.md (consolidated)
- [ ] Domain Validation (DOMAIN-04..08, Phase 2) against coding-standards-ddd.yaml
- [ ] Validate design completeness and consistency
- [ ] Present completion message; await approval

---

## Phase 1 — Domain Exposition Questions

Each question cites its source requirement and uses the requirement's own vocabulary.

### D1 — Runtime contexts
FR1 (installer), FR3/FR6 (invoke time) and FR6 (SessionEnd stop) split the system's
behaviour across three distinct moments: install time, workflow-invoke time, and
session end. Are these the only runtime contexts the design must handle, or are there
others — e.g. a "first ever run" moment, or a "re-install after the workflow files
changed" moment?

[Answer]: A — install time, workflow-invoke time, and session end are the only runtime
contexts. (User, 2026-10-25T00:06:00Z)

### D2 — Concepts named
FR4 defines the "strict static-analysis subset" and FR5 defines the "agent-generated
fallback" that writes a `<workflow>.viz.yaml`. Is the parse result and the fallback
yaml one concept — a graph source that can be produced by either path — or two distinct
concepts that the design keeps separate?

[Answer]: A — one concept: both paths produce the same graph source; the parser and the
agent fallback are interchangeable producers. (User, 2026-10-25T00:08:00Z)

### D3 — State ownership
FR6 starts the server at invoke time and Q6 (answer B) stops it at session end. Who owns
the start/stop decision — the installer, the PreToolUse hook, or the server itself —
and what must happen when a second workflow invocation arrives while a server is already
running (a new session, a second repo)?

[Answer]: A — the PreToolUse hook owns both decisions: start if no server is running
(reuse the connection file otherwise), SessionEnd stops it — one server per machine,
shared across sessions and repos. User adds: "the viz is stateless, it's driven by the
hooks". (User, 2026-10-25T00:10:00Z)

### D4 — Invariants and failure modes
FR4 says anything outside the parse subset is a "named parse failure" (never a guess),
and NFR2 requires hooks always exit 0 and invoke time never crashes the workflow. How
granular must the named parse failures be for unit-1 — one generic "unparseable" result,
or a distinct failure name per unsupported construct (so the agent fallback and the
dashboard warning can say what went wrong)?

[Answer]: B — distinct failure names per unsupported construct class, so the fallback
agent and dashboard warning can say what went wrong. User adds: "we should give the
agentic yaml generator some information to work with". (User, 2026-10-25T00:12:00Z)

### D5 — Change-togetherness
FR3 requires the generated graph to be served by the existing `/graph` endpoint, and
FR5 requires the fallback yaml to validate against the existing Graph schema. Does the
static parser therefore emit the same internal Graph structure that `Graph.load`
produces from yaml — one contract the parser and the yaml loader both satisfy?

[Answer]: A — yes, the parser emits the same Graph structure; parser output and
yaml-loaded graphs are one contract. (User, 2026-10-25T00:14:00Z)

### D6 — Actors
FR2 makes the entry point a Claude Code command run inside the target repo, and FR5's
fallback needs an agent with Claude Code context. Are the installer and the entry-point
command always used by a human in an interactive shell, or must the installer also work
headless (CI, dotfiles bootstrap, scripts)?

[Answer]: A — interactive human only; the installer can assume a terminal and a user.
(User, 2026-10-25T00:16:00Z)

---

## Design Questions

### D7 — Component identification
The execution plan places the new components in the existing `claude_workflow_viz`
package. How should they be grouped — flat modules next to the existing ones, or a new
subpackage (or subpackages) for the installer/parser/bootstrap surface?

[Answer]: X — all in the same wheel (one package, no second distribution), but the new
components organised into DDD-style subfolders. Structure proposed in chat, confirmed by
user (2026-10-25T00:30:00Z). User verbatim: "They should all be in the same wheel, but
can be organised into ddd-style subfolders. Propose a structure". AMENDMENT (same
message, second part): "We should move these first" — the existing nine flat modules are
to be moved into DDD folders (workflow/, graph/, dashboard/); documented in
planning-docs/000-move-existing-modules-into-ddd-folders.md. FURTHER CLARIFICATION
(2026-10-25T00:34:00Z): "This is separate from ai-dlc units. unit-1 can assume it's
already been done." — the move is standalone work outside the AI-DLC unit structure;
unit-1 design assumes the moved layout exists.

### D8 — Component methods and patterns
NFR2's "hooks always exit 0" and the existing codebase conventions (typed error unions
that never raise, frozen dataclasses, fail-silent hook) point one way: the new parser and
bootstrap return results-or-typed-errors rather than raising. Confirm this is the
convention for the new components, or name where raising is acceptable.

[Answer]: B — uniform for the hook path and domain logic (typed results, never raise);
the interactive installer boundary may fail fast (raise, caught and printed by cli).
Rationale: cli already converts GraphError to stderr+exit 1; DDD standards allow
fail-fast at misuse boundaries; installer failures have a human consumer, not a code
consumer.
(User, 2026-10-25T01:22:00Z)

### D9 — Component methods
FR1 names the installer but not its command. What should the new CLI subcommand be
called — `install`, `bootstrap`, or something else?

[Answer]: A — `claude-workflow-viz install` as the third subcommand.
(User, 2026-10-25T01:24:00Z)

### D10 — Component dependencies
The README wiring contract registers four hooks (PreToolUse/PostToolUse matcher
Workflow, SubagentStart, SubagentStop) each as async `claude-workflow-viz hook`. Must
those four registrations stay byte-identical (new behaviour keyed only off
`hook_event_name`), with the SessionEnd stop as a fifth registration?

[Answer]: A (architecture grounds, not migration): the hook command is the event
dispatcher; all behaviour keyed off hook_event_name inside it; the four registrations
stay byte-identical and SessionEnd is a fifth identical registration. Separate commands
would double processes per PreToolUse event (forward + bootstrap) and fork the silence
contract. Lifecycle operations live in invoke/ internals called from the dispatcher.
(User, 2026-10-25T01:28:00Z)

---

## Mandatory Artifacts (per application-design rule)

- [x] `aidlc-docs/inception/application-design/components.md`
- [x] `aidlc-docs/inception/application-design/component-methods.md`
- [x] `aidlc-docs/inception/application-design/descent-audit.md` (supersedes services.md)
- [x] `aidlc-docs/inception/application-design/component-dependency.md`
- [ ] `aidlc-docs/inception/application-design/application-design.md` (consolidated)

## Domain Validation Checklist (Phase 2, DOMAIN-04..08)

- [ ] DOMAIN-04: traceability list mapping each proposed concept to its exposition answer
- [ ] DOMAIN-05: model checked against blocking shapes (delegating entities,
  service-named value objects, coined labels, per-endpoint domain services,
  behaviourless aggregates)
- [ ] DOMAIN-06: descent audit — every service names the descent step that justifies it
  (0 value object, 1 existing entity method, 2 new entity, 3 domain service,
  4 application service)
- [ ] DOMAIN-07: no 1:1 controller→aggregate delegates; no Manager/Helper/Orchestrator/
  Facade names
- [ ] DOMAIN-08: no Repository/DAO/store/unit-of-work; persistence is a method on the
  owning entity
