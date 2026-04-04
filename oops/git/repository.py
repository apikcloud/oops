# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: repository.py — oops/git/repository.py

# TODO: deprecated, to be removed in the future.

import contextlib
import subprocess
from pathlib import Path

from oops.core.models import CommitInfo
from oops.io.manifest import find_addons_extended
from oops.io.tools import run
from oops.utils.compat import Optional


def get_last_commit(path: Optional[str] = None) -> Optional[CommitInfo]:
    """Get information about the last commit.

    Args:
        path: Optional path to git repository (uses current directory if None)

    Returns:
        CommitInfo object or None if not a git repo or no commits
    """
    cmd = ["git", "log", "-1", "--date=iso-strict", "--pretty=format:%h;%an;%ae;%ad;%s"]

    if path:
        cmd.insert(1, "-C")
        cmd.insert(2, path)

    try:
        output = run(cmd, capture=True)

        if not output:
            return None

        return CommitInfo.from_string(output)

    except subprocess.CalledProcessError:
        return None


def list_available_addons(root: Path):
    """List all available addons from git submodules.

    Yields addon information from each submodule. Updates submodules if needed.

    Args:
        root: Root path of the git repository

    Yields:
        AddonInfo objects for each addon found

    Raises:
        FileNotFoundError: If .gitmodules doesn't exist
    """
    # Import here to avoid circular dependency
    from oops.git.config import parse_submodules_extended  # noqa: PLC0415
    from oops.git.submodules import submodule_update  # noqa: PLC0415

    gitmodules = root / ".gitmodules"

    if not gitmodules.exists():
        raise FileNotFoundError()

    subs = parse_submodules_extended(gitmodules)

    for _, info in subs.items():
        sub_path = info.get("path")
        if not sub_path:
            continue

        abs_path = root / sub_path

        if not abs_path.exists():
            with contextlib.suppress(subprocess.CalledProcessError):
                submodule_update(sub_path)

            # re-check
            if not abs_path.exists():
                continue

        yield from find_addons_extended(abs_path)
