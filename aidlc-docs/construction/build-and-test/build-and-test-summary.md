# Build and Test Summary

## Build Status

- **Build Tool**: hatchling via `pip install -e .` (no compile step)
- **Build Status**: Success (install verified in CI on both platforms)
- **Build Artifacts**: console script `claude-workflow-viz`; wheel on demand
- **Build Time**: < 1 minute in CI

## Test Execution Summary

### Unit Tests

- **Total Tests**: Python 597 (ubuntu) / 597 incl. 2 skipped (windows);
  Node 103
- **Passed**: 597 (ubuntu) / 595 (windows); Node 103
- **Failed**: 0 on both platforms and both suites
- **Coverage**: structural (module-per-test + parser fixture corpus +
  checked-in graph fixture guard); no numeric metric
- **Status**: Pass

### Integration Tests

- **Test Scenarios**: 3 (graph source → hook path; installer → dispatcher;
  live stream → client skip inference) via `./run-demo.sh` + fixture
  contract/replay tests
- **Passed**: all (demo exits 0, `/shutdown` 204, 23/23 events ingest)
- **Failed**: 0
- **Status**: Pass

### Performance Tests

- **Response Time**: bounded by the pathological-fixture parser test
  (within the 1-second hook timeout); no numeric target
- **Throughput**: N/A (single-user desktop tool)
- **Error Rate**: N/A
- **Status**: N/A (desktop profile; instructions document the rationale)

### Additional Tests

- **Contract Tests**: the `/ingest` fixture contract test
  (`tests/test_demo_fixture.py`) — Pass
- **Security Tests**: authn/z, input validation, secret handling, vendored
  hash, pip-audit (dev-loop restore step) — Pass, zero findings
- **E2E Tests**: `run-demo.sh` scenario plus CI matrix — Pass

## Property-Based Tests (PBT-08)

`--hypothesis-seed=42` twice: identical, 23 passed. `--hypothesis-seed=7`:
23 passed. Shrink/seed reproducibility satisfied.

## Platform Coverage

- **ubuntu-latest**: Python 597 passed; Node 103 tests, 0 fail (CI run
  40217946252)
- **windows-latest**: Python 595 passed, 2 skipped; Node 103 tests, 0 fail
  (same run) — the NFRB4 requirement for a passing Windows CI job
- **Local (macOS)**: Python 597 passed; Node 100 tests, 0 fail; ruff clean

The Windows leg was made green by making POSIX-only test assertions
platform-aware (`tests/_platform.py`), routing signal-based stops through
the product's `/shutdown` endpoint on win32, and pinning the vendored
Mermaid file's line endings via `.gitattributes`. Product code was not
changed.

## Overall Status

- **Build**: Success
- **All Tests**: Pass
- **Ready for Operations**: Yes

## Next Steps

All four units (A graph source, B hook path/server lifecycle, C install,
D skipped-stage visualisation) are code-complete, reviewed, and approved,
and the full suite passes on both CI platforms. Proceed to the Operations
phase.
