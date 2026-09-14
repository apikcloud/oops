# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: utils.py — src/oops_engine/utils.py

import ast
import subprocess
import warnings

from oops_engine.compat import Any, Generator, Optional, Tuple
from oops_engine.logger import log


def parse_python_source(source: str, filename: str = "<unknown>") -> ast.Module:
    """`ast.parse`, with SyntaxWarning noise from legacy source suppressed.

    Odoo core/addon trees going back several major versions are full of
    non-raw regex string literals with invalid escape sequences (``'\\d'``,
    ``'\\s'``, ...) — CPython's parser emits a SyntaxWarning for each one,
    even via plain `ast.parse` (escape-sequence processing happens at parse
    time, not just on exec/compile). Scanning a whole Odoo tree can surface
    hundreds of these; they are pre-existing quirks in vendored source we
    only ever read, never fix, so they drown out real output rather than
    inform it. A genuine syntax error still raises SyntaxError normally —
    only the warning category is suppressed, not parse failures.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(source, filename=filename)


def literal_eval_source(source: str) -> Any:
    """`ast.literal_eval`, with the same SyntaxWarning noise suppressed.

    `ast.literal_eval` parses internally (no `filename` parameter of its
    own, always reported as ``<unknown>``) and is subject to the same
    invalid-escape-sequence warnings as `parse_python_source` above — most
    commonly hit here parsing old Odoo `__manifest__.py` files whose
    `description` field contains a stray backslash.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.literal_eval(source)


def deep_visit(obj: Any, prefix: str = "") -> Generator[Tuple[str, Any], None, None]:
    """Yield flattened (path, value) pairs by recursively walking a nested structure.

    Dict keys become dot-separated segments; list indices become ``[n]`` segments.
    Example: ``assets.web.assets_backend[0]`` → ``"/module/static/..."``

    Args:
        obj: Nested dict, list, tuple, or scalar to walk.
        prefix: Accumulated path prefix for the current node. Defaults to "".

    Yields:
        Tuple of (dotted_path_string, leaf_value) for each scalar encountered.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            yield from deep_visit(v, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from deep_visit(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


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
