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

from oops.commands.project.common import check_project, parse_odoo_version
from oops.git.core import GitRepository
from oops.services.docker import check_image, parse_image_tag
from oops.utils.render import render_table


@click.command(name="check", help=__doc__)
@click.option("--strict", is_flag=True, help="Do not fail on warnings")
def main(strict: bool):  # noqa: C901

    repo = GitRepository()

    warnings, errors = check_project(repo.path, strict=strict)
    odoo_version = parse_odoo_version(repo.path)
    image_infos = parse_image_tag(odoo_version)
    warnings += check_image(image_infos, strict=strict)

    rows = []
    if warnings:
        for row in warnings:
            rows.append([click.style("Warning", fg="yellow"), click.style(row, fg="yellow")])

    if errors:
        for row in errors:
            rows.append([click.style("Error", fg="red"), click.style(row, fg="red")])

    click.echo(render_table(rows))
