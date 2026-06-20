# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manage.py — src/oops/commands/pr/manage.py

""" """

import os
import shutil
from pathlib import Path

from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import AppAbort, EarlyExit
from oops.core.logger import live_progress
from oops.core.models import Result, Rows
from oops.io.file import desired_path, get_symlink_map, rewrite_symlink
from oops.output.helper import render_and_raise, render_plan
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, prompt_choices, prompt_confirm


@command("manage", help=__doc__)
def main():  # noqa: C901

    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    available = {sub.name for sub in submodules}
    pull_requests = {sub.name for sub in submodules if is_pull_request(sub)}

    selected = prompt_choices("Select pull request(s): ", available, pull_requests)
    if not selected:
        raise AppAbort()

    # PR downgraded to a regular submodule
    marked_as_sub = pull_requests - selected

    # Regular submodule marked as a PR
    marked_as_pr = selected - pull_requests

    names = set(marked_as_sub.union(marked_as_pr))

    if not names:
        raise EarlyExit()

    mapping = get_symlink_map(repo_path)

    # Planning pass: compute renames + path rewrites without executing
    actions = []  # (old_name, new_name, old_path, new_path, mark_as_pr)
    for submodule in submodules:
        if submodule.name not in names:
            continue
        pull_request = submodule.name in marked_as_pr
        first_symlink = mapping.get(submodule.path) if pull_request else None
        new_name = desired_path(submodule.url, pull_request=pull_request, suffix=first_symlink)
        new_path = desired_path(
            submodule.url,
            prefix=str(config.submodules.current_path),
            pull_request=pull_request,
            suffix=first_symlink,
        )
        if submodule.name != new_name:
            actions.append((submodule.name, new_name, str(submodule.path), str(new_path), pull_request))

    if not actions:
        raise EarlyExit()

    promoted = sum(1 for *_, as_pr in actions if as_pr)
    render_plan(
        "Planned renames + rewrites",
        [
            ("From", "dim", "left"),
            ("To", "brand.primary", "left"),
            ("New Path", "dim", "left"),
            ("Direction", "dim", "right"),
        ],
        [
            [old, new, new_path, colorize("→ PR", "green") if as_pr else colorize("→ regular", "yellow")]
            for old, new, _, new_path, as_pr in actions
        ],
        {"total": len(actions), "promoted": promoted, "demoted": len(actions) - promoted},
    )

    if not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    result: Result[Rows] = Result()
    result.data = Rows(
        title="Renames + Rewrites",
        columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": len(actions), "success": 0, "failed": 0},
    )
    outer: Result[None] = Result()

    moved = []
    for old_name, new_name, old_path, new_path, _ in actions:
        sub = next(s for s in submodules if s.name == old_name)
        try:
            sub.rename(new_name)
            if old_path != new_path:
                sub.move(new_path)
                moved.append((old_path, new_path))
            result.data.rows.append([old_name, colorize("renamed + moved", "green")])
            result.data.metrics["success"] += 1
        except Exception as err:
            outer.add_error(f"{old_name}: {err}")
            result.data.rows.append([old_name, colorize("failed", "red")])
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

    # move() stages .gitmodules; stage it explicitly to also capture rename() changes.
    repo.index.add([".gitmodules"])
    outer.merge(commit_v2(repo, repo_path, [], "pr_manage", skip_hooks=True, already_staged=True))

    render_and_raise(result, outer)
