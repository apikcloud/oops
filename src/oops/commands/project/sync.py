"""
Synchronise files from a remote repository (no parent relationship).

Flow:
    1. Sparse-clone the remote repo into a temporary directory
    2. Show a diff against the local repo
    3. Apply changes and create a commit (with confirmation)
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import click
import git
from oops.commands.base import command
from oops.core.config import config
from oops.services.git import commit, get_local_repo, show_diff
from oops.utils.net import sparse_clone
from oops.utils.render import print_success

# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@command("sync")
@click.option("--dry-run", is_flag=True, help="Show the diff without applying changes.")
@click.option("--force", "-f", is_flag=True, help="Apply changes without asking for confirmation.")
@click.option("--branch", "-b", default=None, help="Remote branch to sync from (overrides sync.branch).")
@click.option("--files", "-F", multiple=True, help="Files/folders to sync (overrides sync.files, repeatable).")
def main(dry_run: bool, force: bool, branch: str | None, files: tuple) -> None:
    """Synchronise files from the configured remote repository."""

    remote_url = config.sync.remote_url
    resolved_branch = branch or config.sync.branch
    resolved_files: list[str] = list(files) if files else config.sync.files

    if not remote_url:
        raise click.ClickException("sync.remote_url is not configured. Set it in ~/.oops.yaml or .oops.yaml.")

    if not resolved_files:
        raise click.ClickException("sync.files is empty. List the files to sync in ~/.oops.yaml or .oops.yaml.")

    # Resolve the local repo once — fail fast if not inside a git repository.
    local_repo, repo_path = get_local_repo()

    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = Path(_tmpdir)

        # 1. FETCH
        click.echo(f"↓ Cloning {remote_url} …")
        try:
            sparse_clone(remote_url, tmpdir, resolved_files, resolved_branch)
        except git.GitCommandError as exc:
            raise click.ClickException(f"Clone failed: {exc.stderr.strip()}") from exc

        # 2. DIFF
        click.echo("")
        has_changes = show_diff(tmpdir, resolved_files, local_repo, repo_path)

        if not has_changes:
            print_success("Already up to date.")
            raise click.exceptions.Exit(0)

        if dry_run:
            print_success("Finished dry run.")
            raise click.exceptions.Exit(0)

        # 3. APPLY + COMMIT
        click.echo("")
        if not force:
            click.confirm("Apply these changes?", abort=True)

        _apply(tmpdir, resolved_files, repo_path)
        commit(local_repo, repo_path, resolved_files, "project_sync")


def _apply(tmpdir: Path, files: list, repo_path: Path) -> None:
    """Copy files/directories from tmpdir into the local repo."""
    for f in files:
        src = tmpdir / f
        dst = repo_path / f

        if not src.exists():
            continue

        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        click.echo(f"  ✓ {f}")
