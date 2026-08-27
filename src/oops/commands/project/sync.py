# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: sync.py — oops/commands/project/sync.py

"""
Synchronise files from a remote repository (no parent relationship).

Flow:
    1. Sparse-clone the remote repo into a temporary directory
    2. Show a diff and a plan of files to apply
    3. Apply changes and create a commit (with confirmation)
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import ConfigError, EarlyExit
from oops.core.models import Plan, PlanAction, Result
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository, show_diff
from oops.services.project import fetch_project_files
from oops.utils.render import colorize, conclude, rule
from oops_engine.compat import Tuple
from rich.live import Live
from rich.spinner import Spinner


def _build_plan(tmpdir: Path, files: list, repo_path: Path) -> Plan:
    """Build sync plan from cloned files — pure data, no I/O."""
    actions = []
    for f in files:
        src = tmpdir / f
        if not src.exists():
            actions.append(PlanAction(label=f, kind="skipped", detail="not in remote"))
        else:
            detail = "new" if not (repo_path / f).exists() else "update"
            actions.append(PlanAction(label=f, kind="available", detail=detail))
    return Plan(title="Files to sync", actions=actions)


@command("sync")
@click.option("--no-commit", is_flag=True, help="Do not commit applied changes.")
@click.option("--force", "-f", is_flag=True, help="Apply changes without asking for confirmation.")
@click.option("--branch", "-b", default=None, help="Remote branch to sync from (overrides sync.branch).")
@click.option("--files", "-F", multiple=True, help="Files/folders to sync (overrides sync.files, repeatable).")
def main(no_commit: bool, force: bool, branch: "str | None", files: tuple) -> None:
    """Synchronise files from the configured remote repository."""

    remote_url = config.sync.remote_url
    resolved_branch = branch or config.sync.branch
    resolved_files: list[str] = list(files) if files else list(config.sync.files)

    if not remote_url:
        raise ConfigError("sync.remote_url is not configured. Set it in ~/.oops.yaml or .oops.yaml.")
    if not resolved_files:
        raise ConfigError("sync.files is empty. List the files to sync in ~/.oops.yaml or .oops.yaml.")

    local_repo, repo_path = require_repository()

    rule(f"Sync from {remote_url}")

    with tempfile.TemporaryDirectory() as _tmpdir:
        tmpdir = Path(_tmpdir)

        with Live(Spinner("dots", text=f"Cloning {remote_url} …"), refresh_per_second=10):
            fetch_project_files(remote_url, resolved_branch, resolved_files, tmpdir)

        # Show diff for context; also detects whether there is anything to do.
        has_changes = show_diff(tmpdir, resolved_files, local_repo, repo_path)
        if not has_changes:
            conclude(True, "Already up to date.")
            raise EarlyExit()

        # 1. Build the plan (pure business logic)
        plan = _build_plan(tmpdir, resolved_files, repo_path)

        # 2. Define how to execute one action
        def apply(action: PlanAction) -> Tuple[str, bool]:
            src = tmpdir / action.label
            dst = repo_path / action.label
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return colorize("synced", "green"), True

        # 3. Run the shared scenario (present → confirm → apply)
        outer: Result[None] = Result()
        result = run_mutation_workflow(
            plan=plan,
            apply=apply,
            outer=outer,
            title="Synced files",
            force=force,
            select=False,
            empty_message="Nothing to sync.",
        )

    # 4. Command-specific side effect: commit
    applied = [a.label for a in plan.actionable]
    if applied and not no_commit:
        outer.merge(commit_v2(local_repo, repo_path, applied, "project_sync"))
    elif applied:
        outer.add_warning("Don't forget to commit the synced files.")

    # 5. Final render (after commit), non-zero exit on errors
    render_and_raise(result, outer)
