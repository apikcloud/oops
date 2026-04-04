# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
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
from oops.services.docker import check_image, parse_image_tag
from oops.services.git import get_local_repo
from oops.utils.render import render_table


@command(name="check", help=__doc__)
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def main(strict: bool):  # noqa: C901

    _, repo_path = get_local_repo()

    # Always collect without raising so we can display everything before exiting
    warns, errors = check_project(repo_path, strict=False)

    try:
        odoo_version = parse_odoo_version(repo_path)
        image_info = parse_image_tag(odoo_version)
        warns += check_image(image_info, strict=False)
    except ValueError as e:
        errors.append(str(e))

    rows = []
    for msg in warns:
        rows.append([click.style("Warning", fg="yellow"), click.style(msg, fg="yellow")])
    for msg in errors:
        rows.append([click.style("Error", fg="red"), click.style(msg, fg="red")])

    if rows:
        click.echo(render_table(rows))

    if errors or (strict and warns):
        raise click.exceptions.Exit(1)
