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
from oops.io.file import parse_odoo_version
from oops.services.docker import check_image
from oops.services.git import require_repository
from oops.services.project import check_project
from oops.utils.render import conclude, render_result, rule


@command(name="check", help=__doc__)
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def main(strict: bool):

    _, repo_path = require_repository()

    rule(f"Project check — {repo_path.name}")

    result = check_project(repo_path, strict=False)

    try:
        image_info = parse_odoo_version(repo_path)
        result.merge(check_image(image_info, strict=False))
    except (FileNotFoundError, ValueError) as e:
        result.add_error(str(e) or "Could not parse Odoo version.")

    if strict and result.warnings:
        for w in result.warnings:
            result.add_error(w)
        result.warnings.clear()

    render_result(result)  # raises OopsError(Exit 1) on errors
    conclude(result.ok, "Check completed without errors")
