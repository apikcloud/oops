# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: git.py — oops/utils/git.py

"""Subprocess-based git helpers for managing external repository checkouts."""

import subprocess
from pathlib import Path

import click
from oops.core.compat import Optional
from oops.core.exceptions import APIError


def _git(*args: str, cwd: Optional[Path] = None, quiet: bool = False) -> None:
    """Run a git command, streaming output to the terminal.

    Args:
        *args: Arguments passed verbatim to git.
        cwd: Working directory for the command. Defaults to None (inherit).
        quiet: Suppress stdout/stderr (e.g. when inside a Rich Live context).
    """
    sink = subprocess.DEVNULL if quiet else None
    subprocess.run(["git", *args], check=True, cwd=cwd, stdout=sink, stderr=sink)


def _git_output(*args: str, cwd: Optional[Path] = None) -> str:
    """Run a git command and return its stdout as a stripped string.

    Args:
        *args: Arguments passed verbatim to git.
        cwd: Working directory for the command. Defaults to None (inherit).

    Returns:
        Stripped stdout of the git command.
    """
    result = subprocess.run(
        ["git", *args],
        check=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def clone(url: str, dest: Path, branch: str, quiet: bool = False) -> None:
    """Shallow-clone a git repository to a local destination.

    Args:
        url: Remote URL to clone from.
        dest: Local path where the repository will be created.
        branch: Branch name to check out.
        quiet: Suppress git stdout/stderr.
    """
    _git(
        "clone",
        url,
        "--branch",
        branch,
        "--depth",
        "1",
        "--single-branch",
        str(dest),
        quiet=quiet,
    )


def update_latest(dest: Path, quiet: bool = False) -> None:
    """Fetch and reset to the tip of the remote branch (shallow).

    Args:
        dest: Local repository path to update.
        quiet: Suppress git stdout/stderr.
    """
    _git("fetch", "--depth", "1", cwd=dest, quiet=quiet)
    _git("reset", "--hard", "FETCH_HEAD", cwd=dest, quiet=quiet)


def repo_info(path: Path) -> str:
    """Return a short commit summary for a git repo, or an empty string.

    Args:
        path: Path to a local git repository.

    Returns:
        String of the form ``<hash>  <date>`` or empty string if unavailable.
    """
    if not path.exists():
        return ""
    try:
        return _git_output("log", "-1", "--format=%h  %ai", cwd=path) or ""
    except subprocess.CalledProcessError:
        return ""


def update_at_date(dest: Path, date: str, quiet: bool = False) -> None:
    """Fetch history back to *date* and checkout the last commit before it.

    The result is a detached HEAD pointing at the latest commit whose author
    date is ≤ DATE 23:59:59.

    Args:
        dest: Local repository path to update.
        date: Target date in YYYY-MM-DD format.
        quiet: Suppress git stdout/stderr.

    Raises:
        click.ClickException: If no commit is found at or before *date*.
    """
    _git("fetch", "--shallow-since", date, cwd=dest, quiet=quiet)

    commit = _git_output(
        "rev-list",
        "-1",
        f"--before={date} 23:59:59",
        "FETCH_HEAD",
        cwd=dest,
    )

    if not commit:
        raise APIError(
            f"No commit found at or before {date} in '{dest}'. "
            "Try an earlier date or check that the branch has history that far back."
        )

    if not quiet:
        click.echo(f"  Checking out {commit[:12]}  (last commit ≤ {date})")
    _git("checkout", commit, cwd=dest, quiet=quiet)
