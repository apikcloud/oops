# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: git.py — oops/services/git.py

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from git.util import IterableList

import click
from git import GitCommandError, InvalidGitRepositoryError, Repo, Submodule
from git.config import GitConfigParser
from oops.core.compat import List, Optional, Tuple
from oops.core.exceptions import OopsError
from oops.core.messages import commit_messages
from oops.core.metadata import update_metadata
from oops.core.models import CommitInfo, Result
from oops.core.paths import PR_DIR
from oops.io.format import format_file
from oops.io.manifest import find_addons_extended
from oops.io.tools import run
from oops.utils.net import encode_url
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


def require_repository() -> "tuple[Repo, Path]":
    """Guard: locate and return the git repository containing the current directory.

    Returns:
        Tuple of (Repo, repo_root_path).

    Raises:
        click.ClickException: If no git repository is found or it has no working tree.
    """

    try:
        repo = Repo(Path.cwd(), search_parent_directories=True)
    except InvalidGitRepositoryError as error:
        raise OopsError("Not inside a git repository.") from error
    except Exception as err:
        raise OopsError(f"Error accessing git repository: {err}") from err

    if repo.working_tree_dir is None:
        raise OopsError("Not inside a git repository.")

    update_metadata(
        project_path=str(Path(repo.working_tree_dir)),
        project_name=Path(repo.working_tree_dir).name,
        git_commit=repo.head.commit.hexsha,
        git_branch=repo.active_branch.name,
    )

    return repo, Path(repo.working_tree_dir)


def require_submodules(repo: "Repo") -> "IterableList[Submodule]":
    """Guard: assert the repository has at least one registered submodule.

    Intended as the first call inside commands that operate on submodules
    (e.g. ``oops submodules update``, ``oops submodules show``), immediately
    after :func:`require_repository`.

    Args:
        repo: The git repository, typically the first element of the tuple
            returned by :func:`require_repository`.

    Returns:
        The repository's submodule list (``repo.submodules``), guaranteed
        non-empty. Returned for caller convenience so the precondition and
        the iteration target are obtained in one call.

    Raises:
        OopsError: If the repository has no registered submodules. Recorded
            by :class:`~oops.commands.base.OopsCommand` telemetry as
            ``"OopsError"`` and rendered as ``✘ <message>`` on stderr.
    """
    if not repo.submodules:
        raise OopsError("This command requires submodules.")
    return repo.submodules


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
    already_staged: bool = False,
    remove_and_add: bool = False,
    **kwargs: object,
) -> None:
    """Stage files and create a commit using a named commit message template.

    Args:
        local_repo: GitPython Repo to commit into.
        repo_root: Repository root used to resolve absolute file paths.
        files: Relative paths of files to stage.
        message_name: Attribute name on commit_messages holding the message template.
        skip_hooks: If True, bypass pre-commit hooks. Defaults to False.
        remove: If True, remove files from the index instead of adding them. Defaults to False.
        already_staged: If True, the index process is skipped and only the commit part is done.
        remove_and_add:
        **kwargs: Optional format arguments interpolated into the commit message template.

    Raises:
        ValueError: If message_name is not found or a template placeholder is missing.
    """

    changes = [str(repo_root / f) for f in files]

    # Format and normalize files before staging (add paths only).
    if not remove and not already_staged:
        for path_str in changes:
            p = Path(path_str)
            if p.is_file():
                format_file(p, repo_root)

    if already_staged:
        # Skip as files are already in the index (only for submodule updates).
        pass
    elif remove:
        local_repo.index.remove(changes)
    elif remove_and_add:
        # Remove the old index entry (e.g. a symlink), then re-add using the git
        # CLI so that directories are staged recursively — index.add() does not
        # walk directory trees.
        local_repo.index.remove(changes)
        for path in changes:
            local_repo.git.add(path)
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


def commit_v2(  # noqa: PLR0913
    local_repo: Repo,
    repo_root: Path,
    files: list,
    message_name: str,
    skip_hooks: bool = False,
    remove: bool = False,
    already_staged: bool = False,
    remove_and_add: bool = False,
    **kwargs: object,
) -> Result[list]:
    """
    TODO: complete docstrings
    Stage files and create a commit using a named commit message template.

    Args:
        local_repo: GitPython Repo to commit into.
        repo_root: Repository root used to resolve absolute file paths.
        files: Relative paths of files to stage.
        message_name: Attribute name on commit_messages holding the message template.
        skip_hooks: If True, bypass pre-commit hooks. Defaults to False.
        remove: If True, remove files from the index instead of adding them. Defaults to False.
        already_staged: If True, the index process is skipped and only the commit part is done.
        remove_and_add:
        **kwargs: Optional format arguments interpolated into the commit message template.

    Returns:
        Result:
    """

    result: Result[list] = Result()
    changes = [str(repo_root / f) for f in files]

    # Format and normalize files before staging (add paths only).
    if not remove and not already_staged:
        for path_str in changes:
            p = Path(path_str)
            if p.is_file():
                format_file(p, repo_root)

    if already_staged:
        # Skip as files are already in the index (only for submodule updates).
        pass
    elif remove:
        local_repo.index.remove(changes)
    elif remove_and_add:
        # Remove the old index entry (e.g. a symlink), then re-add using the git
        # CLI so that directories are staged recursively — index.add() does not
        # walk directory trees.
        local_repo.index.remove(changes)
        for path in changes:
            local_repo.git.add(path)
    else:
        local_repo.index.add(changes)

    # list all changes in current index
    result.data = [a.a_path for a in local_repo.index.diff("HEAD")]

    if not local_repo.index.diff("HEAD"):
        result.add_warning("Nothing to commit (index identical to HEAD).")
        return result

    message = getattr(commit_messages, message_name, None)
    if message is None:
        result.add_error(f"Unknown commit message name: {message_name}")
        return result

    if kwargs:
        try:
            message = message.format(**kwargs)
        except KeyError as exc:
            result.add_error(f"Missing placeholder for commit message: {exc}")
            return result

    commit = local_repo.index.commit(message, skip_hooks=skip_hooks)
    result.add_message(f"Commit {commit.hexsha[:8]} — {message}")

    return result


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


def list_available_addons(repo: Repo, repo_path: Path) -> "Generator[tuple[str, Path, dict]]":
    """Yield addons found in each initialized submodule of the repository.

    Submodules that are not yet initialized on disk are initialized automatically.

    Args:
        repo: GitPython Repo object.
        repo_path: Absolute path to the repository root.

    Yields:
        Tuple of (name, path, manifest) for each addon found in any submodule.
    """
    for sub in repo.submodules:
        abs_path = repo_path / sub.path
        if not abs_path.exists():
            try:
                sub.update(init=True, recursive=False)
            except Exception:
                continue
            if not abs_path.exists():
                continue
        yield from find_addons_extended(abs_path)


@lru_cache()
def _list_submodules_cached(working_dir: str) -> dict:
    repo = Repo(working_dir)
    subs = {}
    for sub in repo.submodules:
        try:
            canonical_url = encode_url(sub.url, "https", suffix=False)
        except (ValueError, AttributeError):
            canonical_url = ""
        try:
            branch = sub.branch_name
        except Exception:
            branch = ""
        subs[sub.path] = {
            "name": sub.name,
            "branch": branch,
            "url": canonical_url,
            "pr": is_pull_request(sub),
        }
    return subs


def list_submodules(repo: Repo) -> dict:
    """Return submodule metadata for all submodules in the repository.

    Results are cached by working directory path; subsequent calls with the
    same repo are free.

    Returns:
        Dict mapping relative path → metadata dict (url, org, branch, pr flag).
    """
    return _list_submodules_cached(repo.working_dir)


def browse_submodules(submodules: List[Submodule], names: Tuple[str]) -> "Generator[Tuple[int, Submodule]]":
    """Yield (1-based index, submodule) for each submodule whose name is in *names*.

    Args:
        submodules: Full list of submodules to filter.
        names: Tuple of submodule names to include.

    Yields:
        Tuples of (index, Submodule) for matching entries.
    """
    selected = [s for s in submodules if s.name in names]
    yield from enumerate(selected, 1)
