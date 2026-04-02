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

from oops.core.config import config
from oops.utils.git import commit, get_local_repo, show_diff
from oops.utils.net import sparse_clone

# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("sync")
@click.option("--dry-run", is_flag=True, help="Show the diff without applying changes.")
@click.option("--force", "-f", is_flag=True, help="Apply changes without asking for confirmation.")
def main(dry_run: bool, force: bool) -> None:
    """Synchronise files from the configured remote repository."""

    remote_url = config.sync.remote_url
    files = config.sync.files

    if not remote_url:
        raise click.ClickException(
            "sync.remote_url is not configured. Set it in ~/.oops.yaml or .oops.yaml."
        )

    if not files:
        raise click.ClickException(
            "sync.files is empty. List the files to sync in ~/.oops.yaml or .oops.yaml."
        )

    # Resolve the local repo once — fail fast if not inside a git repository.
    local_repo, repo_root = get_local_repo()

    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = Path(_tmpdir)

        # 1. FETCH
        click.echo(f"↓ Cloning {remote_url} …")
        try:
            sparse_clone(remote_url, tmpdir, files)
        except git.GitCommandError as exc:
            raise click.ClickException(f"Clone failed: {exc.stderr.strip()}") from exc

        # 2. DIFF
        click.echo("")
        has_changes = show_diff(tmpdir, files, local_repo, repo_root)

        if not has_changes:
            click.echo(click.style("✓ Already up to date.", fg="green"))
            return

        if dry_run:
            click.echo(click.style("\n[dry-run] No changes applied.", fg="yellow"))
            return

        # 3. APPLY + COMMIT
        click.echo("")
        if not force:
            click.confirm("Apply these changes?", abort=True)

        _apply(tmpdir, files, repo_root)
        commit(local_repo, repo_root, files, "project_sync")


def _apply(tmpdir: Path, files: list, repo_root: Path) -> None:
    """Copy files/directories from tmpdir into the local repo."""
    for f in files:
        src = tmpdir / f
        dst = repo_root / f

        if not src.exists():
            continue

        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        click.echo(f"  ✓ {f}")
