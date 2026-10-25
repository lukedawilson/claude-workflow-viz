# Build Instructions

## Prerequisites

- **Build Tool**: hatchling (declared in `pyproject.toml`), no build step beyond
  `pip install -e .`
- **Dependencies**: pyyaml>=6.0.3 (runtime); pytest>=8, hypothesis>=6.100,
  ruff>=0.6 (development). The Mermaid client library is vendored
  (`src/claude_workflow_viz/static/mermaid.min.js`), so no Node packages are
  installed at build time.
- **Environment Variables**: `CLAUDE_WORKFLOW_VIZ_STATE_DIR` is the only
  optional override (defaults to `~/.local/state/claude-workflow-viz`). No
  secrets are required for build.
- **System Requirements**: Python >= 3.12, Node >= 20 (tests only), pip 20+.

## Build Steps

### 1. Install Dependencies

```bash
python -m pip install -e . pytest hypothesis
```

### 2. Configure Environment

```bash
# No configuration is required. For tests that write state:
# export CLAUDE_WORKFLOW_VIZ_STATE_DIR=<test state dir>
```

### 3. Build All Units

```bash
# There is no compilation step. The package is built by installing it:
python -m pip install -e .
# A distributable wheel can be produced with:
python -m pip install build && python -m build
```

### 4. Verify Build Success

- **Expected Output**: `pip install -e .` completes with no errors, and the
  console script `claude-workflow-viz` resolves on PATH.
- **Build Artifacts**: the installed console script; the wheel in `dist/`
  when `python -m build` is run.
- **Common Warnings**: none expected. A warning that a newer pip is
  available is not a build failure.

## Troubleshooting

### Install Fails with a Python Version Error

- **Cause**: the package requires Python >= 3.12 (PEP 695 generic syntax in
  `events.py`); an older interpreter reports a syntax error at import time.
- **Solution**: install with a Python 3.12+ interpreter, or point the
  `PYTHON` environment variable at one.

### Console Script Not Found

- **Cause**: pip installed into a location not on PATH, or (Windows) the
  PATH lookup misses the `Scripts` directory of the interpreter.
- **Solution**: add the install location to PATH and re-run
  `shutil.which("claude-workflow-viz")` to confirm.
