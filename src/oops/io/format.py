# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: format.py — oops/io/format.py

"""Best-effort source formatting applied before staging files in oops commits.

Dispatches by file extension to external formatters (ruff for Python, prettier
for XML) and always applies in-process text normalization (trailing whitespace,
LF line endings, final newline). External formatters run with cwd=repo_root so
the target repository's own config files (.ruff.toml, prettier.config.cjs) are
honoured automatically. Missing binaries emit a one-time warning and degrade to
text normalization only.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from oops.utils.render import print_warning


@lru_cache(maxsize=None)
def _has(binary: str) -> bool:
    """Return True if binary is available in PATH; warn once if not."""
    if shutil.which(binary) is not None:
        return True
    print_warning(
        f"'{binary}' not found in PATH — files will be text-normalized only. "
        f"Install it globally (e.g. `uv tool install {binary}`) to enable full formatting."
    )
    return False


def _run(cmd: list, cwd: Path) -> None:
    """Run a formatter subprocess; ignore errors (best-effort)."""
    subprocess.run(cmd, cwd=str(cwd), check=False, capture_output=True)


def format_python(path: Path, repo_root: Path) -> None:
    """Run `ruff format <path>` if ruff is available in PATH.

    Args:
        path: Absolute path to the Python file to format.
        repo_root: Repository root; ruff reads .ruff.toml / pyproject.toml from here.
    """
    if _has("ruff"):
        _run(["ruff", "format", str(path)], cwd=repo_root)


def format_xml(path: Path, repo_root: Path) -> None:
    """Run `prettier --write <path>` if prettier is available in PATH.

    Args:
        path: Absolute path to the XML file to format.
        repo_root: Repository root; prettier reads prettier.config.cjs / .prettierrc from here.
    """
    if _has("prettier"):
        _run(["prettier", "--write", str(path)], cwd=repo_root)


def normalize_text(path: Path) -> None:
    """Strip trailing whitespace, normalize line endings to LF, ensure final newline.

    No-op for binary files (not decodable as UTF-8) and non-existent paths.

    Args:
        path: Path to the text file to normalize.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    normalized = "\n".join(line.rstrip() for line in text.splitlines())
    if normalized:
        normalized += "\n"
    if normalized != text:
        path.write_text(normalized, encoding="utf-8")


def format_file(path: Path, repo_root: Path) -> None:
    """Format a single file by extension, then normalize whitespace.

    Dispatches .py to ruff-format and .xml to prettier. All text files
    (any extension) receive trailing-whitespace + LF + final-newline
    normalization. Directories and non-existent paths are silently skipped.

    Args:
        path: Absolute path to the file to format.
        repo_root: Repository root for formatter config discovery.
    """
    if not path.is_file():
        return
    suffix = path.suffix.lower()
    if suffix == ".py":
        format_python(path, repo_root)
    elif suffix == ".xml":
        format_xml(path, repo_root)
    normalize_text(path)
