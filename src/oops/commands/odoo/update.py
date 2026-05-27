# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: update.py — oops/commands/odoo/update.py

"""
Update Odoo Community, Enterprise, and Themes source checkouts.

Operates on repositories previously cloned by oops-odoo-download into:

    <base_dir>/<version>/community
    <base_dir>/<version>/enterprise
    <base_dir>/<version>/themes

The sources directory is read from odoo.sources_dir in ~/.oops.yaml.

Without --date, fetches and checks out the latest commit on the branch.

With --date YYYY-MM-DD, fetches history back to that date and checks out
the last commit that existed at or before midnight of that day, leaving
the working tree in a detached-HEAD state at the chosen snapshot.

Pass --no-community / --no-enterprise / --no-themes to skip individual repos.
"""

import subprocess
from datetime import date as Date
from pathlib import Path

import click
from oops.commands.base import command
from oops.core.compat import Optional
from oops.core.exceptions import OopsError
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.io.file import get_odoo_sources_dirs, parse_odoo_version, require_odoo_sources
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.output.sinks import deliver
from oops.services.git import require_repository
from oops.utils.git import update_at_date, update_latest
from oops.utils.helpers import normalize_version
from oops.utils.render import prompt_select

from .presenters.update import prepare

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="update", help=__doc__)
@click.option(
    "--version",
    default=None,
)
@click.option(
    "--date",
    default=None,
    metavar="YYYY-MM-DD",
    help="Checkout the last commit at or before this date.",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--community/--no-community",
    "with_community",
    is_flag=True,
    default=True,
    help="Include or exclude Community in the update.",
)
@click.option(
    "--enterprise/--no-enterprise",
    "with_enterprise",
    is_flag=True,
    default=True,
    help="Include or exclude Enterprise in the update.",
)
@click.option(
    "--themes/--no-themes",
    "with_themes",
    is_flag=True,
    default=True,
    help="Include or exclude design-themes in the update.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format. 'json' is suited for downstream consumption.",
)
@click.option(
    "--output-path",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the output to this path instead of stdout.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Stream git output to the terminal.",
)
def main(
    version: Optional[str],
    date: Optional[Date],
    with_community: bool,
    with_enterprise: bool,
    with_themes: bool,
    output_format: str,
    output_path: "Optional[Path]",
    verbose: bool,
) -> None:
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()
    assert metadata is not None

    availables = require_odoo_sources()

    if version is None:
        try:
            _, repo_path = require_repository()
            image_info = parse_odoo_version(repo_path)
            version = str(image_info.major_version)
        except Exception:
            version = prompt_select("Select a version:", [item.version for item in availables])

    version = normalize_version(version)

    outer: Result[None] = Result()
    result: Result[dict] = Result({"cmd": f"Update Odoo {version} sources", "rows": []})
    assert result.data is not None

    dirs = get_odoo_sources_dirs(version)

    repos = [
        ("Community", dirs.community, with_community),
        ("Enterprise", dirs.enterprise, with_enterprise),
        ("Themes", dirs.themes, with_themes),
    ]

    date_str = date.strftime("%Y-%m-%d") if date else None

    with live_progress("Updating Odoo sources…"):
        for label, dest, enabled in repos:
            if not enabled:
                continue

            if not dest.exists():
                msg = f"'{dest}' not found — run oops-odoo-download first"
                outer.add_warning(msg)
                result.data["rows"].append({"repo": label, "action": "skipped", "detail": "not found"})
                continue

            if date_str:
                log.info(f"Updating {label} {version} to snapshot {date_str}…")
                try:
                    update_at_date(dest, date_str, quiet=not verbose)
                    result.data["rows"].append({"repo": label, "action": "updated", "detail": date_str})
                except (subprocess.CalledProcessError, click.ClickException) as exc:
                    msg = f"{label} update failed: {exc}"
                    result.data["rows"].append({"repo": label, "action": "failed", "detail": str(exc)})
                    outer.add_error(msg)
            else:
                log.info(f"Updating {label} {version} to latest…")
                try:
                    update_latest(dest, quiet=not verbose)
                    result.data["rows"].append({"repo": label, "action": "updated", "detail": "latest"})
                except subprocess.CalledProcessError as exc:
                    msg = f"{label} update failed: {exc}"
                    result.data["rows"].append({"repo": label, "action": "failed", "detail": str(exc)})
                    outer.add_error(msg)

    output = prepare(result, outer, target=formatter.target, metadata=metadata)
    deliver(formatter, output, output_format, output_path)

    if outer.errors:
        raise OopsError("; ".join(outer.errors))
