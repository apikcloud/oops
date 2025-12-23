"""Git submodule operations."""

import logging
import subprocess
from pathlib import Path

from oops.git.config import git_config_submodule
from oops.utils.compat import Optional
from oops.utils.tools import run


class GitSubmodules:
    """Class for handling git submodule operations."""

    path: str

    def add(self, url: str, name: str, path: str, branch: Optional[str] = None) -> None:
        """Add a git submodule to the repository.

        Args:
            url: URL of the submodule repository
            name: Name for the submodule
            path: Path where the submodule should be added
            branch: Optional branch to track
        """
        cmd = [
            "git",
            "submodule",
            "add",
            "--name",
            name,
        ]

        if branch:
            cmd.extend(["-b", branch])

        cmd.extend([url, path])
        run(cmd, name="add submodule")

    @property
    def gitmodules(self) -> Path:
        return Path(self.path) / ".gitmodules"

    def set_branch(self, name: str, branch: str) -> None:
        # FIXME:
        git_config_submodule(str(self.gitmodules), name, "branch", branch)

    def deinit(self, path: str, delete: bool = False) -> None:
        """Deinitialize a git submodule.

        Args:
            path: Path to the submodule
            delete: If True, also remove from index and working tree
        """
        run(["git", "submodule", "deinit", "-f", path], name="submodule deinit")

        if delete:
            # Remove from index + working tree
            run(["git", "rm", "-f", path], name="submodule delete")

    def sync(self) -> None:
        """Synchronize submodule URLs from .gitmodules to .git/config."""
        cmd = ["git", "submodule", "sync", "--recursive"]
        run(cmd, name="sync")

    def update(self, path: Optional[str] = None) -> None:
        """Update git submodules.

        Args:
            path: Optional path to specific submodule. If None, updates all recursively.
        """
        cmd = ["git", "submodule", "update", "--init"]

        if path:
            cmd.extend(["--", path])
        else:
            cmd.extend(["--recursive"])

        run(cmd, name="update")


def rename_submodule(  # noqa: PLR0913
    gitmodules_file: str,
    name: str,
    new_name: str,
    path: str,
    url: str,
    branch: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """Rename a git submodule from `name` to `new_name`, keeping the same path/url/branch.

    Args:
        gitmodules_file: Path to .gitmodules file
        name: Current submodule name
        new_name: New submodule name
        values: Dict with 'path', 'url', and optionally 'branch'
        dry_run: If True, only log what would be done

    Raises:
        ValueError: If new_name already exists
    """
    # Import here to avoid circular dependency
    from oops.git.config import get_submodule_config  # noqa: PLC0415

    # Guard if new_name already exists
    existing_new_path = get_submodule_config(gitmodules_file, new_name, "path")

    if existing_new_path:
        raise ValueError(f"A submodule named '{new_name}' already exists in .gitmodules.")

    logging.debug(f"Renaming submodule identifier '{name}' -> '{new_name}' (path stays '{path}')")

    if dry_run:
        logging.info("[dry-run] Would write .gitmodules: submodule.{name} -> submodule.{new_name}")
        logging.info("[dry-run] Would remove old sections from .gitmodules and .git/config")
        logging.info("[dry-run] Would run: git submodule sync --recursive")
        return

    # Write new section in .gitmodules
    run(["git", "config", "-f", gitmodules_file, f"submodule.{new_name}.path", path])
    run(["git", "config", "-f", gitmodules_file, f"submodule.{new_name}.url", url])

    if branch:
        run(["git", "config", "-f", gitmodules_file, f"submodule.{new_name}.branch", branch])

    # Remove old section from .gitmodules and local .git/config
    run(
        ["git", "config", "-f", gitmodules_file, "--remove-section", f"submodule.{name}"],
        check=False,
    )

    # Sync .git/config from .gitmodules
    run(["git", "submodule", "sync", "--recursive"])


def update_from(path: str, branch: str) -> None:
    """Fetch, checkout and pull the given branch for the git repository at path.

    Args:
        path: Path to the git repository
        branch: Branch name to update from
    """
    subprocess.run(
        ["git", "-C", path, "fetch", "origin", branch],
        check=True,
    )
    subprocess.run(
        ["git", "-C", path, "checkout", branch],
        check=True,
    )
    subprocess.run(
        ["git", "-C", path, "pull", "origin", branch],
        check=True,
    )
