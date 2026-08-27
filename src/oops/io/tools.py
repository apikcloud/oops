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

from oops_engine.compat import List

# ---------------------------------------------------------------------------
# Subprocess
# ---------------------------------------------------------------------------


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
