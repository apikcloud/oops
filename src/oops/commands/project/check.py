# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: check.py — oops/commands/project/check.py

"""
Validate project configuration and list available Odoo Docker images.

Checks for mandatory project files, verifies the configured Odoo image, and
reports warnings and errors. Exits non-zero if errors are found; with --strict,
warnings also cause a non-zero exit.
"""

import click
from oops.commands.base import command
from oops.commands.project.common import check_project
from oops.io.file import parse_odoo_version
from oops.services.docker import check_image
from oops.services.git import get_local_repo
from oops.utils.render import print_error, print_success, print_warning


@command(name="check", help=__doc__)
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def main(strict: bool):

    _, repo_path = get_local_repo()

    # Always collect without raising so we can display everything before exiting
    warns, errors = check_project(repo_path, strict=False)

    try:
        image_info = parse_odoo_version(repo_path)
        warns += check_image(image_info, strict=False)
    except ValueError as e:
        errors.append(str(e))

    for msg in warns:
        print_warning(msg)
    for msg in errors:
        print_error(msg)

    if errors or (strict and warns):
        raise click.exceptions.Exit(1)

    if not warns and not errors:
        print_success("Check completed without errors")
