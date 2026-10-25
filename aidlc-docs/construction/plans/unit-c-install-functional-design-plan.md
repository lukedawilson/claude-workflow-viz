# Unit C (install) — Functional Design Plan

Unit C = install: one command wires a repo — verify the tool, write the five hooks,
create the /viz command, record the viz-dir choice. Source context: unit-of-work.md
(Unit C section), application-design/{components,component-methods,descent-audit}.md,
requirements.md FR1/FR2/FR5/FR7/FR8, Q4/Q5/D6/D8/D9 answers.

## Steps

- [x] Step 1: Analyze unit context (unit-of-work.md, story map, application design)
- [x] Step 2: Create this plan with checkboxes
- [x] Step 3: Domain Exposition Phase 1 questions (UEC1-UEC4) — one-by-one in chat
- [x] Step 4: Store plan with [Answer]: tags
- [x] Step 5: Collect answers + write back + ambiguity analysis + follow-ups
- [x] Step 6: Design questions (UC1-UC7) — one-by-one in chat
- [x] Step 7: Generate artifacts (domain-entities.md, business-logic-model.md,
      business-rules.md) under aidlc-docs/construction/unit-c-install/functional-design/
- [x] Step 8: Domain Validation Phase 2 (DOMAIN-04..08)
- [ ] Step 9: Present completion message + wait for explicit approval
- [ ] Step 10: Log approval + update aidlc-state.md

## Domain Exposition questions (Phase 1, DOMAIN-01)

### UEC1 — bounded-context placement of the install boundary

The installer is the only component that touches a human and repo configuration
files. The graph source owns the /viz template content (UE3-B). Is the install
surface one bounded context, with the cli entry point inside it?

A) One bounded context: installer + cli install subcommand + template deployment
   co-evolve (FR1/FR2/Q4/D9 change together)
B) Two: the installer (repo wiring) is separate from the cli entry point
   (argument surface)
C) Three: template deployment sits in the graph-source context since the content
   lives there (UE3-B split again)

[Answer]: A — one bounded context: installer + cli install subcommand + template deployment co-evolve (2026-10-25T16:22:00Z)

### UEC2 — state ownership of the viz-dir choice

The viz-dir choice (Q4: `.claude-local/viz/` default, `.claude/viz/` alternative)
must be recorded somewhere so the /viz agent writes to the right place. Who owns
that record?

A) The /viz command file itself — the choice is rendered into
   `.claude/commands/viz.md` at install time; no other record exists
B) A separate record (e.g. a small file or a settings.local.json key) owned by
   the installer; the command template stays dir-agnostic and reads it
C) No record — the /viz agent is told the dir in the command's $ARGUMENTS /
   prompt at run time, installer stores nothing

[Answer]: A — the /viz command file itself: the choice is rendered into `.claude/commands/viz.md` at install time; no other record (2026-10-25T16:26:00Z)

### UEC3 — change-togetherness of installer and template deployment

UE3-B placed the /viz template CONTENT in the graph source (co-evolves with
failure codes and the fallback prompt, FR5). Deployment (writing it to
`.claude/commands/viz.md`) sits in Unit C. Does the deployment step change
together with the installer or with the graph source?

A) With the installer: the installer owns all repo writes (FR1); the template
   content is imported as a value, deployment is installer behaviour
B) With the graph source: a deploy function lives next to VIZ_COMMAND_TEMPLATE;
   the installer calls it
C) Split: content in graph source, a thin render step in the installer that
   substitutes the viz-dir

[Answer]: A — with the installer: the installer owns all repo writes (FR1); the template content is imported as a value, deployment is installer behaviour (2026-10-25T16:30:00Z)

### UEC4 — runtime contexts and actors of the install surface

The installer is interactive, human-only, and never on the hook path (D6). Are
those the only runtime contexts for Unit C?

A) Yes: one context (human at a terminal in the target repo), no hook-path
   involvement, no daemon
B) No: there is a second context (e.g. non-interactive CI install with --yes
   style flags)

[Answer]: A — yes: one context (human at a terminal in the target repo), no hook-path involvement, no daemon (2026-10-25T16:34:00Z)

## Design questions (Phase 2)

### UC1 — viz-dir choice mechanism

Q4 said "flag or prompt". Which mechanism?

A) `--viz-dir <path>` flag; if omitted, prompt the user; no silent default
B) `--viz-dir <path>` flag; if omitted, use the default `.claude-local/viz/`
   with no prompt
C) Prompt always; no flag

[Answer]: B — `--viz-dir <path>` flag; if omitted, use the default `.claude-local/viz/` with no prompt (2026-10-25T16:38:00Z)

### UC2 — settings.local.json merge semantics

The installer idempotently merges the five registrations. Details:

A) Preserve every existing key and entry untouched; append only the missing five
   registrations to their hook lists; rewrite with 2-space indent
B) Normalise the whole file to a canonical key order and 2-space indent even
   where nothing changed
C) Preserve the file byte-for-byte if all five registrations are already
   present; otherwise write the minimal merged form

[Answer]: C — preserve the file byte-for-byte if all five registrations are already present; otherwise write the minimal merged form (2026-10-25T16:42:00Z)

### UC3 — verification scope

What does the install-time verify step check?

A) Run `claude-workflow-viz hook` with empty stdin and require exit 0 (the D8
   contract), nothing else
B) Additionally resolve which binary PATH provides and print its path
C) Additionally run a parse+serve smoke test against a bundled sample workflow

[Answer]: B — run `claude-workflow-viz hook` with empty stdin and require exit 0, AND resolve which binary PATH provides and print its path (2026-10-25T16:46:00Z)

### UC4 — pre-existing /viz command handling

The /viz command may already exist (previous install, different viz-dir, or a
hand-edited one).

A) Skip writing if it exists; `--force` overwrites; the summary says which
B) Always overwrite, but show a diff-ish warning first
C) Never overwrite; if it exists, fail loudly telling the user to move it

[Answer]: A — skip writing if it exists; `--force` overwrites; the summary says which (2026-10-25T16:50:00Z)

### UC5 — install failure behaviour

The installer may raise (D8). Which failures are hard stops?

A) Invalid settings.local.json, unwritable target dir, missing .claude dir
   (not created silently), verification failure — all loud, nothing partial
B) Create missing directories (.claude, .claude/commands) silently; only
   invalid JSON and verification failure are hard stops
C) Best-effort: complete the steps that can succeed, report the rest

[Answer]: B — create missing directories (.claude, .claude/commands) silently; only invalid JSON and verification failure are hard stops (2026-10-25T16:54:00Z)

### UC6 — install summary output

What does the summary print?

A) One line per action taken (verified / hooks added / command created /
   viz-dir recorded) plus what happens next ("run a workflow to see the
   dashboard")
B) A compact single line ("installed: 5 hooks, /viz command, viz-dir X")
C) Quiet by default; verbose with --verbose

[Answer]: A — one line per action taken (verified / hooks added / command created / viz-dir recorded) plus what happens next ("run a workflow to see the dashboard") (2026-10-25T16:58:00Z)

### UC7 — idempotency definition

What does "installing twice changes nothing" mean exactly?

A) Second run performs zero writes; every file's bytes are identical after the
   second run
B) Second run may re-verify and re-print but performs no writes
C) Second run rewrites identical content (same bytes) even if it writes

[Answer]: B — second run may re-verify and re-print but performs no writes (2026-10-25T17:02:00Z)

## Domain Validation (Phase 2) — passed

DOMAIN-04: rules R1-R14 cite FR1/FR2/Q4/Q5/D8/D10/UC answers; components trace
to requirements. DOMAIN-05: no blocking shapes — no delegating entities, no
service-named value objects, no coined labels, no behaviourless aggregates.
DOMAIN-06 descent audit: Installer = application service step 5 (steps 0-4
ruled out: not pure helper — repo writes + subprocess verify; not value object —
orchestrates; not entity method — no entity owns repo wiring; not new entity —
adds no behaviour; not domain service — boundary orchestration, no domain
concept). InstallSummary/HookRegistration/VizCommand/VizDirChoice = value
objects step 1; cli = entry point. DOMAIN-07: no banned names, no 1:1
controller→aggregate services. DOMAIN-08: no persistence abstractions; install
state is the files written.

## PBT-01 property candidates

- Merge function: applying the merge twice yields the same file bytes (fixpoint).
- Template rendering: substituting a viz-dir into the template twice is equal to
  substituting once.
- /viz command written content always contains the recorded viz-dir.
