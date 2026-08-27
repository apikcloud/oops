# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — oops/commands/submodules/update.py

"""
Fetch and pull submodules to their latest upstream commit.

For each submodule with a configured branch, fetches from origin, checks out
the branch, and pulls the latest commits. Specific submodules can be targeted
by name; PR submodules can be filtered with --skip-pr or --only-pr.

When called without arguments or PR filters, displays an interactive selection
menu.
"""

from __future__ import annotations

import click
from oops.commands.base import command
from oops.core.logger import log
from oops.core.models import Plan, PlanAction, Result
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, is_pull_request, require_repository, require_submodules
from oops.utils.render import colorize
from oops_engine.compat import Tuple


def _build_plan(submodules, skip_pr: bool, only_pr: bool) -> Plan:
    actions = []
    for sub in submodules:
        if skip_pr and is_pull_request(sub):
            continue
        if only_pr and not is_pull_request(sub):
            continue

        if not sub.path:
            actions.append(PlanAction(label=sub.name, detail="no path", kind="nothing to do"))
            continue
        # FIXME: branch_name defaults to master if not explicitly configured
        if not sub.branch_name:
            actions.append(PlanAction(label=sub.name, detail="no branch", kind="nothing to do"))
            continue

        actions.append(PlanAction(label=sub.name, detail=sub.branch_name, kind="available"))

    return Plan(title="Submodule updates", actions=actions)


@command("update", help=__doc__)
@click.option("--no-commit", is_flag=True, help="Do not commit changes")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.option("--skip-pr", is_flag=True, help="Skip submodules that are pull requests")
@click.option("--only-pr", is_flag=True, help="Only update submodules that are pull requests")
@click.argument("names", nargs=-1, required=False)
def main(no_commit: bool, force: bool, skip_pr: bool, only_pr: bool, names: Tuple[str, ...]):
    if skip_pr and only_pr:
        raise click.UsageError("--skip-pr and --only-pr are mutually exclusive")

    repo, repo_path = require_repository()
    submodules = list(require_submodules(repo))

    plan = _build_plan(submodules, skip_pr, only_pr)

    if names:
        plan.restrict_to(set(names))

    sub_map = {s.name: s for s in submodules}
    changes: list[str] = []

    def apply(action: PlanAction) -> Tuple[str, bool]:
        sub = sub_map[action.label]
        branch = action.detail
        log.info(f"Updating {sub.name}…")
        sub_repo = sub.module()
        sub_repo.remotes.origin.fetch()
        sub_repo.git.checkout(branch)
        sub_repo.remotes.origin.pull(branch)
        repo.git.add(sub.path)
        changes.append(f"{sub.name} ({branch})")
        return colorize(f"updated ({branch})", "green"), True

    # Skip interactive selection when names or PR filters narrow the scope
    use_selection = not (names or skip_pr or only_pr)

    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Updates",
        force=force,
        select=use_selection,
        select_prompt="Select submodule(s) to update: ",
        empty_message="Nothing to update.",
    )

    if not no_commit:
        outer.merge(
            commit_v2(
                repo,
                repo_path,
                [],
                "submodules_update",
                description="\n".join(changes),
                skip_hooks=True,
                already_staged=True,
            )
        )
    else:
        outer.add_warning("Don't forget to commit to share changes with the team.")

    render_and_raise(result, outer)
