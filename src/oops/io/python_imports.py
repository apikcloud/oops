# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: python_imports.py — oops/io/python_imports.py

"""Walk a Python package's __init__.py import chain.

Odoo only loads Python files that are explicitly imported through the
package's __init__.py chain. This module resolves that set so callers
can mirror Odoo's loading semantics rather than what's on disk.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def discover_imported_files(package_dir: Path) -> list[Path]:
    """Return absolute paths of .py files reachable from ``package_dir/__init__.py``.

    Follows ``from . import name`` and ``from .name import …`` statements
    recursively. A name resolves to ``name.py`` when that file exists, or
    to ``name/`` when that subdirectory contains an ``__init__.py``
    (recursing into it). Names that resolve to neither are skipped with
    a debug log line.

    Returns an empty list when ``package_dir`` does not exist or contains
    no ``__init__.py``. Files are returned in deterministic (depth-first,
    declaration) order; duplicates are de-duplicated.

    Args:
        package_dir: Directory expected to contain an ``__init__.py``.

    Returns:
        Absolute, resolved ``Path`` objects pointing to the imported
        ``.py`` files (excluding ``__init__.py`` files themselves).
    """
    if not package_dir.is_dir():
        return []
    init_path = package_dir / "__init__.py"
    if not init_path.is_file():
        return []
    seen: set[Path] = set()
    out: list[Path] = []
    _walk(package_dir, seen, out)
    return out


def _walk(package_dir: Path, seen: set[Path], out: list[Path]) -> None:
    init_path = package_dir / "__init__.py"
    if not init_path.is_file():
        return
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        log.debug("skipping %s (parse failed: %s)", init_path, exc)
        return
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level < 1:
            continue
        # Two shapes:
        #   from . import a, b, c           → node.module is None, names=[a,b,c]
        #   from .sub import x, y           → node.module='sub', names=[x,y]
        if node.module is None:
            for alias in node.names:
                _resolve_name(package_dir, alias.name, seen, out)
        else:
            target = package_dir / node.module
            if target.is_dir() and (target / "__init__.py").is_file():
                _walk(target, seen, out)
            elif (package_dir / f"{node.module}.py").is_file():
                _resolve_name(package_dir, node.module, seen, out)


def _resolve_name(
    package_dir: Path, name: str, seen: set[Path], out: list[Path]
) -> None:
    py_file = package_dir / f"{name}.py"
    if py_file.is_file():
        resolved = py_file.resolve()
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
        return
    sub_pkg = package_dir / name
    if sub_pkg.is_dir() and (sub_pkg / "__init__.py").is_file():
        _walk(sub_pkg, seen, out)
        return
    log.debug(
        "import target %r from %s/__init__.py resolves to nothing",
        name,
        package_dir,
    )
