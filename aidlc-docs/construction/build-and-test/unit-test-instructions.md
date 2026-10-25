# Unit Test Execution

## Run Unit Tests

### 1. Execute All Unit Tests

```bash
python -m pytest tests/ -q -m "not docker"
node --test tests/js/
```

`python -m pytest` is equivalent; the docker marker exclusion is a dev-loop
convention (this project has no docker tests).

### 2. Review Test Results

- **Expected**: Python 597 passed (ubuntu) / 595 passed, 2 skipped (windows);
  Node 103 tests, 0 fail.
- **Test Coverage**: not measured numerically; coverage is structural —
  every module has a matching test module, and the parser subset is locked
  by a fixture corpus (`tests/fixtures/workflows/`) plus a guard test that
  pins parser output to the checked-in graph fixture.
- **Test Report Location**: pytest stdout (add `--junitxml=reports.xml` to
  emit JUnit XML); node:test TAP output on stdout.

### 3. Fix Failing Tests

If tests fail:

1. Review the test output.
2. Identify the failing case and whether it is platform-specific
   (`tests/_platform.py` centralises POSIX-only assertions and console-script
   PATH handling).
3. Fix code or test, rerun until all pass.

## Property-Based Tests (PBT-08)

```bash
python -m pytest tests/test_parser_properties.py tests/test_installer_properties.py \
    tests/test_platform.py -q --hypothesis-seed=42
```

Run twice with the same seed: the pass set must be identical. Run once with
a different seed (e.g. `--hypothesis-seed=7`): it must also pass. Shrunk
failures belong in a permanent example test, not only in the Hypothesis run.

## Lint

```bash
ruff check src tests
```

Must report `All checks passed!`.
