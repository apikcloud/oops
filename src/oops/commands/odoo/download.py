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
from pathlib import Path

import click
from oops.commands.base import command, render_and_exit
from oops.core.compat import Optional
from oops.core.config import config
from oops.core.logger import live_progress, log
from oops.core.metadata import get_metadata
from oops.core.models import Result
from oops.io.file import get_odoo_sources_dirs, parse_odoo_version
from oops.output.formatters import (
    FormatterRegistry,
    JsonFormatter,
    OutputFormatter,
    SimpleSummaryConsoleFormatter,
)
from oops.services.git import require_repository
from oops.utils.git import clone, update_latest
from oops.utils.helpers import normalize_version
from oops.utils.render import prompt_select

from .presenters.download import DownloadPresenter

FORMATTERS: FormatterRegistry = {
    "text": SimpleSummaryConsoleFormatter,
    "json": JsonFormatter,
}


@command(name="download", help=__doc__)
@click.option(
    "--version",
    default=None,
)
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
@click.pass_context
def main(
    ctx,
    version: Optional[str],
    do_update: bool,
    with_community: bool,
    with_enterprise: bool,
    with_themes: bool,
    output_format: str,
    output_path: "Path | None",
    verbose: bool,
) -> None:
    formatter: OutputFormatter = FORMATTERS[output_format]()
    metadata = get_metadata()
    assert metadata is not None

    result: Result[dict] = Result({"cmd": f"Download Odoo {version} sources", "rows": []})
    assert result.data is not None

    if version is None:
        try:
            _, repo_path = require_repository()
            image_info = parse_odoo_version(repo_path)
            version = str(image_info.major_version)
        except Exception:
            version = prompt_select(
                "Select a version:",
                [f"{item}.0" for item in range(config.odoo.min_version, config.odoo.max_version + 1, 1)],
            )

    version = normalize_version(version)
    dirs = get_odoo_sources_dirs(version)

    repos = [
        ("Community", config.odoo.community_url, dirs.community, with_community),
        ("Enterprise", config.odoo.enterprise_url, dirs.enterprise, with_enterprise),
        ("Themes", config.odoo.themes_url, dirs.themes, with_themes),
    ]

    with live_progress("Downloading Odoo sources…"):
        for label, url, dest, enabled in repos:
            if not enabled:
                continue

            if dest.exists():
                if do_update:
                    log.info(f"Updating Odoo {label} {version}…")
                    try:
                        update_latest(dest, quiet=not verbose)
                        result.data["rows"].append({"repo": label, "action": "updated", "status": "ok"})
                    except subprocess.CalledProcessError as exc:
                        msg = f"{label} update failed: {exc}"
                        result.data["rows"].append({"repo": label, "action": "failed", "status": msg})
                        result.add_error(msg)
                else:
                    msg = f"'{dest}' already exists — skipping {label} clone (use --update to pull)"
                    result.add_warning(msg)
                    result.data["rows"].append({"repo": label, "action": "skipped", "status": msg})
            else:
                log.info(f"Cloning Odoo {label} {version}…")
                try:
                    clone(url, dest, version, quiet=not verbose)
                    result.data["rows"].append({"repo": label, "action": "cloned", "status": "ok"})
                except subprocess.CalledProcessError as exc:
                    msg = f"{label} clone failed: {exc}"
                    result.data["rows"].append({"repo": label, "action": "failed", "status": msg})
                    result.add_error(msg)

    output = DownloadPresenter().prepare(result, target=formatter.target, metadata=metadata)
    render_and_exit(result, formatter, output, output_format, output_path)
