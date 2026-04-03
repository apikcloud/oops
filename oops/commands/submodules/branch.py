# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: branch.py — oops/commands/submodules/branch.py

"""
Detect and fix submodules missing a branch in .gitmodules.

Iterates over all submodules, finds those without a branch entry, and either
prompts interactively or applies the default branch provided via --branch.
"""

import configparser
import logging

import click

from oops.commands.base import command
from oops.utils.git import commit, get_local_repo, is_pull_request, read_gitmodules
from oops.utils.tools import ask


@command(name="branch", help=__doc__)
@click.option(
    "--branch",
    "default_branch",
    help="Branch name to set for submodules missing branch in .gitmodules",
)
@click.option(
    "--skip-pr",
    is_flag=True,
    help="Do not ask for submodules that look like pull request paths",
)
@click.option(
    "--no-commit",
    is_flag=True,
    help="Do not commit automatically at the end",
)
def main(default_branch: str, skip_pr: bool, no_commit: bool):  # noqa: C901, PLR0912

    repo, repo_path = get_local_repo()

    if not repo.submodules:
        click.echo("No submodules found.")
        raise click.Abort()

    to_fix = []
    gitmodules = read_gitmodules(repo)

    for submodule in repo.submodules:
        # Check if branch is set in .gitmodules
        # branch_name can't be used because it returns master if not set
        section = f'submodule "{submodule.name}"'
        try:
            branch = gitmodules.get_value(section, "branch")
            logging.debug(f"{submodule.name}: branch = {branch!r}")
        except configparser.NoOptionError:
            pull_request = is_pull_request(submodule)

            if skip_pr and pull_request:
                logging.debug(
                    f"Skipping submodule {submodule.name!r} as it looks like a pull request path"
                )
                continue

            if default_branch and not pull_request:
                to_fix.append((submodule.name, default_branch))
                continue

            res = ask(
                f"Submodule {submodule.name} is missing branch. Please enter the branch to set: "
            )

            if res:
                to_fix.append((submodule.name, res))

    if not to_fix:
        click.echo("Nothing to fix.")
        raise click.Abort()

    for name, branch in to_fix:
        click.echo(f"Setting branch {branch!r} for submodule {name!r}...")
        gitmodules.set_value(f'submodule "{name}"', "branch", branch)

    gitmodules.write()

    if not no_commit:
        click.echo("Committing changes to .gitmodules...")
        commit(
            repo,
            repo_path,
            [".gitmodules"],
            "submodules_branch",
        )
