# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: tools.py — oops/io/tools.py

"""
Low-level runtime utilities: subprocess execution and shell script runners.

Sections:
    - Subprocess: wrappers around subprocess.run and shell script execution
"""

import logging
import subprocess

from oops.utils.compat import Optional

# ---------------------------------------------------------------------------
# Subprocess
# ---------------------------------------------------------------------------


def run(
    cmd: list,
    check: bool = True,
    capture: bool = False,
    cwd: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[str]:
    """Run a subprocess command and optionally capture its output.

    Args:
        cmd: Command and arguments to execute.
        check: If True, raise CalledProcessError on non-zero exit. Defaults to True.
        capture: If True, capture and return stdout. Defaults to False.
        cwd: Working directory for the subprocess. Defaults to None.
        name: Label used in debug log output. Defaults to None.

    Returns:
        Captured stdout as a string if capture is True, otherwise None.
    """
    kwargs: dict = dict(text=True, cwd=cwd)
    if capture:
        # assign explicitly to avoid static type checkers inferring incompatible dict value types
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    logging.debug(f"[{name or 'run'}] {' '.join(cmd)}")

    res = subprocess.run(cmd, check=check, **kwargs)
    return res.stdout if capture else None
