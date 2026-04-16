# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
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
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import get_requirements_diff
from oops.services.git import get_local_repo
from oops.utils.render import print_error, print_success


@command("check", help=__doc__)
@click.option("--no-fail", is_flag=True, default=False, help="Exit 0 even when changes are detected.")
def main(no_fail):
    _, repo_path = get_local_repo()
    requirement_file = Path(config.project.file_requirements)

    has_changes, _, diff = get_requirements_diff(requirement_file, repo_path)

    if not has_changes:
        print_success("No changes detected in requirements.")
        raise click.exceptions.Exit(0)

    click.echo(f"Changes for {requirement_file}:")
    for line in diff:
        if line.startswith("- "):
            print_error(line, symbol="")
        elif line.startswith("+ "):
            print_success(line, symbol="")

    raise click.exceptions.Exit(0 if no_fail else 1)
