# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: rename.py — oops/commands/submodules/rename.py

"""
Rename submodules to match the <ORG>/<REPO> naming convention.

Computes the canonical name from the submodule URL and renames it if it
differs. Displays a plan and prompts for confirmation before applying unless
--force is passed. Specific submodules can be targeted by name.
"""

import click
from oops.commands.base import command
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import desired_path, get_symlink_map
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize
from oops_engine.compat import Tuple


def _build_plan(submodules, mapping) -> Plan:
    """Build the rename plan as pure data — no prompts, no colours."""
    actions = []
    for submodule in submodules:
        pull_request = is_pull_request(submodule)
        first_symlink = mapping.get(submodule.path) if pull_request else None
        new_name = desired_path(submodule.url, pull_request=pull_request, suffix=first_symlink)

        changed = submodule.name != new_name
        actions.append(
            PlanAction(
                label=submodule.name,
                new=new_name if changed else None,
                detail="PR" if pull_request else "regular",
                kind="available" if changed else "nothing to do",
                data={"pr": pull_request, "new_name": new_name},
            )
        )
    return Plan(title="Planned renames", actions=actions)


@command("rename", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.argument("names", nargs=-1, required=False)
def main(no_commit: bool, force: bool, names: Tuple[str, ...]):
    repo, repo_path = require_repository()
    submodules = require_submodules(repo)
    mapping = get_symlink_map(repo_path)

    # 1. Build the plan (pure business logic)
    plan = _build_plan(submodules, mapping)

    # 2. Narrow by CLI names if provided
    if names:
        plan.restrict_to(set(names))

    # 3. Define how to execute one action (pure business logic)
    sub_map = {s.name: s for s in submodules}

    def apply(action: PlanAction) -> Tuple[str, bool]:
        sub = sub_map[action.label]
        sub.rename(action.data["new_name"])
        return colorize("renamed", "green"), True

    # 4. Run the shared scenario (select → present → confirm → apply)
    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Renames",
        force=force,
        select_prompt="Select submodule(s) to rename: ",
        empty_message="Nothing to rename.",
    )

    # 5. Command-specific side effect: commit
    if not no_commit:
        outer.merge(commit_v2(repo, repo_path, [".gitmodules"], "submodules_rename", skip_hooks=True))
    else:
        outer.add_warning("Don't forget to commit .gitmodules to share changes with the team.")

    # 6. Final render (after the commit), non-zero exit on errors
    render_and_raise(result, outer)
