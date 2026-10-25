# Security Test Instructions

## Purpose

Confirm the Security extension baseline (SECURITY-01..15) on the shipped
surface: the loopback HTTP server (`/ingest`, `/stream`, `/graph`,
`/static`, `/shutdown`), the hook contract, the installer writes, and the
supply chain.

## Vulnerability Scanning

Dependency checks run in the dev-loop restore step (`pip-audit`). Running
them standalone:

```bash
python -m pip install pip-audit && pip-audit
```

Expected: no known vulnerabilities for pyyaml (the only runtime dependency).
The vendored Mermaid build is pinned by a sha256 test
(`tests/test_static_ui.py::test_vendored_mermaid_matches_the_recorded_sha256`),
which is the integrity check for the client library.

## Authentication/Authorization Testing

- Unauthenticated requests to every endpoint must be rejected (401 on
  `/ingest`, `/shutdown`; 401 on `/stream` and `/graph` without a token).
- A wrong token must be rejected, and a failed `/shutdown` must leave the
  server running (deny-on-error, SECURITY-15).
- Non-loopback Host headers must be rejected with 421 before any token
  check.
- Coverage: `tests/test_server.py`, `tests/test_server_shutdown.py`,
  `tests/test_connection_file.py`, `tests/test_serve_shutdown.py`.

## Input Validation Testing

- `/ingest` rejects malformed payloads with 400 and caps bodies at 64 KiB
  (413). The demo fixture contract test
  (`tests/test_demo_fixture.py`) proves every accepted shape passes
  validation; `tests/test_hook_adapter.py` covers adapter-level
  normalisation.
- The parser never guesses: unsupported constructs produce typed failures
  (`tests/test_parser.py`, one fixture per failure class).

## Secret Handling

- The token is never logged, never appears in the state dir's `debug.log`,
  and never rides the spawn command line
  (`tests/test_bootstrap.py::test_detached_spawn_logs_no_token_and_keeps_the_state_dir_private`,
  `tests/test_serve_shutdown.py::test_serve_does_not_print_the_token_to_a_non_terminal_stdout`).
- The connection file is written atomically with private permissions
  (`tests/test_connection_file.py`), verified on POSIX; Windows relies on
  per-user state directories.

## Security Findings

None. All SECURITY-01..15 rules are either covered by the tests above or
marked N/A (cloud-only rules: IAM, alerting, encryption at rest) in the
Unit A/B NFR Requirements artifacts.
