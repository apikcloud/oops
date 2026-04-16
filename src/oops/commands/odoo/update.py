# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — oops/commands/odoo/update.py

"""
Update Odoo Community and Enterprise source checkouts.

Operates on repositories previously cloned by oops-odoo-download into:

    <base_dir>/<version>/community
    <base_dir>/<version>/enterprise

The sources directory is read from odoo.sources_dir in ~/.oops.yaml.

Without --date, fetches and checks out the latest commit on the branch.

With --date YYYY-MM-DD, fetches history back to that date and checks out
the last commit that existed at or before midnight of that day, leaving
the working tree in a detached-HEAD state at the chosen snapshot.

Pass --enterprise to also update the Enterprise checkout.
"""

import subprocess
from datetime import date as Date

import click
from oops.commands.base import command
from oops.io.file import get_odoo_sources_dirs
from oops.utils.compat import Optional
from oops.utils.git import update_at_date, update_latest
from oops.utils.helpers import normalize_version
from oops.utils.render import print_success, print_warning


@command(name="update", help=__doc__)
@click.argument("version", callback=normalize_version, is_eager=True)
@click.option(
    "--date",
    default=None,
    metavar="YYYY-MM-DD",
    help="Checkout the last commit at or before this date.",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--enterprise/--no-enterprise",
    "with_enterprise",
    is_flag=True,
    default=True,
    help="Include or exclude Enterprise in the update.",
)
def main(
    version: str,
    date: Optional[Date],
    with_enterprise: bool,
) -> None:
    community_dir, enterprise_dir = get_odoo_sources_dirs(version)

    repos = {"Community": community_dir}
    if with_enterprise:
        repos["Enterprise"] = enterprise_dir

    date_str = date.strftime("%Y-%m-%d") if date else None
    errors: list[str] = []

    for label, dest in repos.items():
        if not dest.exists():
            print_warning(f"'{dest}' not found — run oops-odoo-download first.")
            continue

        if date_str:
            click.echo(f"Updating {label} {version} to snapshot {date_str} in '{dest}'…")
            try:
                update_at_date(dest, date_str)
                print_success(f"{label} {version} checked out at {date_str}.")
            except (subprocess.CalledProcessError, click.ClickException) as exc:
                msg = f"{label} update failed: {exc}"
                errors.append(msg)
                # TODO: replace by print_error, include err=True?
                click.echo(click.style(f"  ✘ {msg}", fg="red"), err=True)
        else:
            click.echo(f"Updating {label} {version} to latest in '{dest}'…")
            try:
                update_latest(dest)
                print_success(f"{label} {version} updated to latest.")
            except subprocess.CalledProcessError as exc:
                msg = f"{label} update failed: {exc}"
                errors.append(msg)
                # TODO: replace by print_error, include err=True?
                click.echo(click.style(f"  ✘ {msg}", fg="red"), err=True)

    if errors:
        raise click.exceptions.Exit(1)
