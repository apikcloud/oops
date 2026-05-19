"""
Synchronise files from a remote repository (no parent relationship).

Flow:
    1. Sparse-clone the remote repo into a temporary directory
    2. Show a diff against the local repo
    3. Apply changes and create a commit (with confirmation)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort, ConfigError
from oops.services.git import commit, require_repository, show_diff
from oops.services.project import copy_project_files, fetch_project_files
from oops.utils.render import conclude, get_console, print_success, prompt_confirm, rule
from rich.live import Live
from rich.spinner import Spinner


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
        raise ConfigError("sync.remote_url is not configured. Set it in ~/.oops.yaml or .oops.yaml.")

    if not resolved_files:
        raise ConfigError("sync.files is empty. List the files to sync in ~/.oops.yaml or .oops.yaml.")

    local_repo, repo_path = require_repository()
    console = get_console()

    rule(f"Sync from {remote_url}")

    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = Path(_tmpdir)

        with Live(Spinner("dots", text=f"Cloning {remote_url} …"), refresh_per_second=10):
            fetch_project_files(remote_url, resolved_branch, resolved_files, tmpdir)

        has_changes = show_diff(tmpdir, resolved_files, local_repo, repo_path)

        if not has_changes:
            conclude(True, "Already up to date.")
            return

        if dry_run:
            conclude(True, "Finished dry run.")
            return

        if not force and not prompt_confirm("Apply these changes?", default=False):
            raise AppAbort()

        applied = copy_project_files(tmpdir, resolved_files, repo_path)

    for f in applied:
        console.print(f"  [green]✓[/] {f}")

    if applied:
        commit(local_repo, repo_path, applied, "project_sync")
    else:
        print_success("Nothing to copy (all listed files absent from remote).")

    conclude(True, "Sync complete")
