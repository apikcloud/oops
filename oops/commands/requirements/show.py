# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: update.py — oops/commands/requirements/show.py

"""
Display the differences between the existing requirements and the expected ones.

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


@click.command("show")
def main():
    requirement_file = Path(config.project_file_requirements)
    repo = Repo()
    repo_path = Path(repo.working_dir)

    has_changes, python_dependencies, diff = get_python_dependencies(requirement_file, repo_path)

    if not has_changes:
        click.echo("No changes detected in requirements.")
        return

    click.echo(f"Changes for {requirement_file}:")
    for line in diff:
        if line.startswith("- "):
            click.secho(line, fg="red")
        elif line.startswith("+ "):
            click.secho(line, fg="green")
