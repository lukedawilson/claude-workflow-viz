import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_javascript_module_tests_pass() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/js"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
