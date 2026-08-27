# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: remove.py — oops/commands/submodules/remove.py

"""
Remove one or more submodules and their associated symlinks.

When called without arguments, displays an interactive selection menu.
Submodule names can also be passed directly as arguments.

Associated symlinks pointing into the removed submodule paths are removed
automatically. Displays a plan and prompts for confirmation before applying.
"""

from __future__ import annotations

import os
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.models import Plan, PlanAction, Result
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, require_repository, require_submodules
from oops.utils.render import colorize
from oops_engine.compat import Tuple


def _collect_symlinks(repo_path: Path) -> list[Path]:
    result = []
    for root, dirs, files in os.walk(repo_path):
        if ".git" in dirs:
            dirs.remove(".git")
        for entry in dirs + files:
            p = Path(root) / entry
            if p.is_symlink():
                result.append(p)
    return result


def _build_plan(submodules, repo_path: Path) -> Plan:
    all_symlinks = _collect_symlinks(repo_path)
    actions = []
    for sub in submodules:
        sub_rel = os.path.relpath(repo_path / sub.path, repo_path)
        links = [lnk for lnk in all_symlinks if sub_rel in os.readlink(lnk)]
        n = len(links)
        detail = f"{n} symlink{'s' if n != 1 else ''}" if n else str(sub.path)
        actions.append(
            PlanAction(
                label=sub.name,
                new=None,
                detail=detail,
                kind="available",
                data={"links": [str(lnk) for lnk in links]},
            )
        )
    return Plan(title="Planned removals", actions=actions)


@command("remove", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.argument("names", nargs=-1, required=False)
def main(no_commit: bool, force: bool, names: Tuple[str, ...]):
    repo, repo_path = require_repository()
    submodules = list(require_submodules(repo))

    plan = _build_plan(submodules, repo_path)

    if names:
        plan.restrict_to(set(names))

    sub_map = {s.name: s for s in submodules}

    def apply(action: PlanAction) -> Tuple[str, bool]:
        for lnk_str in action.data["links"]:
            lnk = Path(lnk_str)
            rel = os.path.relpath(lnk, repo_path)
            repo.git.rm("--force", "--", rel)
        sub_map[action.label].remove(force=True)
        return colorize("removed", "red"), True

    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Removals",
        force=force,
        select=not names,
        select_prompt="Select submodule(s) to remove: ",
        empty_message="Nothing to remove.",
    )

    if not no_commit:
        removed = [a.label for a in plan.actionable]
        description = "\n".join(f"- {n}" for n in removed)
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                [],
                "submodules_remove",
                description=description,
                skip_hooks=True,
                already_staged=True,
            )
        )
    else:
        outer.add_warning("Don't forget to commit to share changes with the team.")

    render_and_raise(result, outer)
