"""Git core operations - Basic git commands."""

import contextlib
import os
import subprocess
from configparser import ConfigParser
from pathlib import Path

from oops.core.exceptions import NoGitRepository
from oops.git.config import GitModule
from oops.git.utils import extract_submodule_name
from oops.utils.compat import Optional
from oops.utils.io import ensure_parent, is_pull_request_path
from oops.utils.net import parse_repository_url
from oops.utils.tools import run


class GitRepository:
    def __init__(self, force_workdir: bool = True) -> None:
        self.path = self._get_root_path()
        self.gitignore = self.path / ".gitignore"
        self.gitmodules = self.path / ".gitmodules"

        if force_workdir:
            os.chdir(self.path)

    def _get_root_path(self) -> Path:
        """Get the top-level directory of the current git repository.

        Returns:
            Path to the git repository root

        Raises:
            NoGitRepository: If not in a git repository
        """
        out = run(["git", "rev-parse", "--show-toplevel"], capture=True, name="top")

        if not out:
            raise NoGitRepository()

        return Path(out.strip())

    @property
    def has_gitmodules(self) -> bool:
        """Check if the repository has submodules.

        Returns:
            True if .gitmodules exists, False otherwise
        """
        return self.gitmodules.exists()

    @staticmethod
    def commit(message: str, description: Optional[str] = None, skip_hook: bool = False) -> None:
        """Create a git commit with the given message and optional description.

        Args:
            message: Commit message
            description: Optional longer description (separate -m flag)
            skip_hook: If True, skip pre-commit hooks (--no-verify)
        """
        cmd = ["git", "commit", "-m", message]

        if description:
            # Use -m twice to preserve newlines robustly
            cmd.extend(["-m", description])

        if skip_hook:
            cmd.insert(2, "--no-verify")

        run(cmd, name="commit")

    @staticmethod
    def commit_if_needed(paths: list, message: str, add: bool = True) -> bool:
        """Commit files only if there are changes.

        Args:
            paths: List of file paths to commit
            message: Commit message
            add: If True, add files before checking for changes

        Returns:
            True if a commit was created, False otherwise
        """
        if add:
            cmd = ["git", "add"] + paths
            subprocess.check_call(cmd)

        cmd = ["git", "diff", "--quiet", "--exit-code", "--cached", "--"] + paths
        r = subprocess.call(cmd)

        if r != 0:
            cmd = ["git", "commit", "-m", message, "--"] + paths
            subprocess.check_call(cmd)
            return True

        return False

    @staticmethod
    def add(paths: list) -> None:
        """Add files to the git index.

        Args:
            paths: List of file paths to add
        """
        cmd = ["git", "add"] + paths
        subprocess.check_call(cmd)

    @staticmethod
    def add_all() -> None:
        """Add all changes to the git index (git add -A)."""
        run(["git", "add", "-A"], name="add")

    @staticmethod
    def reset_hard() -> None:
        """Reset the working directory to HEAD (git reset --hard)."""
        run(["git", "reset", "--hard"])

    @staticmethod
    def move(src: Path, dst: Path) -> None:
        """Move a file or directory using git mv, with fallback to manual move.

        Args:
            src: Source path
            dst: Destination path
        """
        ensure_parent(dst)

        try:
            run(["git", "mv", "-k", str(src), str(dst)])
        except subprocess.CalledProcessError:
            if src.exists():
                src.rename(dst)
            run(["git", "add", "-A", str(dst)])

            with contextlib.suppress(subprocess.CalledProcessError):
                run(["git", "rm", "-f", "--cached", str(src)])

    def get_remote_url(self, origin: str = "origin") -> tuple:
        """Get the remote URL for a git repository.

        Args:
            path: Path to the git repository
            origin: Remote name (default: "origin")

        Returns:
            Tuple of (url, owner, repo) from parse_repository_url
        """
        result = subprocess.run(
            ["git", "-C", self.path, "remote", "get-url", origin],
            check=True,
            text=True,
            capture_output=True,
        )

        return parse_repository_url(result.stdout.strip())

    def parse_gitmodules(self):
        """Parse .gitmodules file and yield submodule information.

        Args:
            filepath: Path to .gitmodules file

        Yields:
            Tuple of (name, path, branch, url, is_pull_request)
        """
        config = ConfigParser()
        config.read(self.gitmodules)

        for section in config.sections():
            name = extract_submodule_name(section)
            path = config.get(section, "path", fallback=None)
            branch = config.get(section, "branch", fallback=None)
            url = config.get(section, "url", fallback=None)
            pr = is_pull_request_path(path) or is_pull_request_path(name)

            yield GitModule(name, path, branch, url, pr)
