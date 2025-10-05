#!/usr/bin/env python3


import click

from osh.docker import check_image, parse_image_tag
from osh.gitutils import git_top
from osh.project.common import check_project, parse_odoo_version
from osh.render import render_table


@click.command(name="check")
@click.option("--strict", is_flag=True, help="Do not fail on warnings")
def main(strict: bool):  # noqa: C901
    """Check project configuration and list available odoo images."""

    repo = git_top()

    warnings, errors = check_project(repo, strict=strict)
    odoo_version = parse_odoo_version(repo)
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
