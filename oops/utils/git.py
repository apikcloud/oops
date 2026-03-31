# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: git.py — oops/utils/git.py

from pathlib import Path, PurePosixPath

from git import Repo, Submodule
from git.config import GitConfigParser

from oops.core.paths import PR_DIR


def read_gitmodules(repo: Repo) -> GitConfigParser:
    """Read the .gitmodules file of the given repository."""

    if repo.working_tree_dir is None:
        raise ValueError("Repository does not have a working tree directory")

    gitmodules_path = Path(repo.working_tree_dir) / ".gitmodules"
    cfg = GitConfigParser(str(gitmodules_path), read_only=False)

    return cfg


def is_pull_request(submodule: Submodule) -> bool:
    for raw in (submodule.path, submodule.name):
        p = PurePosixPath(raw)
        match = p.parts[:1] == (PR_DIR,) or "pr" in p.parts
        if match:
            return True

    return False
