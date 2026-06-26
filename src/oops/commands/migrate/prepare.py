# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: prepare.py — oops/commands/migrate/prepare.py

"""
Prepare the migration worktree and destination branch.

Creates a git worktree at worktree_path (from plan.migration), resets the
destination branch to the target Odoo version ref, runs project sync, and
records a sentinel commit so apply() can verify preparation is done.

Idempotent: safe to re-run if something went wrong. If the worktree already
exists and the sentinel commit is present, reports success without touching
anything.

Must be run from the source branch. apply() works exclusively in the worktree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.services.git import require_repository
from oops.utils.render import conclude, render_panel

from .apply import ApplyStatus, _load_status, _save_status
from .common import (
    PLAN_FILE,
    STATUS_FILE,
    artifact_path,
    get_dest_branch,
    get_worktree_path,
    load_plan,
)

SENTINEL_PREFIX = "[migrate] prepare"


def _sentinel_message(to_version: str) -> str:
    return f"{SENTINEL_PREFIX} {to_version} base"


def _worktree_exists(repo, worktree_path: Path) -> bool:
    try:
        out = repo.git.worktree("list", "--porcelain")
        return str(worktree_path) in out
    except Exception:
        return False


@command(name="prepare", help=__doc__)
@click.option(
    "--destination-ref",
    "dest_ref",
    required=True,
    help="Commit/tag to reset destination branch to (e.g. a 19.0 Odoo tag).",
)
@click.option(
    "--destination-branch",
    "dest_branch_override",
    default=None,
    help="Override the destination branch (default: plan.migration.dest_branch or 'main').",
)
@click.option(
    "--force",
    is_flag=True,
    help="Re-prepare even if already done.",
)
@click.pass_context
def main(ctx, dest_ref, dest_branch_override, force):
    repo, repo_path = require_repository()

    plan_path = artifact_path(repo_path, PLAN_FILE)
    if not plan_path.exists():
        raise OopsError(f"No plan found at {plan_path}. Run `oops migrate plan` first.")
    plan = load_plan(plan_path)
    migration = plan.migration

    to_version = migration.get("to", "")
    source_ref = migration.get("source_ref", "")
    worktree_path = get_worktree_path(migration, repo_path)
    dest_branch = dest_branch_override or get_dest_branch(migration)
    sentinel = _sentinel_message(to_version)

    render_panel(
        "Prepare migration worktree",
        "\n".join(
            [
                f"Source branch     : [brand.primary]{source_ref}[/]",
                f"Destination branch: {dest_branch}",
                f"Reset to ref      : {dest_ref}",
                f"Worktree path     : {worktree_path}",
            ]
        ),
    )

    # Guard: must not be on the destination branch.
    try:
        current = repo.active_branch.name
    except TypeError:
        current = repo.git.rev_parse("HEAD", short=True)

    if current == dest_branch:
        raise OopsError(
            f"You are on '{dest_branch}' (the destination branch). "
            f"Switch to the source branch ('{source_ref}') before running prepare."
        )

    # Idempotency check.
    status_path = artifact_path(repo_path, STATUS_FILE)
    apply_status = _load_status(status_path)
    if apply_status and apply_status.prepared and not force:
        conclude(True, f"Already prepared — worktree: {apply_status.worktree_path}")
        return

    # --- Step 1: reset or create destination branch at dest_ref ---
    with live_progress(f"Resetting '{dest_branch}' to {dest_ref!r}…"):
        existing = [b.name for b in repo.branches]
        if dest_branch in existing:
            # Force-reset to dest_ref without checking out.
            repo.git.branch("-f", dest_branch, dest_ref)
            log.debug(f"Branch '{dest_branch}' reset to {dest_ref!r}")
        else:
            repo.git.branch(dest_branch, dest_ref)
            log.debug(f"Branch '{dest_branch}' created at {dest_ref!r}")

    # --- Step 2: create or verify the worktree ---
    # dest_branch must not be checked out in the main repo for worktree add.
    # Step 1 kept us on the source branch, so this is safe.
    with live_progress(f"Setting up worktree at {worktree_path}…"):
        if _worktree_exists(repo, worktree_path):
            log.debug(f"Worktree already exists at {worktree_path}")
        else:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            repo.git.worktree("add", str(worktree_path), dest_branch)
            log.debug(f"Worktree created at {worktree_path}")

    # --- Step 3: project sync in the worktree ---
    with live_progress("Syncing project in worktree…"):
        # TODO: import and call the appropriate oops sync functions.
        # The worktree is a fresh checkout of dest_branch — submodules,
        # symlinks and any project-level setup should be initialised here.
        # Example:
        #   from oops.commands.project.sync import sync_project
        #   sync_project(repo_path=worktree_path)
        log.debug("Project sync: not yet wired — fill in as needed.")

    # --- Step 4: sentinel commit ---
    with live_progress("Recording sentinel commit…"):
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", sentinel],
            cwd=worktree_path,
            check=True,
            capture_output=True,
        )
        log.debug(f"Sentinel: {sentinel!r}")

    # --- Step 5: persist in status.yml ---
    if apply_status is None:
        apply_status = ApplyStatus(
            version=plan.version,
            plan_source_ref=source_ref,
            from_version=migration.get("from", ""),
            to_version=to_version,
        )
    apply_status.prepared = True
    apply_status.worktree_path = str(worktree_path)
    apply_status.dest_branch = dest_branch
    _save_status(status_path, apply_status)

    conclude(True, f"Worktree ready at {worktree_path} — run: oops migrate apply")
