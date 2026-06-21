# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: replace.py — oops/commands/submodules/replace.py

"""
Replace one or more submodules with a new repository.

Removes the named submodules, adds the new repository as a submodule, and
rewrites any symlinks that pointed to the old paths to point to the new one.

When called without submodule names, displays an interactive selection menu.
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.core.compat import Tuple
from oops.core.config import config
from oops.core.exceptions import NotFoundError
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import desired_path, rewrite_symlinks
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository, require_submodules
from oops.utils.net import encode_url
from oops.utils.render import colorize


def _build_plan(submodules, new_name: str, branch: str) -> Plan:
    actions = []
    for sub in submodules:
        actions.append(
            PlanAction(
                label=sub.name,
                new=new_name,
                detail=branch,
                kind="available",
            )
        )
    return Plan(title="Planned replacements", actions=actions)


@command("replace", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.argument("names", nargs=-1, required=False)
@click.argument("url")
@click.argument("branch")
def main(
    no_commit: bool,
    force: bool,
    names: Tuple[str, ...],
    url: str,
    branch: str,
):
    repo, repo_path = require_repository()
    submodules = list(require_submodules(repo))

    if names:
        name_set = {s.name for s in submodules}
        not_found = [n for n in names if n not in name_set]
        if not_found:
            raise NotFoundError(f"Submodule(s) not found: {', '.join(not_found)}")

    new_url = encode_url(url, config.submodules.force_scheme)
    new_name = desired_path(new_url, pull_request=False)
    new_path = desired_path(new_url, pull_request=False, prefix=str(config.submodules.current_path))

    plan = _build_plan(submodules, new_name, branch)

    if names:
        plan.restrict_to(set(names))

    sub_map = {s.name: s for s in submodules}
    old_paths: list[str] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        sub = sub_map[action.label]
        old_path = str(sub.path)
        sub.remove(force=True)
        old_paths.append(old_path)
        return colorize("removed", "red"), True

    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Replacements",
        force=force,
        select_prompt="Select submodule(s) to replace: ",
        empty_message="Nothing to replace.",
    )

    # Add the new submodule (or update branch if it already exists)
    if new_name not in repo.submodules:
        repo.git.submodule("add", "--name", new_name, "-b", branch, new_url, new_path)
        actual_new_path = new_path
    else:
        actual_new_path = str(repo.submodules[new_name].path)
        if branch != repo.submodules[new_name].branch:
            repo.git.config(f"submodule.{new_name}.branch", branch)

    # Rewrite symlinks pointing to removed submodule paths
    moved = [(old_path, actual_new_path) for old_path in old_paths]
    rewrites = rewrite_symlinks(repo, moved)
    outer.add_message(f"Symlinks rewritten: {rewrites}")

    if not no_commit:
        removed = [a.label for a in plan.actionable]
        description = "\n".join(
            f"- replaced '{n}' with '{new_name}' (branch={branch})" for n in removed
        )
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                [],
                "submodules_replace",
                description=description,
                skip_hooks=True,
                already_staged=True,
            )
        )
    else:
        outer.add_warning("Don't forget to commit to share changes with the team.")

    render_and_raise(result, outer)
