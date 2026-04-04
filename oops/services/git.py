# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: git.py — oops/services/git.py

from pathlib import Path, PurePosixPath

import click
from git import GitCommandError, InvalidGitRepositoryError, Repo, Submodule
from git.config import GitConfigParser

from oops.core.messages import commit_messages
from oops.core.paths import PR_DIR
from oops.utils.compat import Optional
from oops.utils.render import print_success, print_warning


def read_gitmodules(repo: Repo) -> GitConfigParser:
    """Open the .gitmodules file of a repository for reading and writing.

    Args:
        repo: GitPython Repo object with a working tree.

    Returns:
        GitConfigParser instance pointing at .gitmodules.

    Raises:
        ValueError: If the repository has no working tree directory.
    """

    if repo.working_tree_dir is None:
        raise ValueError("Repository does not have a working tree directory")

    gitmodules_path = Path(repo.working_tree_dir) / ".gitmodules"
    cfg = GitConfigParser(str(gitmodules_path), read_only=False)

    return cfg


def is_pull_request(submodule: Submodule) -> bool:
    """Determine whether a submodule represents a pull request.

    Checks both the submodule path and name for pull-request path conventions.

    Args:
        submodule: GitPython Submodule to inspect.

    Returns:
        True if the submodule path or name matches pull-request conventions.
    """

    for raw in (submodule.path, submodule.name):
        p = PurePosixPath(raw)
        match = p.parts[:1] == (PR_DIR,) or "pr" in p.parts
        if match:
            return True

    return False


def get_local_repo() -> "tuple[Repo, Path]":
    """Locate and return the git repository containing the current directory.

    Returns:
        Tuple of (Repo, repo_root_path).

    Raises:
        click.ClickException: If no git repository is found or it has no working tree.
    """

    try:
        repo = Repo(Path.cwd(), search_parent_directories=True)
    except InvalidGitRepositoryError as error:
        raise click.ClickException("Not inside a git repository.") from error
    except Exception as err:
        raise click.ClickException(f"Error accessing git repository: {err}") from err

    if repo.working_tree_dir is None:
        raise click.ClickException("Not inside a git repository.")
    return repo, Path(repo.working_tree_dir)


def show_diff(tmpdir: Path, files: list, local_repo: Repo, repo_root: Path) -> bool:
    """Print the diff between remote files and their local counterparts.

    Args:
        tmpdir: Directory containing the remote (downloaded) versions of the files.
        files: Relative file paths to compare.
        local_repo: GitPython Repo used to run git diff --no-index.
        repo_root: Local repository root where the files live.

    Returns:
        True if at least one file differs or is new, False if all files are identical.
    """
    has_changes = False

    for f in files:
        src = tmpdir / f
        dst = repo_root / f

        if not src.exists():
            click.echo(click.style(f"[SKIP] {f}", fg="yellow") + " — not present in remote repo")
            continue

        if not dst.exists():
            click.echo(click.style(f"[NEW]  {f}", fg="green") + " — will be created")
            has_changes = True
            continue

        # git diff --no-index compares two arbitrary paths (outside a repo)
        try:
            diff_output = local_repo.git.diff("--no-index", "--color", str(dst), str(src))
            # No exception = exit code 0 = no differences
        except GitCommandError as exc:
            # Exit code 1 = differences found; stdout contains the diff
            diff_output = exc.stdout

        if diff_output:
            click.echo(diff_output)
            has_changes = True

    return has_changes


def commit(  # noqa: PLR0913
    local_repo: Repo,
    repo_root: Path,
    files: list,
    message_name: str,
    skip_hooks: bool = False,
    remove: bool = False,
    **kwargs,
) -> None:
    """Stage files and create a commit using a named commit message template.

    Args:
        local_repo: GitPython Repo to commit into.
        repo_root: Repository root used to resolve absolute file paths.
        files: Relative paths of files to stage.
        message_name: Attribute name on commit_messages holding the message template.
        skip_hooks: If True, bypass pre-commit hooks. Defaults to False.
        remove: If True, remove files from the index instead of adding them. Defaults to False.
        **kwargs: Optional format arguments interpolated into the commit message template.

    Raises:
        ValueError: If message_name is not found or a template placeholder is missing.
    """

    changes = [str(repo_root / f) for f in files]
    if remove:
        local_repo.index.remove(changes)
    else:
        local_repo.index.add(changes)

    if not local_repo.index.diff("HEAD"):
        print_warning("Nothing to commit (index identical to HEAD).")
        return

    message = getattr(commit_messages, message_name, None)
    if message is None:
        raise ValueError(f"Unknown commit message name: {message_name}")
    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError as exc:
            raise ValueError(f"Missing placeholder for commit message: {exc}") from exc

    commit = local_repo.index.commit(message, skip_hooks=skip_hooks)
    print_success(f"Commit {commit.hexsha[:8]} — {message}")


def get_submodule_sha(repo: Repo, ref: str, path: str) -> Optional[str]:
    """Resolve the recorded SHA of a submodule at a given commit-ish.

    Args:
        repo: GitPython Repo containing the submodule.
        ref: Commit-ish (branch, tag, or SHA) to inspect.
        path: Path of the submodule relative to the repository root.

    Returns:
        SHA string of the submodule at the given ref, or None if not found.
    """
    try:
        return repo.git.rev_parse(f"{ref}:{path}")
    except Exception:
        return None
