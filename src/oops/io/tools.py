# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: tools.py — oops/io/tools.py

"""
Low-level runtime utilities: subprocess execution and shell script runners.

Sections:
    - Subprocess: wrappers around subprocess.run and shell script execution
"""

import json
import subprocess
import sys

from oops.core.compat import List, Optional
from oops.core.logger import log

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

    log.debug(f"[{name or 'run'}] {' '.join(cmd)}")

    res = subprocess.run(cmd, check=check, **kwargs)
    return res.stdout if capture else None


def run_oops(args: List[str], cwd: str, timeout: int = 180) -> dict:
    """Run ``oops <args> --format json`` in *cwd* and return the parsed payload.

    Check commands exit non-zero when a check fails but still print the JSON
    payload to stdout, so the payload is parsed regardless of the return code.
    A non-JSON stdout (a real crash) surfaces stderr as an error payload that
    the SPA renders via its "error" view.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "oops", *args, "--format", "json"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        msg = proc.stderr.strip() or f"oops {' '.join(args)} failed (exit {proc.returncode})"
        return {"metadata": {"command": "error"}, "error": msg}
