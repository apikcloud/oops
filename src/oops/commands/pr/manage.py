# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manage.py — src/oops/commands/pr/manage.py

""" """

from oops.commands.base import command
from oops.core.exceptions import AppAbort, EarlyExit
from oops.core.models import Result, Rows
from oops.io.file import desired_path, get_symlink_map
from oops.output.helper import render_and_raise, render_plan
from oops.services.git import browse_submodules, commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, prompt_choices, prompt_confirm


@command("manage", help=__doc__)
def main():

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

    names = tuple(marked_as_sub.union(marked_as_pr))

    if not names:
        raise EarlyExit()

    # Assume at most one symlink per submodule
    mapping = get_symlink_map(repo_path)

    def get_new_name(submodule, pull_request: bool) -> str:
        first_symlink = mapping.get(submodule.path) if pull_request else None
        return desired_path(
            submodule.url,
            pull_request=pull_request,
            suffix=first_symlink,
        )

    # Planning pass: compute renames without executing
    actions = []  # list of (old_name, new_name, mark_as_pr)
    for _, submodule in browse_submodules(submodules, names):
        pull_request = submodule.name in marked_as_pr
        new_name = get_new_name(submodule, pull_request)
        if submodule.name != new_name:
            actions.append((submodule.name, new_name, pull_request))

    if not actions:
        raise EarlyExit()

    promoted = sum(1 for *_, as_pr in actions if as_pr)
    render_plan(
        "Planned renames",
        [("From", "dim", "left"), ("To", "brand.primary", "left"), ("Direction", "dim", "right")],
        [
            [old, new, colorize("→ PR", "green") if as_pr else colorize("→ regular", "yellow")]
            for old, new, as_pr in actions
        ],
        {"renames": len(actions), "promoted": promoted, "demoted": len(actions) - promoted},
    )

    if not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    result: Result[Rows] = Result()
    result.data = Rows(
        title="Renames",
        columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": len(actions), "success": 0, "failed": 0},
    )
    outer: Result[None] = Result()

    renames = {old: new for old, new, _ in actions}
    for _, submodule in browse_submodules(submodules, tuple(renames.keys())):
        try:
            submodule.rename(renames[submodule.name])
            result.data.rows.append([submodule.name, colorize("renamed", "green")])
            result.data.metrics["success"] += 1
        except Exception as err:
            outer.add_error(f"{submodule.name}: {err}")
            result.data.rows.append([submodule.name, colorize("failed", "red")])
            result.data.metrics["failed"] += 1

    outer.merge(commit_v2(repo, repo_path, [".gitmodules"], "submodules_rename", skip_hooks=True))

    render_and_raise(result, outer)
