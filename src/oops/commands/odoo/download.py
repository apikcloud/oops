# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — oops/commands/odoo/download.py

"""
Download (or update) Odoo Community and Enterprise source code.

Clones Community and Enterprise from GitHub using SSH into:

    <sources_dir>/<version>/community
    <sources_dir>/<version>/enterprise

The sources directory is read from odoo.sources_dir in ~/.oops.yaml.

If a directory already exists the clone step is skipped.  Pass --update to
pull the latest changes instead.
"""

import subprocess

import click
from oops.commands.base import command
from oops.core.config import config
from oops.io.file import get_odoo_sources_dirs
from oops.utils.git import clone, update_latest
from oops.utils.helpers import normalize_version
from oops.utils.render import print_success, print_warning


@command(name="download", help=__doc__)
@click.argument("version", callback=normalize_version, is_eager=True)
@click.option("--update", "do_update", is_flag=True, help="Pull latest changes if repos already exist.")
@click.option(
    "--enterprise/--no-enterprise",
    "with_enterprise",
    is_flag=True,
    default=True,
    help="Include or exclude Enterprise sources.",
)
def main(  # noqa: C901, PLR0912
    version: str,
    do_update: bool,
    with_enterprise: bool,
) -> None:

    errors: list[str] = []
    community_dir, enterprise_dir = get_odoo_sources_dirs(version)

    # --- Community ---
    if community_dir.exists():
        if do_update:
            click.echo(f"Updating Odoo Community {version} in '{community_dir}'…")
            try:
                update_latest(community_dir)
                print_success(f"Community {version} updated.")
            except subprocess.CalledProcessError as exc:
                errors.append(f"Community update failed: {exc}")
                click.echo(click.style(f"  ✘ {errors[-1]}", fg="red"), err=True)
        else:
            print_warning(f"'{community_dir}' already exists — skipping Community clone (use --update to pull).")
    else:
        click.echo(f"Cloning Odoo Community {version} into '{community_dir}'…")
        try:
            clone(config.odoo.community_url, community_dir, version)
            print_success(f"Community {version} cloned.")
        except subprocess.CalledProcessError as exc:
            errors.append(f"Community clone failed: {exc}")
            click.echo(click.style(f"  ✘ {errors[-1]}", fg="red"), err=True)

    # --- Enterprise ---
    if not with_enterprise:
        return

    if enterprise_dir.exists():
        if do_update:
            click.echo(f"Updating Odoo Enterprise {version} in '{enterprise_dir}'…")
            try:
                update_latest(enterprise_dir)
                print_success(f"Enterprise {version} updated.")
            except subprocess.CalledProcessError as exc:
                errors.append(f"Enterprise update failed: {exc}")
                click.echo(click.style(f"  ✘ {errors[-1]}", fg="red"), err=True)
        else:
            print_warning(f"'{enterprise_dir}' already exists — skipping Enterprise clone (use --update to pull).")
    else:
        click.echo(f"Cloning Odoo Enterprise {version} into '{enterprise_dir}'…")
        try:
            clone(config.odoo.enterprise_url, enterprise_dir, version)
            print_success(f"Enterprise {version} cloned.")
        except subprocess.CalledProcessError as exc:
            errors.append(f"Enterprise clone failed: {exc}")
            click.echo(click.style(f"  ✘ {errors[-1]}", fg="red"), err=True)

    if errors:
        raise click.exceptions.Exit(1)
