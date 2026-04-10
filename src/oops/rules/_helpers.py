# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: _helpers.py — oops/rules/_helpers.py

"""Shared helpers for oops fixit rules.

Import from here in every rule module so future rules don't duplicate code::

    from oops.rules._helpers import (
        load_manifest_cfg,
        extract_kv,
        string_value,
        key_name,
        sort_key,
        Elements,
        VERSION_PATTERN,
        # git-aware helpers (for version-bump rule):
        set_lint_path,
        get_lint_path,
        git_repo_root,
        staged_addon_manifest_relpaths,
        file_at_ref,
        last_tag,
        parse_version_str,
        module_version,
    )
"""

import ast
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union  # noqa: UP035

import libcst as cst

from oops.core.config import ManifestConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fallback version pattern when odoo_version is not set in config.
# Matches the 5-part Odoo format: <odoo_major>.<odoo_minor>.<x>.<y>.<z>
# e.g. "16.0.1.0.0", "19.0.3.2.1"
VERSION_PATTERN = r"^\d+\.\d+\.\d+\.\d+\.\d+$"

# Type alias for the sequence of elements inside a cst.Dict.
Elements = Sequence[Union[cst.DictElement, cst.StarredDictElement]]

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def load_manifest_cfg() -> Optional[ManifestConfig]:
    """Return the manifest section of .oops.yaml, or None if unavailable.

    Rules call this in ``__init__`` and fall back to class-level defaults when
    config is not present (e.g. standalone fixit invocation or CI without a
    project-level ``.oops.yaml``).
    """
    try:
        from oops.core.config import config as _cfg  # noqa: PLC0415

        return _cfg.manifest
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CST helpers
# ---------------------------------------------------------------------------


def extract_kv(node: cst.Dict) -> "dict[str, cst.BaseExpression]":
    """Return a ``{key_str: value_node}`` map for all plain-string-keyed entries.

    Non-string keys (variables, f-strings, …) are silently skipped.
    """
    kv: dict[str, cst.BaseExpression] = {}
    for el in node.elements or []:
        if not isinstance(el, cst.DictElement):
            continue
        if isinstance(el.key, cst.SimpleString):
            kv[el.key.value.strip("'\"")] = el.value
    return kv


def string_value(node: cst.BaseExpression) -> "str | None":
    """Return the unquoted Python str for a ``SimpleString`` node, or None.

    Use this instead of accessing ``.value`` directly — it handles evaluation
    (escape sequences, raw strings) and skips f-strings or concatenations.
    """
    if isinstance(node, cst.SimpleString):
        val = node.evaluated_value
        return val if isinstance(val, str) else None
    return None


def key_name(element: Any) -> "str | None":
    """Return the string key of a ``DictElement``, or None if not a plain string."""
    key = element.key
    if isinstance(key, cst.SimpleString):
        return key.value.strip("'\"")
    return None


def sort_key(name: "str | None", order: List[str]) -> Tuple[int, str]:
    """Return a ``(position, name)`` tuple for sorting dict elements into *order*.

    Keys absent from *order* are pushed after all known keys; ties are broken
    by name so the sort is stable and deterministic.
    """
    if name is None:
        return (len(order), "")
    try:
        return (order.index(name), name)
    except ValueError:
        return (len(order), name)


# ---------------------------------------------------------------------------
# Current lint path — set by run_fixit before processing each file
# ---------------------------------------------------------------------------
#
# fixit 2.x does not expose the file path to individual rule instances.
# common.py's run_fixit() calls set_lint_path(path) before fixit_file() so
# that rules can read the current file path in their __init__.

_current_lint_path: Optional[Path] = None


def set_lint_path(path: Path) -> None:
    """Record the file currently being linted. Called by run_fixit() per file."""
    global _current_lint_path
    _current_lint_path = path


def get_lint_path() -> Optional[Path]:
    """Return the file currently being linted, or None if not set."""
    return _current_lint_path


# ---------------------------------------------------------------------------
# Git helpers (cached — safe to call repeatedly within one fixit run)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def git_repo_root() -> Optional[Path]:
    """Return the absolute path of the git repository root, or None."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else None


@lru_cache(maxsize=None)
def _staged_files() -> frozenset:
    """Return repo-relative paths of files currently staged (ACMR filter)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    return frozenset(result.stdout.splitlines()) if result.returncode == 0 else frozenset()


@lru_cache(maxsize=None)
def last_tag() -> Optional[str]:
    """Return the most recent tag reachable from HEAD, or None."""
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


@lru_cache(maxsize=2048)
def file_at_ref(rel_path: str, ref: str) -> Optional[str]:
    """Return the content of *rel_path* at *ref*, or None if absent.

    Use ``ref="HEAD"`` for the last commit, a tag name for a release, or
    ``ref=":"`` to read from the git index (staged content).
    """
    git_path = f":{rel_path}" if ref == ":" else f"{ref}:{rel_path}"
    result = subprocess.run(["git", "show", git_path], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


# ---------------------------------------------------------------------------
# Addon discovery from staged paths
# ---------------------------------------------------------------------------


def _find_manifest_rel(addon_dir: Path, repo_root: Path) -> Optional[str]:
    """Return the repo-relative path to the manifest inside *addon_dir*, or None."""
    try:
        from oops.core.config import config as _cfg  # noqa: PLC0415
        names = _cfg.manifest_names
    except Exception:
        names = ["__manifest__.py", "__openerp__.py"]
    for name in names:
        candidate = addon_dir / name
        if candidate.exists():
            return str(candidate.relative_to(repo_root))
    return None


def _addon_root_of(path: Path, repo_root: Path) -> Optional[Path]:
    """Walk *path* upward until a directory that contains a manifest is found."""
    try:
        from oops.core.config import config as _cfg  # noqa: PLC0415
        names = _cfg.manifest_names
    except Exception:
        names = ["__manifest__.py", "__openerp__.py"]

    current = path if path.is_dir() else path.parent
    # Stop at repo_root (don't escape the repository)
    while True:
        if any((current / name).exists() for name in names):
            return current
        if current == repo_root:
            break
        current = current.parent
    return None


@lru_cache(maxsize=None)
def staged_addon_manifest_relpaths() -> frozenset:
    """Return repo-relative manifest paths for every addon with staged files.

    Cached for the lifetime of the process — safe because staged files don't
    change during a single oops-man-check / oops-man-fix invocation.
    """
    repo_root = git_repo_root()
    if not repo_root:
        return frozenset()

    manifests: set = set()
    for rel in _staged_files():
        full = repo_root / rel
        addon_root = _addon_root_of(full, repo_root)
        if addon_root is None:
            continue
        manifest_rel = _find_manifest_rel(addon_root, repo_root)
        if manifest_rel:
            manifests.add(manifest_rel)
    return frozenset(manifests)


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def parse_version_str(source: str) -> Optional[Tuple[int, ...]]:
    """Extract the ``version`` tuple from manifest source text.

    Returns a tuple of ints such as ``(19, 0, 1, 0, 0)``, or None if the
    field is absent or cannot be parsed.
    """
    try:
        data = ast.literal_eval(source)
        raw = data.get("version", "") if isinstance(data, dict) else ""
        if not raw:
            return None
        return tuple(int(p) for p in str(raw).split("."))
    except Exception:
        return None


def module_version(version: Tuple[int, ...]) -> Tuple[int, ...]:
    """Return the module-specific tail of an Odoo version tuple.

    Odoo versions are ``<major>.<minor>.<x>.<y>.<z>``; the module part is the
    last three components. Shorter tuples (legacy format) are returned whole.

    Comparing only the module part prevents false positives when migrating an
    addon to a new Odoo major version (e.g. 17.0 → 18.0) without bumping the
    module-level version.
    """
    return version[-3:] if len(version) >= 5 else version
