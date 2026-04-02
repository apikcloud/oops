# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: check.py — oops/commands/requirements/check.py

"""
Check the differences between the existing requirements and the expected ones.

The expecting requirements are computed by going through the addons at the root of the project and extracted from the
manifests.

In case of changes, it will be displayed like this:

Changes for requirements.txt:
- astor
+ pandas
+ python-stdnum
- pytz
+ pytz==2023.3

"""

from __future__ import annotations

from pathlib import Path

import click
from git import Repo

from oops.core.config import config
from oops.utils.io import get_python_dependencies


@click.command("check", help=__doc__)
def main():

    repo = Repo()
    requirement_file = Path(config.project_file_requirements)
    repo_path = Path(repo.working_dir)

    has_changes, _, diff = get_python_dependencies(requirement_file, repo_path)

    if not has_changes:
        click.echo("No changes detected in requirements.")
        raise click.exceptions.Exit(0)

    click.echo(f"Changes for {requirement_file}:")
    for line in diff:
        if line.startswith("- "):
            click.secho(line, fg="red")
        elif line.startswith("+ "):
            click.secho(line, fg="green")

    raise click.exceptions.Exit(1)
