"""
oops sync — Synchronise files from a remote repository (no parent relationship).

Flow:
    1. Sparse-clone the remote repo into a temporary directory
    2. Show a diff against the local repo
    3. Apply changes and create a commit (with confirmation)

Usage:
    oops sync
    oops sync --dry-run
    oops sync --yes
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import click
import git

from oops.core.config import config
from oops.core.messages import commit_messages

# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("sync")
@click.option("--dry-run", is_flag=True, help="Show the diff without applying changes.")
@click.option("--yes", "-y", is_flag=True, help="Apply without asking for confirmation.")
def main(dry_run: bool, yes: bool) -> None:
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

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. FETCH
        click.echo(f"↓ Cloning {remote_url} …")
        try:
            _fetch(remote_url, tmpdir, files)
        except git.GitCommandError as exc:
            raise click.ClickException(f"Clone failed: {exc.stderr.strip()}") from exc

        # 2. DIFF
        click.echo("")
        has_changes = _show_diff(Path(tmpdir), files)

        if not has_changes:
            click.echo(click.style("✓ Already up to date.", fg="green"))
            return

        if dry_run:
            click.echo(click.style("\n[dry-run] No changes applied.", fg="yellow"))
            return

        # 3. APPLY + COMMIT
        click.echo("")
        if not yes:
            click.confirm("Apply these changes?", abort=True)

        _apply(Path(tmpdir), files)

        local_repo = git.Repo(Path.cwd(), search_parent_directories=True)
        repo_root = Path(local_repo.working_tree_dir)

        local_repo.index.add([str(repo_root / f) for f in files])

        if not local_repo.index.diff("HEAD"):
            click.echo(click.style("⚠ Nothing to commit (index identical to HEAD).", fg="yellow"))
            return

        commit = local_repo.index.commit(commit_messages.project_sync)
        click.echo(
            click.style(
                f"\n✓ Commit {commit.hexsha[:8]} — {commit_messages.project_sync}", fg="green"
            )
        )


# ---------------------------------------------------------------------------
# 1. Fetch — sparse clone of the remote repo
# ---------------------------------------------------------------------------


def _fetch(remote_url: str, tmpdir: str, files: list[str]) -> None:
    """Clone only the listed files/directories (sparse checkout, depth=1)."""
    remote_repo = git.Repo.clone_from(
        remote_url,
        tmpdir,
        depth=1,
        no_checkout=True,
    )

    # Enable sparse checkout
    with remote_repo.config_writer() as cw:
        cw.set_value("core", "sparseCheckout", True)

    # Write the list of patterns to .git/info/sparse-checkout
    sparse_file = Path(tmpdir) / ".git" / "info" / "sparse-checkout"
    sparse_file.write_text("\n".join(files) + "\n", encoding="utf-8")

    # Perform the actual checkout
    remote_repo.git.checkout("HEAD")


# ---------------------------------------------------------------------------
# 2. Diff — show differences before applying
# ---------------------------------------------------------------------------


def _show_diff(tmpdir: Path, files: list[str]) -> bool:
    """
    Show the diff between remote files (tmpdir) and local files.
    Returns True if at least one file differs.
    """
    local_repo = git.Repo(Path.cwd(), search_parent_directories=True)
    repo_root = Path(local_repo.working_tree_dir)
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
            diff_output = local_repo.git.diff(
                "--no-index",
                "--color",
                str(dst),
                str(src),
            )
            # No exception = exit code 0 = no differences
        except git.GitCommandError as exc:
            # Exit code 1 = differences found; stdout contains the diff
            diff_output = exc.stdout

        if diff_output:
            click.echo(diff_output)
            has_changes = True

    return has_changes


# ---------------------------------------------------------------------------
# 3. Apply — copy remote files into the local repo
# ---------------------------------------------------------------------------


def _apply(tmpdir: Path, files: list[str]) -> None:
    """Copy files/directories from tmpdir into the local repo."""
    local_repo = git.Repo(Path.cwd(), search_parent_directories=True)
    repo_root = Path(local_repo.working_tree_dir)

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
