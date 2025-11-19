import logging
import os
import subprocess

from oops.core.exceptions import ScriptNotFound
from oops.utils.compat import Optional


def get_exec_dir():
    """Return the directory where the current script is located."""

    return os.path.dirname(__file__)


def run(
    cmd: list,
    check: bool = True,
    capture: bool = False,
    cwd: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[str]:
    kwargs: dict = dict(text=True, cwd=cwd)
    if capture:
        # assign explicitly to avoid static type checkers inferring incompatible dict value types
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    logging.debug(f"[{name or 'run'}] {' '.join(cmd)}")

    res = subprocess.run(cmd, check=check, **kwargs)
    return res.stdout if capture else None


def run_script(filepath: str, *args: str) -> str:
    """Run a shell script and return its output as a string."""

    path = os.path.join(get_exec_dir(), filepath)
    logging.debug(f"[script] Running script from {path}")

    if not os.path.exists(path):
        raise ScriptNotFound()

    result = subprocess.run([path, *args], capture_output=True, text=True, check=True)
    return result.stdout
