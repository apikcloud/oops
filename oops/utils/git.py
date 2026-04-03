# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: git.py — oops/utils/git.py

from pathlib import Path, PurePosixPath

import click
from git import GitCommandError, InvalidGitRepositoryError, Repo, Submodule
from git.config import GitConfigParser

from oops.core.messages import commit_messages
from oops.core.paths import PR_DIR
from oops.utils.compat import Optional
from oops.utils.render import print_success, print_warning


def read_gitmodules(repo: Repo) -> GitConfigParser:
    """Read the .gitmodules file of the given repository."""

    if repo.working_tree_dir is None:
        raise ValueError("Repository does not have a working tree directory")

    gitmodules_path = Path(repo.working_tree_dir) / ".gitmodules"
    cfg = GitConfigParser(str(gitmodules_path), read_only=False)

    return cfg


def is_pull_request(submodule: Submodule) -> bool:
    """Determine whether a submodule is a pull request based on its path or name."""

    for raw in (submodule.path, submodule.name):
        p = PurePosixPath(raw)
        match = p.parts[:1] == (PR_DIR,) or "pr" in p.parts
        if match:
            return True

    return False


def get_local_repo() -> "tuple[Repo, Path]":
    """Return the local git repo and its working tree root."""

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
    """
    Show the diff between remote files (tmpdir) and local files.
    Returns True if at least one file differs.
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
    """Stage the synced files and create a commit."""

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
    """Get the SHA of a submodule at a given ref (commit-ish)."""
    try:
        return repo.git.rev_parse(f"{ref}:{path}")
    except Exception:
        return None
