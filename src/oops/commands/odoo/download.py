# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: download.py — oops/commands/odoo/download.py

"""
Download (or update) Odoo Community, Enterprise, and Themes source code.

Clones the requested repositories from GitHub using SSH into:

    <sources_dir>/<version>/community
    <sources_dir>/<version>/enterprise
    <sources_dir>/<version>/themes

The sources directory is read from odoo.sources_dir in ~/.oops.yaml.

If a directory already exists the clone step is skipped.  Pass --update to
pull the latest changes instead.
"""

import subprocess

import click
from oops.commands.base import command
from oops.core.config import config
from oops.core.exceptions import OopsError
from oops.io.file import get_odoo_sources_dirs
from oops.utils.git import clone, update_latest
from oops.utils.helpers import normalize_version
from oops.utils.render import print_success, print_warning


@command(name="download", help=__doc__)
@click.argument("version", callback=normalize_version, is_eager=True)
@click.option("--update", "do_update", is_flag=True, help="Pull latest changes if repos already exist.")
@click.option(
    "--community/--no-community",
    "with_community",
    is_flag=True,
    default=True,
    help="Include or exclude Community sources.",
)
@click.option(
    "--enterprise/--no-enterprise",
    "with_enterprise",
    is_flag=True,
    default=True,
    help="Include or exclude Enterprise sources.",
)
@click.option(
    "--themes/--no-themes",
    "with_themes",
    is_flag=True,
    default=True,
    help="Include or exclude design-themes sources.",
)
def main(
    version: str,
    do_update: bool,
    with_community: bool,
    with_enterprise: bool,
    with_themes: bool,
) -> None:
    dirs = get_odoo_sources_dirs(version)

    repos = [
        ("Community", config.odoo.community_url, dirs.community, with_community),
        ("Enterprise", config.odoo.enterprise_url, dirs.enterprise, with_enterprise),
        ("Themes", config.odoo.themes_url, dirs.themes, with_themes),
    ]

    errors: list[str] = []

    for label, url, dest, enabled in repos:
        if not enabled:
            continue

        if dest.exists():
            if do_update:
                click.echo(f"Updating Odoo {label} {version} in '{dest}'…")
                try:
                    update_latest(dest)
                    print_success(f"{label} {version} updated.")
                except subprocess.CalledProcessError as exc:
                    msg = f"{label} update failed: {exc}"
                    errors.append(msg)
                    # TODO: replace by print_error, include err=True?
                    click.echo(click.style(f"  ✘ {msg}", fg="red"), err=True)
            else:
                print_warning(f"'{dest}' already exists — skipping {label} clone (use --update to pull).")
        else:
            click.echo(f"Cloning Odoo {label} {version} into '{dest}'…")
            try:
                clone(url, dest, version)
                print_success(f"{label} {version} cloned.")
            except subprocess.CalledProcessError as exc:
                msg = f"{label} clone failed: {exc}"
                errors.append(msg)
                # TODO: replace by print_error, include err=True?
                click.echo(click.style(f"  ✘ {msg}", fg="red"), err=True)

    if errors:
        raise OopsError("; ".join(errors))
