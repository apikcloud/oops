# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: manage.py — src/oops/commands/addons/manage.py

"""Interactively link or unlink addons from submodules at the repo root."""

import os
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.exceptions import AppAbort, NotFoundError
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import relpath
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, list_available_addons, require_repository, require_submodules
from oops.utils.render import colorize, prompt_choices
from oops_engine.compat import Tuple
from oops_engine.manifest import find_addons_extended


def _build_plan(added: set, removed: set, available: dict) -> Plan:
    """Build addon link/unlink plan as pure data — no prompts, no colours."""
    actions = []
    for name in sorted(added):
        actions.append(
            PlanAction(
                label=name,
                kind="promote",
                detail="link",
                data={"action": "link", "path": str(available[name])},
            )
        )
    for name in sorted(removed):
        actions.append(
            PlanAction(
                label=name,
                kind="demote",
                detail="unlink",
                data={"action": "unlink"},
            )
        )
    return Plan(title="Addon changes", actions=actions)


@command("manage", help=__doc__)
@click.option(
    "--no-commit",
    is_flag=True,
    help="If set, symlink changes will not be committed.",
)
def main(no_commit: bool) -> None:

    repo, repo_path = require_repository()
    require_submodules(repo)

    existing = {name for name, _, _ in find_addons_extended(repo_path)}
    available: dict = {name: path for name, path, _ in list_available_addons(repo, repo_path)}

    if not available:
        raise NotFoundError("No addons found in any submodule.")

    # Selection: user chooses the desired active-addon state (desired set, not a diff).
    result_sel = prompt_choices("Select addon(s): ", set(available.keys()), existing)
    if result_sel is None:
        raise AppAbort()

    selected = set(result_sel)
    previously_selected = existing & set(available.keys())

    added = selected - previously_selected
    removed = previously_selected - selected

    if not added and not removed:
        click.echo("Nothing to do.")
        return

    # 1. Build the plan (pure business logic)
    plan = _build_plan(added, removed, available)

    # 2. Define how to execute one action; track results for separate commits.
    created: list[str] = []
    unlinked: list[str] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        link = repo_path / action.label
        if action.data["action"] == "link":
            if link.exists() or link.is_symlink():
                return colorize("skipped (exists)", "yellow"), False
            os.symlink(relpath(repo_path, Path(action.data["path"])), link)
            created.append(action.label)
            return colorize("linked", "green"), True
        else:
            if not link.is_symlink():
                return colorize("skipped (not symlink)", "yellow"), False
            link.unlink()
            unlinked.append(action.label)
            return colorize("unlinked", "yellow"), True

    # 3. Run the shared scenario (present → confirm → apply)
    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Applied changes",
        select=False,
        empty_message="Nothing to do.",
    )

    # 4. Command-specific side effects: one commit per change type.
    if not no_commit:
        if created:
            outer.merge(commit_v2(repo, repo_path, created, "addons_new", skip_hooks=True))
        if unlinked:
            outer.merge(commit_v2(repo, repo_path, unlinked, "addons_remove", remove=True, skip_hooks=True))
    elif created or unlinked:
        outer.add_warning("Don't forget to commit the symlink changes.")

    # 5. Final render (after commits), non-zero exit on errors
    render_and_raise(result, outer)
