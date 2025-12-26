#!/usr/bin/env python3


import configparser
import logging

import click
from git import Repo

from oops.core.messages import commit_messages
from oops.utils.git import is_pull_request, read_gitmodules
from oops.utils.tools import ask


@click.command(name="branch")
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
    """Fix submodules missing branch in .gitmodules"""

    repo = Repo(".")

    if not repo.submodules:
        click.echo("No submodules found.")
        return 0

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
        return 0

    for name, branch in to_fix:
        click.echo(f"Setting branch {branch!r} for submodule {name!r}...")
        gitmodules.set_value(f'submodule "{name}"', "branch", branch)

    gitmodules.write()

    if not no_commit:
        click.echo("Committing changes to .gitmodules...")
        repo.index.add([".gitmodules"])
        repo.index.commit(commit_messages.submodules_branch)
