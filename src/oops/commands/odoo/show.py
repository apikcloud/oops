# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/odoo/show.py

"""
List locally available Odoo source checkouts.

Scans the sources directory for version folders and shows, for each version,
the current commit hash and author date for Community and Enterprise.

The sources directory is configured via odoo.sources_dir in ~/.oops.yaml.
"""

import click
from oops.commands.base import command
from oops.core.config import config
from oops.utils.git import repo_info
from oops.utils.render import render_table


@command(name="show", help=__doc__)
def main() -> None:
    resolved = config.odoo.sources_dir
    if resolved is None:
        raise click.UsageError("No base directory provided. Set odoo.sources_dir in ~/.oops.yaml.")

    if not resolved.exists():
        raise click.ClickException(f"Sources directory '{resolved}' does not exist.")

    version_dirs = sorted(
        (d for d in resolved.iterdir() if d.is_dir()),
        key=lambda d: d.name,
    )

    if not version_dirs:
        click.echo(f"No version directories found in '{resolved}'.")
        return

    rows = []
    for version_dir in version_dirs:
        community = repo_info(version_dir / "community")
        enterprise = repo_info(version_dir / "enterprise")
        if community or enterprise:
            rows.append([version_dir.name, community or "—", enterprise or "—"])

    if not rows:
        click.echo(f"No Odoo checkouts found in '{resolved}'.")
        return

    click.echo(render_table(rows, headers=["Version", "Community", "Enterprise"]))
