# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: installed_modules.py — oops/io/installed_modules.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from oops.core.config import config


@dataclass(frozen=True)
class InstalledModules:
    modules: list[str]
    generated_at: datetime | None  # parsed from header, falls back to mtime
    generated_by: str | None  # parsed from header, may be None
    path: Path  # absolute path of the file


def installed_modules_path(repo_root: Path) -> Path:
    """Return the conventional path of the installed-modules file."""
    return repo_root / config.project.file_installed_modules


def read_installed_modules(repo_root: Path) -> InstalledModules | None:
    """Read installed_modules.txt at repo root.

    Returns None when the file does not exist. The caller decides whether
    that is fatal (oops refactor) or merely informational.

    Header lines accepted (case-sensitive):
        # generated_at: 2026-05-09T11:46:14Z
        # generated_by: <free-form>
    Other ``#`` lines are treated as plain comments and ignored.
    Blank lines are ignored. One module name per non-comment line.
    """
    path = installed_modules_path(repo_root)
    if not path.exists():
        return None

    generated_at: datetime | None = None
    generated_by: str | None = None
    seen: dict[str, None] = {}  # insertion-order dedup via dict

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("# generated_at:"):
                value = line[len("# generated_at:"):].strip()
                try:
                    generated_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    generated_at = None
            elif line.startswith("# generated_by:"):
                generated_by = line[len("# generated_by:"):].strip()
            continue
        seen[line] = None

    if generated_at is None:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    return InstalledModules(
        modules=list(seen.keys()),
        generated_at=generated_at,
        generated_by=generated_by,
        path=path,
    )
