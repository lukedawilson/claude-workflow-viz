# Unit A — NFR Design Patterns

How each NFR requirement is incorporated into the design, with the chosen pattern per
category.

## Resilience patterns

- **Typed failures instead of exceptions (fail-closed)**: every construct outside the
  R1-R17 subset is a `ParseFailure` value; the parse result is a `Graph` or a
  `ParseFailureReport`, never an exception (SECURITY-15, R2/R3).
- **Debug-log swallow (NRA1 = B)**: an internal bug — an unexpected exception inside
  `parse()` — is caught at the unit boundary, swallowed for the hook, and its stack
  trace appended to a state-dir debug log. The hook contract stays pure; a broken
  graph has a diagnosable cause. Log writes themselves are best-effort and
  exception-guarded (the log must never be the thing that crashes the hook).
- **Degradation path**: the failures-win rule means a parse error degrades to the
  fallback prompt / linear mode downstream — never to a crash or a wrong graph
  (NFR4).

## Scalability patterns

- None. Single machine, single user; the parse is in-process and per-invocation
  (NRA3 = A). Bounded memory by construction: input is a human-authored file, output
  is a `Graph` whose size the existing validator already bounds.

## Performance patterns

- **Linear-time scan discipline**: regex patterns contain no nested quantifiers;
  pathological inputs cannot trigger catastrophic backtracking (NFR-A1/NFR-A2
  mitigation).
- **Single-pass collection**: failures and nodes are collected in one scan; no
  reparsing per construct class.
- **Budget**: parse completes in milliseconds, far inside the hook's 1-second HTTP
  timeout; the pathological-fixture test asserts bounded time on adversarial input.

## Security patterns

- **Threat model**: local human-authored workflow files in the invoked repo. No
  network surface, no secrets, no new dependencies (NFR-A1). Failure context lines
  flow only into the /viz agent prompt.
- **Least privilege**: the parser only reads the file it was pointed at; nothing else
  on the machine is touched.

## Logical components

- None (NRA3 = A). No queues, caches, circuit breakers, or workers: the parser is a
  pure in-process function behind the dispatcher. The one infrastructure-ish
  element, the state-dir debug log, is a plain append-only file, rotated by size
  during construction if it grows (stated: cap at ~1 MiB, truncate-oldest).

## Resiliency-baseline user decisions (NRA2 = A, all confirmed)

- RESILIENCY-02 RTO/RPO: N/A — reinstall wheel / regenerate graph; git history is the
  backup.
- RESILIENCY-03 change management: AI-DLC units — subset changes are planned units.
- RESILIENCY-04 CI/CD/rollback/deployment: dev loop runs tests; rollback = reinstall
  previous wheel; deployment = `pipx install --force`.
- RESILIENCY-08 regional topology: N/A — single machine.
- RESILIENCY-14 resiliency testing: pathological-fixture + determinism tests are the
  resiliency tests.
- RESILIENCY-15 incident response: N/A — single user; failures surface as parse
  failures or linear-mode fallback.
