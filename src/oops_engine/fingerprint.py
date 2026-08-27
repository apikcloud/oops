# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: fingerprint.py — oops_engine/fingerprint.py

"""Content fingerprinting for cache invalidation. No config/Click/git dependency."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from oops_engine.compat import Iterable

_SKIP_DIRS = {"__pycache__", ".git"}
_SKIP_SUFFIXES = (".pyc",)


def fingerprint_directory(path: Path) -> str:
    """Fast fingerprint of a directory tree: sha256 over sorted (relpath, size, mtime_ns).

    Not a true content hash (doesn't read file bytes) — trades a small risk of a
    same-size/same-mtime false negative for avoiding a full read of every file on
    every invocation. Consistent with how the module's own source is expected to
    change (edits touch mtime), matching the existing get_addon_loc/cloc use case.
    """
    h = hashlib.sha256()
    for entry in sorted(_walk_files(path)):
        rel, size, mtime_ns = entry
        h.update(f"{rel}:{size}:{mtime_ns}\n".encode())
    return h.hexdigest()


def _walk_files(root: Path) -> Iterable[tuple[str, int, int]]:
    """Walk ``root``, pruning ``_SKIP_DIRS`` from traversal (not just from the
    result) and stat-ing each file exactly once. On a module directory that
    carries its own ``.git`` (e.g. a standalone-repo addon) or an accumulated
    ``__pycache__``, filtering after a full ``rglob`` descent — the previous
    approach — walked and discarded a potentially large subtree on every call.
    """
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root_str):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(_SKIP_SUFFIXES):
                continue
            full_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(full_path)
            except OSError:
                continue  # broken symlink, race with a concurrent delete, etc.
            rel = os.path.relpath(full_path, root_str)
            yield (rel, stat.st_size, stat.st_mtime_ns)


def chain_fingerprint(own: str, dependency_fingerprints: Iterable[str]) -> str:
    """Combine a module's own fingerprint with its resolved dependencies' fingerprints.

    Dependency fingerprints must themselves already be chained (each encodes its own
    transitive dependencies) — callers must process modules in load-order (bottom-up)
    so every dependency's chained fingerprint is available before its dependents.
    """
    h = hashlib.sha256(own.encode())
    for dep_fp in sorted(dependency_fingerprints):
        h.update(dep_fp.encode())
    return h.hexdigest()
