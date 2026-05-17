# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: show.py — oops/commands/odoo/show.py

"""
List locally available Odoo source checkouts.

Scans the sources directory for version folders and shows, for each version,
the current commit hash and author date for Community, Enterprise, and
design-themes.

The sources directory is configured via odoo.sources_dir in ~/.oops.yaml.
"""

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import ConfigError, NotFoundError
from oops.utils.git import repo_info
from oops.utils.render import get_console, make_table, metrics_panel


@command(name="show", help=__doc__)
def main() -> None:
    resolved = config.odoo.sources_dir
    if resolved is None:
        raise ConfigError("No base directory provided. Set odoo.sources_dir in ~/.oops.yaml.")

    if not resolved.exists():
        raise NotFoundError(f"Sources directory '{resolved}' does not exist.")

    version_dirs = sorted(
        (d for d in resolved.iterdir() if d.is_dir()),
        key=lambda d: d.name,
    )

    if not version_dirs:
        click.echo(f"No version directories found in '{resolved}'.")
        return

    rows: list[list[str]] = []
    counts = {"community": 0, "enterprise": 0, "themes": 0}

    for version_dir in version_dirs:
        community = repo_info(version_dir / "community")
        enterprise = repo_info(version_dir / "enterprise")
        themes = repo_info(version_dir / "themes")
        if community:
            counts["community"] += 1
        if enterprise:
            counts["enterprise"] += 1
        if themes:
            counts["themes"] += 1
        if community or enterprise or themes:
            rows.append([
                version_dir.name,
                community or "—",
                enterprise or "—",
                themes or "—",
            ])

    if not rows:
        click.echo(f"No Odoo checkouts found in '{resolved}'.")
        return

    console = get_console()

    panel = metrics_panel(
        "Summary",
        [
            ["Versions", str(len(rows))],
            ["Community", str(counts["community"])],
            ["Enterprise", str(counts["enterprise"])],
            ["Themes", str(counts["themes"])],
        ],
    )

    columns = [
        ("Version", "brand.primary", "left"),
        ("Community", "dim", "left"),
        ("Enterprise", "dim", "left"),
        ("Themes", "dim", "left"),
    ]

    table = make_table(title=None, columns=columns, rows=rows)

    console.print()
    console.print(panel)
    console.print()
    console.print(table)
    console.print()
