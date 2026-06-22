# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: add.py — oops/commands/addons/add.py
"""
Create root-level symlinks for addons found in tracked submodules.

Searches all submodules for addons matching the provided names and creates
symlinks at the repository root. Skips addons that are already present.
If no names are given, opens an interactive picker over all available addons.
"""

import os
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Optional, Tuple
from oops.core.exceptions import NotFoundError
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import relpath
from oops.io.manifest import find_addons_extended
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, list_available_addons, require_repository
from oops.utils.render import colorize


def _build_plan(names: Optional[set], available: dict, existing: set) -> Plan:
    """Build addon symlink plan as pure data.

    If `names` is None, all available-but-not-linked addons are candidates.
    """
    candidates = names if names is not None else set(available.keys()) - existing
    actions = []
    for name in sorted(candidates):
        if name in existing:
            actions.append(PlanAction(label=name, kind="nothing to do", detail="already linked"))
        elif name in available:
            actions.append(PlanAction(label=name, kind="available", data={"path": str(available[name])}))
        else:
            actions.append(PlanAction(label=name, kind="skipped", detail="not found in any submodule"))
    return Plan(title="Addons to link", actions=actions)


@command("add", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit created symlinks.")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting.")
@click.argument("names", nargs=-1, required=False)
def main(names: Tuple[str, ...], no_commit: bool, force: bool) -> None:
    repo, repo_path = require_repository()

    existing = {name for name, _, _ in find_addons_extended(repo_path)}
    available: dict = {name: path for name, path, _ in list_available_addons(repo, repo_path)}

    requested: Optional[set] = set(names) if names else None

    # 1. Build the plan (pure business logic)
    plan = _build_plan(requested, available, existing)

    if requested is not None:
        not_found = {a.label for a in plan.actions if a.kind == "skipped"}
        if not_found:
            raise NotFoundError(f"Addon(s) not found in any submodule: {', '.join(sorted(not_found))}")

    # 2. Define how to execute one action
    created: list[str] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        link = repo_path / action.label
        if link.exists() or link.is_symlink():
            return colorize("skipped (exists)", "yellow"), False
        os.symlink(relpath(repo_path, Path(action.data["path"])), link)
        created.append(action.label)
        return colorize("linked", "green"), True

    # 3. Run the shared scenario (select → present → confirm → apply)
    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Linked addons",
        force=force,
        select=requested is None,
        select_prompt="Select addon(s) to link: ",
        empty_message="No addons available to link.",
    )

    # 4. Command-specific side effect: commit
    if created and not no_commit:
        outer.merge(commit_v2(repo, repo_path, created, "addons_new", skip_hooks=True))
    elif created:
        outer.add_warning("Don't forget to commit the symlinks.")

    # 5. Final render (after commit), non-zero exit on errors
    render_and_raise(result, outer)
