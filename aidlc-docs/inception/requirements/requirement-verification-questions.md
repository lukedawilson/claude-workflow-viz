# Requirement Verification Questions — claude-workflow-viz unit-1

**Generated**: 2026-10-24T22:15:00Z
**Stage**: Requirements Analysis (Standard Depth)

## Intent Analysis Summary

- **User request**: "unit-1 is how to generate the graph and generally bootstrap this
  installation nicely into a repo with claude dynamic workflows.
  The hooks approach is good, the general architecture is good"
- **Request type**: Enhancement + New Feature (new bootstrap/generation capability for
  the existing tool)
- **Scope estimate**: Multiple Components (CLI, graph-generation logic, hooks
  configuration writer, possibly server auto-start)
- **Complexity estimate**: Moderate

## Working Understanding (confirm in Q8)

Hand-authoring `<workflow>.viz.yaml` is rejected. Unit-1 must generate the graph and
bootstrap the installation into a repo that has Claude Dynamic Workflows, keeping the
hook-based observation architecture and the current security posture unchanged.

---

## Q1: Source of truth for graph generation

Where should the generated graph come from?

A) Runtime observation (record mode) — the visualiser already sees every `agent()` label
   and journal result. With no graph config, it observes a run and persists a generated
   `.viz.yaml` skeleton (observed nodes, observed transitions, loop-backs from round>1).
   Zero changes to workflow code. Weakness: edges only appear after they have been
   exercised; the first run is linear.

B) Declarative manifest in the workflow — workflow authors add a small metadata block
   (e.g. `meta.viz` or a `workflow.viz.json` beside the JS) describing nodes and edges;
   bootstrap converts it to the yaml. Author-maintained but small and explicit.

C) Static JS analysis — bootstrap scans `.claude/workflows/*.js`, finds `agent()` calls,
   label templates, and loop structure, and infers nodes and edges. Zero workflow change,
   but fragile against arbitrary JS (template literals, computed labels, conditionals).

D) Hybrid — C for an initial skeleton, A to refine edges from observed runs.

X) Other (please describe after [Answer]: tag below)

[Answer]: Dynamic — ideally no yaml file at all, but it must be reliable and capture all
the gates and loops. (User, 2026-10-24T22:25:00Z)

---

## Q1b: Source of structure for a dynamic graph (follow-up to Q1)

A fully dynamic graph has no persisted yaml. The visualiser observes nodes from
`agent()` labels, but edges — which node follows which, and where loops return on
failure — are structure that only exists in the workflow's control flow. To be
reliable and capture all gates and loops from the first run, that structure must come
from somewhere:

A) Workflow declares it at runtime — a small `viz` block exported from the workflow JS
   (nodes, edges, loop-backs, terminals), colocated with the logic it mirrors. The
   visualiser reads it from the workflow launch payload or run-dir artifact and renders
   dynamically. No yaml file; complete from run one. Requires workflow authors to add
   the declaration (much smaller than a yaml, lives inside the workflow).

B) Observe and learn — the visualiser accumulates the graph from observed events in its
   state dir; nothing is declared. Zero author effort, but structure appears only after
   paths have been exercised: the first run renders linear, and rare paths (a missed
   classify, a SKIPPED verify-fsm) stay invisible until they actually happen.

C) Static analysis of the workflow JS — infer edges by reading the control flow. Zero
   author effort, complete for simple patterns, fragile against arbitrary JS (computed
   labels, conditionals, helper functions).

D) Hybrid — A for structure, B for refinement (observation adds or confirms edges the
   declaration missed).

X) Other (please describe after [Answer]: tag below)

[Answer]: Try static analysis, but be strict about what it will attempt to parse.
If it can't parse statically, have the Claude Code agent read and generate it.
(User, 2026-10-24T22:40:00Z)

**Static-analysis feasibility check (workflow-examples, assessed by AI)**:
- implement.js — parseable. 9 `agent()` call sites: 3 literal labels
  (pre-flight/head-check, planner, gate-baseline), 6 template literals with a literal
  stage segment (`${slice.id ?? 'slice'}/<stage>:r${round}`). Single `while` loop +
  `for` over slices, `continue` → loop back to develop, `const MAX_ROUNDS = 3` literal,
  returns name the terminals (DONE/BLOCKED/NEEDS_CONTEXT). Hard bits: the conditional
  verify-fsm guard (`if (classify?.touchesConcurrency && ...)`), the gate-null
  `continue`, the `fsm = { verdict: 'SKIPPED' }` default.
- rca.js — parseable with one hard case. Labels `r${round}/<stage>` (dynamic round,
  literal stage); remeasure runs concurrently (`Promise.allSettled`-style `.then()`
  mapping) with `${f.depth}` in its label — a parallel stage group with a dynamic label.
- cross-repo-check.js — trivial (2 agents, straight line).
- Strict subset the parser will attempt: `meta` export; `agent()` call sites whose
  label is a literal or a template literal with literal static segments; `const
  MAX_ROUNDS = <int>`; `while`/`for` + `continue`/`break` → loop-back edges; early
  `return` with a literal outcome/verdict → terminal edges; `if`-guarded `agent()` →
  conditional node; `Promise.all` agent groups → parallel group. Anything else →
  named parse failure (never a guess) → agent fallback.
- Fallback: during bootstrap, a Claude Code agent in the target repo reads the
  workflow and emits the graph structure in a strict, trivially-parseable declaration
  format (generated, never hand-edited). Where that declaration lives is open —
  see Q4.

**Amendment (User, 2026-10-24T22:55:00Z)**: the strict declaration format will be
the current yaml format (`<workflow>.viz.yaml`) unless a real reason to deviate
emerges — i.e. the agent-generated fallback artifact is a yaml in the existing
schema, reusing Graph validation and /graph serving unchanged.

---

## Q2: Bootstrap scope

What must "bootstrap this installation nicely" include?

A) Minimal — install/verify the tool, write the four hooks into
   `.claude/settings.local.json`, generate the graph config, start the server, print the
   dashboard URL.

B) Medium — A plus auto-start: a SessionStart hook starts the server so the dashboard is
   live with every Claude session, and the server stops when the session ends.

C) Full — B plus a verification pass (server starts, hooks fire, an event round-trips
   end to end) and a short usage note written into the target repo.

X) Other (please describe after [Answer]: tag below)

[Answer]: Split into two phases (User, 2026-10-24T22:55:00Z):
- Installer (install-time): install/verify the tool, write the four hooks into
  .claude/settings.local.json.
- Invoke-time (when the workflow itself is invoked, via hooks): generate the graph,
  start the server, print the dashboard URL.

---

## Q2b: Surfacing the dashboard at invoke time (follow-up to Q2)

Async hook stdout is not shown to the user, so "print the dashboard URL" needs a
mechanism. How should the dashboard reach the user when the workflow starts?

A) Auto-open — the hook opens the dashboard in the default browser (`open` on
   macOS, `xdg-open` elsewhere). The dashboard just appears when the workflow starts.

B) URL file — the hook writes the dashboard URL to a well-known file (e.g. the viz
   state dir or `<repo>/.claude/viz/dashboard.url`); the user opens it when they want.

C) Both — auto-open and record the URL.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — auto-open the dashboard in the default browser when the workflow starts.
(User, 2026-10-24T23:00:00Z)

---

## Q3: Target workflows

Should bootstrap be generic from the start, or implement-first?

A) Generic-first — any repo with `.claude/workflows/*.js` works out of the box.

B) Implement-first — build for the /implement workflow specifically; generalise later.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — generic-first: the installer and parser are workflow-agnostic; any repo
with `.claude/workflows/*.js` works out of the box.
(User, 2026-10-24T23:05:00Z)

---

## Q4: Generated config location

Where does the generated graph config live?

A) In-repo — `<target>/.claude/viz/<workflow>.viz.yaml`, committed and versionable next
   to the workflow.

B) Tool state dir — `~/.local/state/claude-workflow-viz/graphs/...`, outside the target
   repo.

C) Both — default in-repo, state dir as fallback when the target repo is read-only.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — in-repo: `<repo>/.claude/viz/<workflow>.viz.yaml`, committed and
versionable next to the workflow.
(User, 2026-10-24T23:10:00Z)

**Amendment (User, 2026-10-24T23:15:00Z)**: the fallback yaml can live in `.claude`
or `.claude-local` — the installer must make this a choice (flag or prompt), not a
fixed path. Design proposal to confirm at design time: `--viz-dir` flag with default
`.claude-local/viz/` (personal, per-machine artifact) and `.claude/viz/` for shared
committed repos.

---

## Q5: Bootstrap entry point

How does the user run bootstrap?

A) CLI subcommand — `claude-workflow-viz bootstrap <repo>` does everything in one command.

B) In-repo Claude command — a `.claude/commands/viz.md` the user invokes inside the
   target repo.

C) Both — CLI for scripting, in-repo command for interactive use.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — Claude Code command in the target repo (e.g. `.claude/commands/viz.md`),
run inside the repo; agent context available for the fallback generation.
(User, 2026-10-24T23:15:00Z)

---

## Q6: Server lifecycle

How should the server start and stop after bootstrap?

A) Manual serve (status quo) — the user runs `serve`; bootstrap only wires hooks and
   prints the command.

B) Auto-start — a SessionStart hook starts the server on a fixed port, and it is shut
   down when the session ends.

C) Both — manual `serve` remains, plus an opt-in auto-start flag.

X) Other (please describe after [Answer]: tag below)

[Answer]: B — stop at session end: a fifth hook (SessionEnd) shuts the server down
when the session ends. (Corrected from A on 2026-10-24T23:22:00Z.)
(User, 2026-10-24T23:20:00Z / corrected 2026-10-24T23:22:00Z)

---

## Q7: Failing README smoke test

The suite currently has one failing test: the README heading structure drifted from what
the smoke test expects. Is fixing it in scope for unit-1?

A) Yes — fix as part of unit-1 (Build and Test must be green at the end anyway).

B) No — leave it for a separate follow-up unit.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — fix in unit-1: the build must be green, and unit-1 will touch the README
anyway (new installer and bootstrap sections).
(User, 2026-10-24T23:24:00Z)

---

## Q8: Success criteria

Proposed acceptance for unit-1: after running bootstrap in workflow-examples and then
running /implement, the dashboard shows the correct live graph — nodes, retries,
loop-backs, verdict colours — with zero hand-authored graph config, and the dashboard is
reachable without manual serve steps.

A) Confirm as stated.

B) Adjust (please describe after [Answer]: tag below)

X) Other (please describe after [Answer]: tag below)

[Answer]: A — confirm: after running bootstrap in workflow-examples and running
/implement, the dashboard shows the correct live graph (nodes, retries, loop-backs,
verdict colours) with zero hand-authored graph config, reachable without manual serve
steps. (User, 2026-10-24T23:26:00Z)

---

## Question: Security Extensions

Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for
   production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental
   projects)

X) Other (please describe after [Answer]: tag below)

[Answer]: A — enforce all SECURITY rules as blocking constraints.
(User, 2026-10-24T23:28:00Z)

---

## Question: Property-Based Testing Extension

Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with
   business logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips
   (suitable for projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or
   thin integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]: B — Partial: enforce PBT rules only for pure functions and serialization
round-trips. (User, 2026-10-24T23:30:00Z)

---

## Question: Resiliency Extensions

Should the resiliency baseline be applied to this project?

**What this extension is.** Enabling it applies a set of **directional, design-time best
practices** for building resilient systems, derived from the **AWS Well-Architected
Framework (Reliability Pillar)** and resilience-review guidance. It steers requirements,
design, and code toward fault tolerance, high availability, observability, and
recoverability — covering 15 practice areas across business goals, change management,
observability, high availability, disaster recovery, and continuous improvement.

**What this extension is NOT.** Enabling it does **not** make your workload
production-ready, nor does it certify or guarantee any availability, RTO, or RPO target.
It is a **starting point** that scaffolds good resiliency decisions early — it is not a
substitute for a formal **AWS Well-Architected Review** of the built system.

Treat the output as a well-grounded **first draft of your resiliency posture** to build
on and validate — not a finished, production-certified result.

A) Yes — apply the resiliency baseline as directional best practices and design-time
   guidance (recommended for business-critical workloads, as an informed starting point
   that you can validate and harden before go-live)

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and experimental
   projects where rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]: A but minimal — apply directionally but keep it lightweight: the tool runs
on the desktop, not a web server. (User, 2026-10-24T23:32:00Z, corrected "Am"→"A"
2026-10-24T23:34:00Z)

---

## Question: Domain Standards Extension

This extension forces a two-phase domain design flow at Application Design and
Functional Design: the domain is exposed from the product requirements (exposition Q&A)
before any model is proposed, and the proposed model is validated against
`coding-standards-ddd.yaml` (descent audit, services as exceptions, no persistence
abstractions). All rules are blocking; findings gate stage completion.

A) Yes — enforce the Domain Standards extension as blocking

B) No — do not enforce this extension

X) Other (describe after the [Answer]: tag below)

[Answer]: A — enforce the Domain Standards extension as blocking.
(User, 2026-10-24T23:36:00Z)

---

## Question: RTO/RPO Goals and Disaster Recovery Strategy (RESILIENCY-02)

What are your Recovery Time Objective (RTO) and Recovery Point Objective (RPO) goals?
These determine the appropriate Disaster Recovery strategy and infrastructure redundancy
level. (For this desktop tool, option E is the likely fit.)

A) RPO/RTO: Hours — Backup & Restore strategy. Lowest cost ($). Data backed up, no
   services deployed. Redeploy from IaC and restore from backups on failure. Suitable
   for non-critical workloads.

B) RPO/RTO: 10s of minutes — Pilot Light strategy. Cost: $$. Data live, services idle.
   Infrastructure deployed but not running, scaled up on failover. Suitable for
   important workloads.

C) RPO/RTO: Minutes — Warm Standby strategy. Cost: $$$. Data live, services run at
   reduced capacity. Scaled up during failover. Suitable for business-critical
   applications.

D) RPO/RTO: Near real-time — Multi-site Active/Active strategy. Highest cost ($$$$).
   Data live, live services in multiple regions simultaneously. Suitable for
   mission-critical, zero-downtime requirements.

E) N/A — Single-region deployment is acceptable, no cross-region DR needed. Rely on
   multi-zone availability within one region.

X) Other (please describe after [Answer]: tag below)

[Answer]: DEFERRED — user said "Continue" (2026-10-24T23:40:00Z), explicitly asking to
proceed without answering the resiliency clarifying questions. Per rule Step 6, user
explicitly asked to proceed. These questions are deferred to NFR Design (the rules
permit asking RESILIENCY-03/04/15 at NFR Design; RESILIENCY-02 is flagged as an open
decision in requirements.md, defaulting to E per the user's "minimal, desktop tool"
framing — to be confirmed at NFR Design).

---

## Question: Change Management Process (RESILIENCY-03)

How should production changes for this workload be governed? AI-DLC will conform the
design to your answer rather than inventing a process.

A) Use our existing organizational change management process — provide the name/tool
   (e.g., ServiceNow, Jira Change, internal CAB). AI-DLC will reference it and ensure
   deployable artifacts fit that process (change records, approval gates).

B) No formal process exists yet — AI-DLC should propose a lightweight change management
   process (change record + approval + rollback note) for the team to adopt.

C) N/A — this workload is exempt from formal change management (e.g., internal tooling).
   Document the exemption rationale.

X) Other (describe after [Answer]: tag below)

[Answer]:
