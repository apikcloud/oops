# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: check.py — oops/commands/manifest/check.py

"""
[EXPERIMENTAL] Check all Odoo manifest files against the oops lint rules.

Scans the repository for __manifest__.py files and runs the rules defined
in oops.rules.manifest (author/maintainers, key order). Reports violations
and exits non-zero if any are found.

Use oops-man-fix to apply autofixes.
"""

import click

from oops.commands.base import command
from oops.commands.manifest.common import collect_paths, run_fixit
from oops.services.git import get_local_repo
from oops.utils.helpers import str_to_list


@command(name="check", help=__doc__)
@click.option("--diff", is_flag=True, help="Show the autofix diff alongside each violation.")
@click.option("--names", default=None, help="Comma-separated list of addon names to check.")
def main(diff: bool, names: str) -> None:
    _, repo_path = get_local_repo()

    name_filter = str_to_list(names) if names else None
    paths = collect_paths(repo_path, name_filter)

    if not paths:
        click.echo("No manifest files found.")
        raise click.exceptions.Exit(0)

    violations = run_fixit(paths, autofix=False, show_diff=diff)

    if violations:
        raise click.exceptions.Exit(1)

    click.echo(f"All {len(paths)} manifest(s) passed.")
