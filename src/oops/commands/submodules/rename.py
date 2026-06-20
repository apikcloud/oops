# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: rename.py — oops/commands/submodules/rename.py

"""
Rename submodules to match the <ORG>/<REPO> naming convention.

Computes the canonical name from the submodule URL and renames it if it
differs. Prompts for confirmation on each change unless --no-prompt is passed.
Specific submodules can be targeted by name.
"""

from collections import Counter

import click
from oops.commands.base import command
from oops.core.exceptions import AppAbort, EarlyExit
from oops.core.models import Result, Rows
from oops.io.file import desired_path, get_symlink_map
from oops.output.helper import render_and_raise, render_plan
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize, conclude, prompt_choices, prompt_confirm


@command("rename", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.argument("names", nargs=-1, required=False)
def main(no_commit, force, names):
    repo, repo_path = require_repository()
    submodules = require_submodules(repo)
    mapping = get_symlink_map(repo_path)

    # First step: list the submodules that can be renamed. If the list is empty, exit.
    plan = []
    for submodule in submodules:
        pull_request = is_pull_request(submodule)
        first_symlink = mapping.get(submodule.path) if pull_request else None
        new_name = desired_path(submodule.url, pull_request=pull_request, suffix=first_symlink)
        if submodule.name != new_name:
            plan.append([submodule.name, new_name, pull_request, "available"])
        else:
            plan.append([submodule.name, "", pull_request, "nothing to do"])

    available = {item[0] for item in plan if item[-1] == "available"}

    # If a list of names has been provided, the selection is restricted to that list
    if names:
        available = available.intersection(set(names))

    if not available:
        conclude(True, "Nothing to rename.")
        raise EarlyExit()

    # Selection. --no-prompt selects all non-interactively.
    if not names and not force:
        selected = prompt_choices("Select submodule(s) to rename: ", available, available)
        if not selected:
            raise AppAbort()
    else:
        selected = available

    # We update the plan with the user’s choices
    for item in plan:
        if item[0] in selected:
            item[-1] = "rename"
        elif item[-1] == "available":
            item[-1] = "skipped"

    counter = Counter(item[-1] for item in plan)

    if not counter["rename"]:
        conclude(True, "Nothing to rename.")
        raise EarlyExit()

    # Presentation of the plan and user approval
    render_plan(
        "Planned renames",
        [("From", "dim", "left"), ("To", "brand.primary", "left"), ("Kind", "dim", "right"), ("Action", "dim", "left")],
        [
            [old, new, colorize("PR", "green") if pr else colorize("regular", "yellow"), action]
            for old, new, pr, action in plan
        ],
        counter,
    )

    if not force and not prompt_confirm("Proceed?", default=True):
        raise AppAbort()

    result: Result[Rows] = Result()
    result.data = Rows(
        title="Renames",
        columns=[("Name", "brand.primary", "left"), ("Status", "dim", "center")],
        rows=[],
        metrics={"total": len(plan), "success": 0, "failed": 0},
    )
    outer: Result[None] = Result()

    # Implementation of the plan and results
    for old, new, _, action in plan:
        if action == "skipped":
            continue
        sub = next(s for s in repo.submodules if s.name == old)
        try:
            sub.rename(new)
            result.data.rows.append([old, colorize("renamed", "green")])
            result.data.metrics["success"] += 1
        except Exception as err:
            outer.add_error(f"{old}: {err}")
            result.data.rows.append([old, colorize("failed", "red")])
            result.data.metrics["failed"] += 1

    if not no_commit:
        outer.merge(commit_v2(repo, repo_path, [".gitmodules"], "submodules_rename", skip_hooks=True))
    else:
        outer.add_warning("Don't forget to commit .gitmodules to share changes with the team.")

    render_and_raise(result, outer)
