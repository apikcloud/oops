# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: branch.py — oops/commands/submodules/branch.py

"""
Detect and fix submodules missing a branch in .gitmodules.

Iterates over all submodules, finds those without a branch entry, and sets the
specified branch (or the project's major Odoo version if not given).

Usage:
    oops submodules branch [NAMES...] [BRANCH]

If BRANCH is omitted it is read from the project's odoo_version.txt.
If NAMES are omitted an interactive selection menu is shown.
"""

from __future__ import annotations

import configparser

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.core.logger import log
from oops.core.models import Plan, PlanAction, Result
from oops.io.file import parse_odoo_version
from oops.output.helper import render_and_raise
from oops.output.workflow import run_mutation_workflow
from oops.services.git import commit_v2, is_pull_request, read_gitmodules, require_repository, require_submodules
from oops.utils.render import colorize
from oops_engine.compat import Optional, Tuple


def _build_plan(submodules, gitmodules, branch: str, skip_pr: bool) -> Plan:
    actions = []
    for sub in submodules:
        section = f'submodule "{sub.name}"'
        try:
            existing = gitmodules.get_value(section, "branch")
            log.debug(f"{sub.name}: branch already set to {existing!r}, skipping")
        except configparser.NoOptionError:
            pull_request = is_pull_request(sub)
            if skip_pr and pull_request:
                log.debug(f"Skipping PR submodule {sub.name!r}")
                continue
            actions.append(
                PlanAction(
                    label=sub.name,
                    new=branch,
                    detail="PR" if pull_request else "",
                    kind="available",
                )
            )
    return Plan(title="Branch fixes", actions=actions)


@command(name="branch", help=__doc__)
@click.option("--skip-pr", is_flag=True, help="Skip submodules that are pull requests")
@click.option("--no-commit", is_flag=True, help="Do not commit automatically at the end")
@click.option("-f", "--force", is_flag=True, help="Apply all changes without prompting")
@click.argument("names", nargs=-1, required=False)
@click.argument("branch", required=False, default=None)
def main(
    skip_pr: bool,
    no_commit: bool,
    force: bool,
    names: Tuple[str, ...],
    branch: Optional[str],
):
    repo, repo_path = require_repository()
    require_submodules(repo)

    if branch is None:
        try:
            branch = str(parse_odoo_version(repo_path).major_version)
        except Exception as exc:
            raise OopsError(
                f"Could not read Odoo version from {config.project.file_odoo_version}. "
                "Pass BRANCH explicitly."
            ) from exc

    gitmodules = read_gitmodules(repo)
    plan = _build_plan(repo.submodules, gitmodules, branch, skip_pr)

    if names:
        plan.restrict_to(set(names))

    def apply(action: PlanAction) -> Tuple[str, bool]:
        log.debug(f"Setting branch {action.new!r} for {action.label!r}")
        gitmodules.set_value(f'submodule "{action.label}"', "branch", action.new)
        return colorize(f"set to {action.new!r}", "green"), True

    outer: Result[None] = Result()
    result = run_mutation_workflow(
        plan=plan,
        apply=apply,
        outer=outer,
        title="Branch fixes",
        force=force,
        select=not names,
        select_prompt="Select submodule(s) to fix: ",
        empty_message="No submodules missing a branch.",
    )

    # Flush all in-memory gitmodules changes to disk before staging
    gitmodules.write()

    if not no_commit:
        outer.merge(
            commit_v2(repo, repo_path, [".gitmodules"], "submodules_branch", skip_hooks=True)
        )
    else:
        outer.add_warning("Don't forget to commit .gitmodules to share changes with the team.")

    render_and_raise(result, outer)
