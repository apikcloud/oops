# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: prune.py — oops/commands/submodules/prune.py

"""
Remove submodules that are not referenced by any symlink.

Iterates over all submodules, checks whether any symlink in the repository
points to the submodule path, and removes those that are unused. Specific
submodules can be targeted by passing their names as arguments.

When called without arguments, displays an interactive selection menu of
unused submodules.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Tuple
from oops.core.logger import live_progress, log
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import list_symlinks, relpath
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository, require_submodules
from oops.utils.render import colorize


def _is_used(repo_path: Path, path: Path, symlinks: list) -> bool:
    rel = relpath(repo_path, path)
    return any(rel in t for t in symlinks)


def _build_plan(submodules, repo_path: Path, symlinks: list) -> Plan:
    actions = []
    for sub in submodules:
        log.info(f"Checking {sub.name}")
        path = repo_path / Path(sub.path)
        if not _is_used(repo_path, path, symlinks):
            actions.append(
                PlanAction(
                    label=sub.name,
                    new=None,
                    detail=str(sub.path),
                    kind="available",
                )
            )
    return Plan(title="Unused submodules", actions=actions)


@command(name="prune", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.argument("names", nargs=-1, required=False)
def main(no_commit: bool, force: bool, names: Tuple[str, ...]):
    repo, repo_path = require_repository()
    submodules = require_submodules(repo)

    symlinks = list_symlinks(repo_path)

    with live_progress("Looking for unused submodules..."):
        plan = _build_plan(submodules, repo_path, symlinks)

    if names:
        plan.restrict_to(set(names))

    sub_map = {s.name: s for s in submodules}

    def apply(action: PlanAction) -> Tuple[str, bool]:
        sub_map[action.label].remove(force=True)
        return colorize("removed", "red"), True

    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Pruned",
        force=force,
        select_prompt="Select submodule(s) to prune: ",
        empty_message="No unused submodules detected.",
    )

    if not no_commit:
        outer.merge(
            commit_v2(repo, repo_path, [], "submodules_prune", skip_hooks=True, already_staged=True)
        )
    else:
        outer.add_warning("Don't forget to commit to share changes with the team.")

    render_and_raise(result, outer)
