# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/requirements/check.py

"""
Check the differences between the existing requirements and the expected ones.

The expected requirements are computed by scanning every root addon manifest and
collecting their ``external_dependencies["python"]`` entries.

In case of changes, it will be displayed like this:

    Changes for requirements.txt:

    - astor
    + pandas
    + python-stdnum
    - pytz
    + pytz==2023.3

See the requirements documentation for merging rules
and name-mapping details.
"""

from __future__ import annotations

from pathlib import Path

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import EarlyExit, OopsError
from oops.io.file import get_requirements_diff
from oops.services.git import require_repository
from oops.utils.render import print_error, print_success


@command("check", help=__doc__)
@click.option("--no-fail", is_flag=True, default=False, help="Exit 0 even when changes are detected.")
def main(no_fail):
    _, repo_path = require_repository()
    requirement_file = Path(config.project.file_requirements)

    has_changes, _, diff = get_requirements_diff(repo_path)

    if not has_changes:
        print_success("No changes detected in requirements.")
        raise EarlyExit()

    click.echo(f"Changes for {requirement_file}:")
    for line in diff:
        if line.startswith("- "):
            print_error(line, symbol="")
        elif line.startswith("+ "):
            print_success(line, symbol="")

    if no_fail:
        raise EarlyExit()
    raise OopsError("Requirements differ. See output above.")
