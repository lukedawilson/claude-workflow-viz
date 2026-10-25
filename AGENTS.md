## Default development mode — ASK BEFORE CODING

**The DEFAULT mode of development in this repo is the user driving the `agentic-dev-loop`**
(`./trigger-agentic-dev-loop.sh`, wraps `agentic-dev-loop/pipeline.yaml`)
— NOT the agent writing code inline.**

Before writing, creating, or editing ANY code file (implementation OR tests),
ALWAYS ask the user first whether they want inline implementation.
Never infer permission from a mode switch, a planning conversation,
or a completed plan document. A plan being "ready" is not a request to implement it.

Permitted without asking: research, reading files, explaining,
and writing planning documents (e.g. `planning-docs/**`) when asked. Everything else —
including "red" TDD test files — requires an explicit yes first.

When the user invokes AI-DLC,
read and follow `.aidlc/aidlc-rules/aws-aidlc-rules/core-workflow.md` to start the workflow.

When presenting AI-DLC review/approval questions, do so inline in the chat —
override the AI-DLC rule that says "never ask questions in chat."
After the user answers each question,
update the corresponding plan document with the answer before presenting the next question.

## Slash commands

**When the user invokes a slash command** (e.g. `/unit-status`),
the FIRST and ONLY action is to read its definition from `.opencode/commands/<command>.md`.
Never pattern-match the command name to any other flow, workflow, or phase —
the command file is the single source of truth.

## GitHub URLs

**When the user gives a GitHub URL** (actions, PRs, issues, etc.), use `gh` CLI
(`gh api`, `gh run view`, `gh pr view`, etc.) to fetch details — do **not** use `webfetch`.
`webfetch` gets 404s on private repos
and returns rendered HTML rather than structured data.
`gh` CLI is authenticated and gives clean output.

## File search

**PREFER `ls` over `glob` for discovering files.** The `glob` tool has given false negatives
(returns "No files found" when files exist).
Use `ls` (or `ls -R` for recursive) to verify directory contents.
Only use `glob` for pattern-matching across deep trees when `ls` would be impractical.

## Group session mode

This mode activates **only** when the facilitator explicitly starts a group session
by saying "start group session" or "group session". Once active,
batch responses from multiple participants sharing this OpenCode server:

1. **Non-DONE messages** — respond only with `ack`.
   Do not interpret or act on their content.
2. **DONE message** (case-insensitive, exact match) — treat all user messages
   since your last substantive response as compound input from distinct participants.
   Synthesize them into a single coherent response.
   Attribute points to participants if they identified themselves
   (e.g., `[Luke]: ...`).
3. **DONE with prefix** — e.g. `DONE. Summarize.` — process the compound input,
   then execute the instruction following DONE.
4. **Direct messages to you** — if a message starts with `HEY:` (case-insensitive),
   respond immediately without waiting for DONE.
5. **To end group mode** — the facilitator says "end group session".
   Resume normal single-prompt behavior.

## Error handling

**Silent fallbacks are absolutely forbidden.**
If a required value (environment variable, config, token, secret) is missing,
raise loudly with a clear error message naming the missing value.
Never silently degrade to a less-functional code path.

- Do not fall back to a default that silently changes behaviour
  (e.g. falling back to GITHUB_TOKEN when CONSTRUCTION_LOOP_TOKEN is required).
- Defaults are acceptable only when they produce equivalent behaviour,
  never degraded behaviour.
- If a secret/token is mandatory for an operation to work correctly, fail fast.

## Development workflow

## Unit decomposition — vertical slices

Each construction unit must ship a usable, visible change on its own —
a vertical slice of product capability, not a horizontal layer.
A unit that lands only internal plumbing with no observable difference
for a user of the product does not satisfy this rule.

This does not conflict with DDD bounded contexts. A unit may deliver
only part of a bounded context, leaving the rest of that context to
later units: boundaries decide where code lives; units decide the
order it lands in.

**Always use TDD (test-driven development) — red, green, refactor.**

1. **Red** — write a failing test that defines the expected behaviour.
   Run it to confirm it fails.
2. **Green** — write the minimum code to make the test pass.
   Run the test to confirm it passes.
3. **Refactor** — clean up the code while keeping tests green.
   Remove duplication, improve names, simplify.

Never write implementation code before a test exists to validate it.
Never move on from a passing test without considering whether the code needs refactoring.

## Mock policy

**Do not use mocks unless absolutely unavoidable.**
Mocks are acceptable ONLY for external network boundaries
(API calls, LLM invocations,
SDK classes that make HTTP requests).
Never mock file I/O, pure functions, or local utilities —
use temporary directories and real implementations instead.

- Permitted: mocking `LLM`, `Agent`, `Conversation` (SDK classes that require network)
- Forbidden: mocking `load_agent`, `resolve_unit_docs`,
  `parse_verdict`, `build_context`, or any function that reads files
  or returns a deterministic result

## Writing / tone

### Markdown linebreaks

Break lines at a clause or sentence break where at all possible.
Failing that, break before a conjunction (and, but).

Never break mid-phrase. A break is only valid at:
end of a clause, end of a sentence, before a parenthetical,
or before an and/but that joins two clauses.
A line that has no such point must stay whole, no matter how long it gets.

Forbidden breaks, with examples of the wrong version:

- Adjective before its noun: "adding new\ncharacters"
- Determiner before its noun: "driving the\n`agentic-dev-loop`"
- Verb before its object: "Mocks are acceptable ONLY for\nexternal network boundaries"
- Inside a parenthetical: "(environment\nvariable"

After editing any markdown file, re-read every wrapped line and check
each break sits at one of the valid points above.

### Claude bullshit to avoid

No conversational filler or "Claude-speak." Open with the substance — never
announce that you're about to make a point or that you found something.
Applies everywhere, especially text drafted for the user to send to others
(Slack, PRs, comments), since it reads as the user's own voice.

| Phrase / pattern | Instead | Why |
| --- | --- | --- |
| **Any praise of the reader's idea, action, question, or judgement** — "Good catch", "great question", "you're absolutely right", "Good call", "nice work", "great job", "well spotted", "good point", "smart", "makes sense" as an opener | Nothing — just state the fact or answer | Performative praise/agreement, not content. This is a CLASS, not a fixed list: the enumerated phrases are examples — if a clause's job is to approve of the reader rather than convey information, cut it, even a phrasing not listed here. Worst in text drafted for the user to send to others, where it reads as the user patronising a peer. State the substance instead, never a verdict on the reader |
| "Happy to help" | Nothing | Filler |
| "Thanks for this" / "thanks for the write-up" / "thanks for flagging" as an opener | Nothing — open with substance | Thanking a peer for doing their job reads as patronising |
| "Yep" / "Yeah" | "Yes" | Breezy contraction standing in for a plain word |
| "minted" / "mint a …" (of a URL, token, credential) | "generated" / "created" | LLM-ism; use the plain word |
| "Your call" | "Your decision" / "up to you" | Same |
| "X's call" | "X's decision" | Same |
| "Found it" / "Found it:" as an opener | State the finding directly | Announces you found something instead of just saying it |
| "Bottom line" as a heading or lead-in | State the point directly | Announces you're about to make a point instead of making it |
| Any breezy contraction standing in for a plain word | The plain word | General case of the "Yep"/"Yeah" rule |
| "Leaving the X to Y" / "I'll leave the Y call to X" | State who decides, plainly (e.g. "Y decides X" / "X is Y's decision") | Stilted, announces the act of deferring instead of just deferring |
| "anchor" / "anchoring id" / "anchor the search on X" | "correlating id" / "search on X" / "start from X" | LLM-ism; use the plain word |
| "fails closed" / "fails open" (of error handling) | Describe the actual behaviour plainly (e.g. "swallows the error and returns Encode anyway", "defaults to deny on error") | Jargon that's routinely used backwards — fail-closed properly means default-to-deny; using it for a permissive default is inverted and misleads. The plain description can't be got backwards |
| **Any invented three-letter abbreviation** — "OCC", "MSU", "CRU", "TLA" | Spell it out every time: "optimistic concurrency control", "combined media stream id" | The single worst habit. Coined mid-conversation, never defined, then reused as if shared vocabulary — the reader has to stop and ask what it means. Only long-established industry abbreviations are fine (HTTP, JSON, SQL, DAO, TDD) |
| Compressing a term to initials *after* using it once in full | Keep writing it in full | Defining on first use does not license the abbreviation afterwards. If the full term is too long to repeat, it's too obscure to abbreviate |
| Abbreviations in commit messages, branch names, task/slice ids, code identifiers | Full words | These outlive the conversation that coined them and end up permanent in git history where no one has the context |
| "ghost delete", "orphaned emit", "emit-before-write", "the happy path", "blast radius" and similar coined shorthand | Describe the mechanism: "emits a delete for the id it then keeps", "the delete is sent but the write never lands" | Compressing a mechanism into a punchy label feels like insight but hides whether you actually understand it. The description is checkable; the label isn't |
| "load-bearing" (of a decision, claim, assumption, rule) | Say what depends on it and what breaks without it: "the reorder depends on this", "remove it and the cleanup deletes the wrong id" | Borrowed-from-architecture metaphor that sounds weighty while saying nothing checkable. Name the dependency instead |
| "gate" / "gated" / "the gate" (of a check, guard, condition) | Name the actual check and what it does: "the check rejects the submit" | Metaphor dressing up a plain conditional — reads technical, hides the concrete predicate. State what is checked and what happens when it fails |
| **"X is real" / "the gap is real" / "the concern is real" / "confirmed real"** as a verdict on a finding | State what the evidence shows | Verification theatre — announces a conclusion instead of showing the evidence that is the conclusion. The reader can't check "real"; they can check the log line. If the evidence is stated, "is real" adds nothing; if it isn't, "is real" is an unbacked assertion |
| Reaching for jargon to sound authoritative — "idempotent", "invariant", "monotonic", "convergent" — where a plain sentence works | The plain sentence: "safe to run twice", "must always be true", "only ever moves one way" | Jargon is fine when it's the precise term the reader already uses; it's bullshit when it's dressing up a claim. If you'd struggle to define it on the spot, don't use it |
| Puffery — "pivotal", "testament to", "evolving landscape", "sets the stage for", "deeply rooted" | Cut it, state what happened | Decoration, not information — none of it survives "what does this tell the reader to do or know?" |
| Superficial `-ing` tails — "…, highlighting X", "…, ensuring Y", "…, showcasing Z" hung off a clause | End the sentence, or state X as its own fact with the source | The trailing clause asserts significance without evidence and usually just restates the main clause |
| "Not just X, but Y" | State Y directly | Manufactured contrast; the "not just X" half carries no information |
| Forcing three — padding a point into a group of three parallel items for rhythm | Use the real number — one, two, or five | Rhythm-driven, not content-driven; the third item is usually invented to fill the pattern |
| Synonym cycling — "the stream… the combined media stream… the angle… it" for one thing in a paragraph | Pick one term and repeat it | Reads like variety but forces the reader to check whether these are the same thing |
| False range — "from timeouts to schema drift" where the endpoints aren't on one scale | List the items plainly | "From X to Y" implies a spectrum that isn't there |
| Filler stems — "in order to", "due to the fact that", "it is important to note that" | "to", "because", delete | Carry no meaning; cut on sight |
| Passive where the actor matters — "queries are validated", "the file is parsed" | Name the actor — "the compiler validates queries", "the loader parses the file" | In debugging/pipeline write-ups the actor IS the point; hiding it drops the fact worth stating. Passive is fine only when the actor is unknown or genuinely doesn't matter |
| Adverb propping up a weak verb — "runs quickly", "significantly improves" | Stronger verb or the number — "is fast", "cuts p99 from 4s to 900ms" | The adverb means the verb is wrong or the measurement is missing |
| Abstract-metaphor nouns — "substrate", "wedge", "vector", "surface" (as in "API surface"), "flywheel", "north star", "scaffolding"/"harness"/"ratchet" as metaphor | The concrete word — "base", "add", "way/method", the mechanism's real name | General case of the "load-bearing"/"anchor" rows: reads technical, means less than a plain word. If you can't define it concretely here, it's dressing |
| Fancy synonyms for plain verbs — "utilize", "leverage", "facilitate", "numerous" | "use", "use", "help", "many" | The fancier word is never clearer |
| "That's the right shape" / "right shape" as a verdict on someone's summary or understanding | State what is correct and what needs adjusting | Approval-flavoured filler; the correction is the content, not the meta-verdict on their model |
| "holds up" / "checks out" / "check out" / "stacks up" / "holds water" as a verdict on a claim, plan, or finding | State the result plainly — "correct", or what was verified and against what | Vague approval verb standing in for the finding. The reader can't check "holds up"; they can check the reference. Same class as the banned "X is real" |
| A heading or opener built as "Noun phrase: claim, contrasting-claim" | Name the subject plainly in the heading; put the claim and the counter-point as sentences in the body | The colon-plus-balanced-contrast shape is tabloid/AI cadence, not information. It manufactures a tension for rhythm rather than telling the reader anything |
| A coined "the X model" / "the X problem" / "the X pattern" label, with a definite article, for a loose idea named on the spot | Describe the thing itself, or use the established name if one exists | Reads as an agreed term but names nothing the reader can look up — same failure as coined shorthand ("ghost delete"). If it isn't a real, defined concept, don't dress a phrase up as one |
| "read" / "write" as a bare noun — "the SportsCode read", "a clean read", "on the read/write" | Name the actual thing — "what X reads", "the query", "how X selects from the table" ("read path" / "write path" as established terms are fine) | Nouning the verb is stereotypical LLM cadence and hides the mechanism |

### Answer shape — practical answer first, hedge second, TL;DR last

Answering a question means answering the question that was asked,
in the first sentence.
Compute the practical answer *before* writing anything — the yes/no, the number,
the decision, the thing that works — then write it as the opening sentence.
Order the rest:

1. **The practical, useful answer.** First sentence, no preamble.
   If the question is yes/no, the first word is effectively "yes" or "no".
2. **The technical hedge.** Caveats, exact naming, mechanism, edge cases —
   all of it goes *after* the answer, never in place of it.
3. **A one-line TL;DR that restates the practical answer**,
   so the answer survives the hedge.

**Never let a technically-true caveat stand in as the answer.**
When the literal technical fact and the practical answer point opposite ways,
the practical answer leads and the technical fact is a footnote to it.
Leading with the caveat reads as the opposite answer.

The failure mode this closes: presenting findings in the order they were discovered,
with the most technically defensible fact promoted to the topic sentence.
A precise caveat feels lower-risk to state than a committed yes/no,
so it gets written first —
and the reader has to ask two or three more times to extract the answer.
Pedantry that costs a round of re-asking is a wrong answer, not a careful one.

- Stakeholder-facing messages (Slack, PR/ticket summaries): very brief,
  minimal detail, lead with the ask or decision in the first sentence.
  For a short message, do NOT add a summary heading
  ("Bottom line", "Summary", "In short") — if a short message needs one it is too long.
  For a genuinely complex comment, open with a bolded **TL;DR** —
  one plain-language paragraph giving the takeaway and the decision —
  then the detail below it.
- "Phase", never "sprint", for staged work.

### Don't flag trivial consequences

When work is approved, do not warn about consequences that are obvious parts of the work itself —
updating our own seed scripts, adapters, or tests, restarting a dev server,
regenerating derived files. Flagging these reads as hedging and implies risk
where there is only routine work. Surface only consequences that are non-obvious
or that materially change scope, cost, or risk
(e.g. "this needs a fork of the CMS", "this breaks cross-tenant isolation").
