# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: rewrite.py — oops/commands/submodules/rewrite.py

"""
Move submodule paths under a canonical base directory and update symlinks.

Computes the target path for each submodule under the base directory (default:
.third-party), moves the submodule, and rewrites all symlinks that referenced
the old path. Prompts for confirmation unless --force is used.
"""

from __future__ import annotations

import os
import shutil
from collections import Counter
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort, EarlyExit
from oops.core.logger import live_progress
from oops.core.models import Result, Rows
from oops.io.file import desired_path, get_symlink_map, rewrite_symlink
from oops.output.helper import render_and_raise, render_plan
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, conclude, prompt_choices, prompt_confirm


@command(name="rewrite", help=__doc__)
@click.option(
    "--base-dir",
    default=lambda: config.submodules.current_path,
    help="Base directory for rewritten paths (default: .third-party)",
)
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end")
@click.argument("names", nargs=-1, required=False)
def main(base_dir, force, no_commit, names):  # noqa: C901, PLR0912
    repo, repo_path = require_repository()
    submodules = require_submodules(repo)
    mapping = get_symlink_map(repo_path)

    # Build plan for ALL submodules with status
    plan = []
    for submodule in submodules:
        if not submodule.url or submodule.path not in mapping:
            plan.append([submodule.name, str(submodule.path), "", "skipped"])
            continue
        pull_request = is_pull_request(submodule)
        first_symlink = mapping[submodule.path] if pull_request else None
        target = desired_path(
            submodule.url, prefix=base_dir, pull_request=pull_request, suffix=first_symlink
        )
        if str(submodule.path) != str(target):
            plan.append([submodule.name, str(submodule.path), str(target), "available"])
        else:
            plan.append([submodule.name, str(submodule.path), "", "nothing to do"])

    available = {item[0] for item in plan if item[-1] == "available"}

    # If a list of names has been provided, restrict selection to that list
    if names:
        available = available.intersection(set(names))

    if not available:
        conclude(True, "No submodule needs rewriting.")
        raise EarlyExit()

    # Selection. --force selects all non-interactively.
    if not force:
        selected = prompt_choices("Select submodule(s) to rewrite: ", available, available)
        if not selected:
            raise AppAbort()
    else:
        selected = available

    # Update plan with user's choices
    for item in plan:
        if item[0] in selected:
            item[-1] = "rewrite"
        elif item[-1] == "available":
            item[-1] = "skipped"

    counter = Counter(item[-1] for item in plan)

    if not counter["rewrite"]:
        conclude(True, "Nothing accepted.")
        raise EarlyExit()

    render_plan(
        "Planned rewrites",
        [("Name", "brand.primary", "left"), ("From", "dim", "left"), ("To", "dim", "left"), ("Action", "dim", "left")],
        [[name, frm, to, action] for name, frm, to, action in plan],
        counter,
    )

    if not force and not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    result: Result[Rows] = Result()
    result.data = Rows(
        title="Rewrites",
        columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": len(plan), "success": 0, "failed": 0, "skipped": 0},
    )
    outer: Result[None] = Result()

    # Execution: move submodules and record which paths moved.
    moved = []
    for name, old_path, target, action in plan:
        if action != "rewrite":
            continue
        sub = next(s for s in repo.submodules if s.name == name)
        try:
            sub.move(target)
            moved.append((old_path, target))
            result.data.rows.append([name, colorize("moved", "green")])
            result.data.metrics["success"] += 1
        except Exception as err:
            outer.add_error(f"{name}: {err}")
            result.data.rows.append([name, colorize("failed", "red")])
            result.data.metrics["failed"] += 1

    # Rewrite symlinks that referenced moved paths.
    rewrites = 0
    with live_progress("Rewriting symlinks..."):
        for root, dirs, files in os.walk(repo.working_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for fname in dirs + files:
                p = Path(root) / fname
                if p.is_symlink():
                    for oldp, newp in moved:
                        if rewrite_symlink(p, oldp, newp):
                            rewrites += 1
                            repo.index.add([str(p)])
                            break
    outer.add_message(f"Symlinks rewritten: {rewrites}")

    # Remove old base dir if it still exists.
    if config.submodules.old_paths[0].exists():
        shutil.rmtree(config.submodules.old_paths[0])
        repo.index.remove([str(config.submodules.old_paths[0])], r=True, f=True)
        outer.add_message(f"Removed old submodule base dir: {config.submodules.old_paths[0]}")

    if not no_commit and repo.index.diff(repo.head.commit):
        outer.merge(
            commit_v2(repo, repo_path, [], "submodules_rewrite", skip_hooks=True, already_staged=True)
        )
    elif no_commit:
        outer.add_warning("Changes staged but not committed (--no-commit).")

    render_and_raise(result, outer)
