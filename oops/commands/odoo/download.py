# Copyright 2026 apik (https://apik.cloud).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
#
# File: download.py — oops/commands/odoo/download.py

"""
Download (or update) Odoo Community and Enterprise source code.

Clones Community and Enterprise (when --enterprise is passed) from GitHub
using SSH into:

    <base_dir>/<version>/community
    <base_dir>/<version>/enterprise

The base directory is read from odoo.sources_dir in ~/.oops.yaml (or .oops.yaml)
and can be overridden with --base-dir.

If a directory already exists the clone step is skipped.  Pass --update to
pull the latest changes instead.
"""

import subprocess
from pathlib import Path

import click

from oops.commands.base import command
from oops.core.config import config
from oops.utils.compat import Optional
from oops.utils.git import clone, update_latest
from oops.utils.render import print_success, print_warning


def _normalize_version(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Ensure version is in X.0 format (e.g. '19' → '19.0')."""
    return value if "." in value else f"{value}.0"


@command(name="download", help=__doc__)
@click.argument("version", callback=_normalize_version, is_eager=True)
@click.option(
    "--base-dir",
    default=None,
    type=click.Path(file_okay=False, writable=True),
    help="Root directory for Odoo sources. Defaults to odoo.sources_dir in config.",
)
@click.option(
    "--update", "do_update", is_flag=True, help="Pull latest changes if repos already exist."
)
@click.option(
    "--enterprise/--no-enterprise",
    "with_enterprise",
    is_flag=True,
    default=True,
    help="Include or exclude Enterprise in the update.",
)
def main(  # noqa: C901, PLR0912
    version: str,
    base_dir: Optional[str],
    do_update: bool,
    with_enterprise: bool,
) -> None:
    resolved = Path(base_dir) if base_dir else config.odoo.sources_dir
    if resolved is None:
        raise click.UsageError(
            "No base directory provided. Pass --base-dir or set odoo.sources_dir in ~/.oops.yaml."
        )
    target = resolved / version
    target.mkdir(parents=True, exist_ok=True)

    community_dir = target / "community"
    enterprise_dir = target / "enterprise"

    errors: list[str] = []

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
            print_warning(
                f"'{community_dir}' already exists — "
                "skipping Community clone (use --update to pull)."
            )
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
            print_warning(
                f"'{enterprise_dir}' already exists — "
                "skipping Enterprise clone (use --update to pull)."
            )
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
