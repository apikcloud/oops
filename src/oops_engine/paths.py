# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: paths.py — oops_engine/paths.py

from pathlib import Path

# ---------------------------------------------------------------------------
# KB cache (project-local)
# ---------------------------------------------------------------------------

CACHE_DIR_NAME = ".oops-cache"


def project_kb_path(repo_root: Path) -> Path:
    """Return the path of the project KB database for a given repo root.

    Returns:
        ``<repo_root>/.oops-cache/kb.db`` (does not check for existence).
    """
    return repo_root / CACHE_DIR_NAME / "kb.db"


def global_kb_dir() -> Path:
    """Return the default global KB cache directory.

    Returns:
        ``~/.cache/oops/kb`` (does not check for existence).
    """
    return Path.home() / ".cache" / "oops" / "kb"


def global_kb_path(version: str) -> Path:
    """Return the path of the global KB database for a given Odoo version.

    Args:
        version: Odoo version string, e.g. ``'17.0'``.

    Returns:
        ``~/.cache/oops/kb/<version>.db`` (does not check for existence).
    """
    return global_kb_dir() / f"{version}.db"
