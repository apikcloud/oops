from pathlib import Path, PurePosixPath

from git import Repo, Submodule
from git.config import GitConfigParser


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
        match = p.parts[:1] == ("PRs",) or "pr" in p.parts
        if match:
            return True

    return False
