"""Platform-aware test helpers for POSIX-only semantics.

Windows does not enforce POSIX file modes (`chmod` only toggles the read-only
attribute) and console scripts land in a `Scripts` subdirectory of the python
directory for non-venv installs. These helpers keep that platform noise out of
the test bodies.
"""

import os
import stat
import sys
from pathlib import Path

POSIX = os.name != "nt"


def assert_private_mode(path: Path, mode: int) -> None:
    """Assert a private file/directory mode; on Windows assert existence only.

    The privacy invariant (`0600` files, `0700` state directory) is a POSIX
    concept: on Windows `chmod` is effectively a no-op and the operating
    system's ACLs govern access, so the mode value is not meaningful there.
    """
    assert path.exists()
    if POSIX:
        assert stat.S_IMODE(path.stat().st_mode) == mode


def path_with_console_scripts() -> str:
    """A PATH string that includes the directory holding the installed console script.

    In a venv the launcher shares the directory with `python`; in a bare
    `setup-python` install on Windows it lives in the `Scripts` subdirectory.
    """
    directories = [str(Path(sys.executable).parent)]
    if not POSIX:
        scripts = Path(sys.executable).parent / "Scripts"
        if scripts.is_dir():
            directories.append(str(scripts))
    return os.pathsep.join(directories)
